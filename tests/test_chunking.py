"""Chunker tests (spec 0007 AC-4, AC-5).

Covers the value path grammar, deterministic chunk ids, the embedding prefix,
field boundary chunking over a real adapted record, the atomic alternative
chunk, bounded paragraph packing, and the oversize record failure.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from spec_factory import make_corpus, write_spec

from decision_memory.application.chunking import (
    ChunkingError,
    chunk_id,
    chunk_record,
    embedding_input,
    is_valid_value_path,
)
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter
from decision_memory.infrastructure.tokenization import tiktoken_count


def _adapted(tmp_path):
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    discovery = JsmasteryAdapter().discover(corpus)
    assert len(discovery.specs) == 1
    return JsmasteryAdapter().parse(discovery.specs[0])


def _plans(tmp_path, record=None, field_sources=None):
    result = _adapted(tmp_path)
    record = record if record is not None else result.record
    sources = field_sources if field_sources is not None else result.field_sources
    assert record is not None
    return chunk_record(record, sources, "gen-1", "fp-1", tiktoken_count)


def test_value_path_grammar() -> None:
    assert is_valid_value_path("title")
    assert is_valid_value_path("decision.chosen")
    assert is_valid_value_path("decision.alternatives[3].title")
    assert is_valid_value_path("why[12]")
    assert is_valid_value_path("context.triggering_change")
    assert not is_valid_value_path("")
    assert not is_valid_value_path(".leading")
    assert not is_valid_value_path("a..b")
    assert not is_valid_value_path("body[]")
    assert not is_valid_value_path("why[abc]")
    assert not is_valid_value_path("title.")


def test_chunk_id_is_deterministic_and_prefixed() -> None:
    first = chunk_id("gen", "DM-0001", "fp", "decision.chosen", 0)
    second = chunk_id("gen", "DM-0001", "fp", "decision.chosen", 0)
    assert first == second
    assert first.startswith("ch_")
    assert len(first) == 3 + 64


def test_chunk_id_changes_with_any_input() -> None:
    base = chunk_id("gen", "DM-0001", "fp", "decision.chosen", 0)
    assert chunk_id("gen2", "DM-0001", "fp", "decision.chosen", 0) != base
    assert chunk_id("gen", "DM-0002", "fp", "decision.chosen", 0) != base
    assert chunk_id("gen", "DM-0001", "fp2", "decision.chosen", 0) != base
    assert chunk_id("gen", "DM-0001", "fp", "why[0]", 0) != base
    assert chunk_id("gen", "DM-0001", "fp", "decision.chosen", 1) != base


def test_embedding_prefix_collapses_title_whitespace() -> None:
    text = embedding_input("  Private   Access  ", "decision.chosen", "Body text")
    assert text == (
        "Record title: Private Access\nValue path: decision.chosen\n\nBody text"
    )


def test_chunk_record_keeps_field_boundaries(tmp_path) -> None:
    result = _adapted(tmp_path)
    assert result.record is not None
    plans = chunk_record(
        result.record, result.field_sources, "gen", "fp", tiktoken_count
    )
    value_paths = [plan.value_path for plan in plans]
    assert "decision.chosen" in value_paths
    assert "context.problem" in value_paths
    assert "rationale_summary" in value_paths
    assert "body[0]" in value_paths
    assert "consequences.positive[0]" in value_paths
    assert "consequences.negative[0]" in value_paths
    chosen = next(plan for plan in plans if plan.value_path == "decision.chosen")
    # The stored text is underlying content only, never the prefix.
    assert chosen.text == result.record.decision.chosen
    assert chosen.evidence_token_count > 0
    assert chosen.embedding_input_token_count > chosen.evidence_token_count
    assert chosen.sources == tuple(result.field_sources["decision.chosen"])


def test_alternative_is_one_atomic_chunk(tmp_path) -> None:
    result = _adapted(tmp_path)
    assert result.record is not None
    plans = chunk_record(
        result.record, result.field_sources, "gen", "fp", tiktoken_count
    )
    alternative = next(
        (plan for plan in plans if plan.value_path == "decision.alternatives[0]"),
        None,
    )
    assert alternative is not None
    assert alternative.text == (
        "Alternative: Use a hosted provider\nRejected because: Cost and a third party."
    )
    expected_sources = {
        (ref.path, ref.section)
        for ref in result.field_sources["decision.alternatives[0].title"]
    } | {
        (ref.path, ref.section)
        for ref in result.field_sources["decision.alternatives[0].rejection_reason"]
    }
    assert {(ref.path, ref.section) for ref in alternative.sources} == expected_sources


def test_body_splits_into_logical_sections(tmp_path) -> None:
    result = _adapted(tmp_path)
    assert result.record is not None
    body = "## One\n\nFirst section.\n\n## Two\n\nSecond section."
    plans = chunk_record(
        replace(result.record, body=body),
        result.field_sources,
        "gen",
        "fp",
        tiktoken_count,
    )
    body_paths = sorted(
        plan.value_path for plan in plans if plan.value_path.startswith("body[")
    )
    assert body_paths == ["body[0]", "body[1]"]
    first = next(plan for plan in plans if plan.value_path == "body[0]")
    assert first.text == "## One\n\nFirst section."


def test_long_unit_splits_into_bounded_chunks(tmp_path) -> None:
    result = _adapted(tmp_path)
    assert result.record is not None
    long_body = "## Long\n\n" + (
        "This paragraph is long enough to fill several chunks with real words. " * 80
    )
    plans = chunk_record(
        replace(result.record, body=long_body),
        result.field_sources,
        "gen",
        "fp",
        tiktoken_count,
    )
    body_plans = [plan for plan in plans if plan.value_path == "body[0]"]
    assert len(body_plans) > 1
    for plan in body_plans:
        assert plan.embedding_input_token_count <= 8191
        assert plan.evidence_token_count <= 500


def test_oversize_embedding_input_fails_the_record(tmp_path) -> None:
    result = _adapted(tmp_path)
    assert result.record is not None
    record = replace(result.record, body="## Huge\n\n" + ("word " * 20000))
    with pytest.raises(ChunkingError):
        chunk_record(record, result.field_sources, "gen", "fp", tiktoken_count)


def test_empty_values_produce_no_chunk(tmp_path) -> None:
    result = _adapted(tmp_path)
    assert result.record is not None
    record = replace(
        result.record,
        context=None,
        decision=None,
        why=[],
        rationale_summary=None,
        consequences=None,
        body="",
    )
    plans = chunk_record(record, {}, "gen", "fp", tiktoken_count)
    assert plans == ()
