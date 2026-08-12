"""End to end ingest and query tests with deterministic fakes (spec 0007 AC-11).

Adapts a DM-0012 shaped corpus, ingests it into an in memory index with a
deterministic fake embedder, then queries with fake generation callables that
return the AC-11 structured propositions. The live provider check remains an
integration test; this deterministic test locks the same structured
propositions against the real pipeline.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fake_index import (
    FakeIndex,
    fake_coverage,
    fake_embed,
    fake_entail,
    fake_extract_facets,
    fake_generate_answer,
)
from spec_factory import make_corpus
from test_adapter_parse import REAL_PANEL_INDEX, REAL_PANEL_RATIONALE

from decision_memory.application.adapter import adapt_corpus
from decision_memory.application.dto import (
    AbstentionStage,
    FreshnessState,
    IngestRequest,
    IngestState,
    QueryFilters,
    QueryRequest,
    QueryState,
    ResolutionState,
)
from decision_memory.application.ingest import IngestDependencies, ingest_records
from decision_memory.application.query import QueryDependencies, query_index
from decision_memory.infrastructure.bm25 import bm25_lexical_scorer
from decision_memory.infrastructure.file_reader import write_record_file
from decision_memory.infrastructure.index_reader import SqliteChromaIndexReader
from decision_memory.infrastructure.index_store import SqliteChromaIndexWriter
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter
from decision_memory.infrastructure.manifest_reader import (
    load_manifest,
    manifest_path,
    raw_manifest_digest,
    record_loader,
)
from decision_memory.infrastructure.tokenization import tiktoken_count


def _adapt_dm0012(tmp_path) -> Path:
    corpus = make_corpus(tmp_path)
    spec_dir = corpus / "docs" / "specs" / "0012-portfolio"
    spec_dir.mkdir()
    (spec_dir / "index.md").write_text(REAL_PANEL_INDEX, encoding="utf-8")
    (spec_dir / "rationale.md").write_text(REAL_PANEL_RATIONALE, encoding="utf-8")
    outcome = adapt_corpus(corpus, JsmasteryAdapter(), write_record_file)
    assert outcome.exit_code == 0
    return corpus / ".decision-memory" / "records"


def _query_deps(index: Any, **overrides: object) -> QueryDependencies:
    def _stored_manifest_path() -> Path | None:
        stored = index.manifest_metadata()[0]
        return Path(stored) if stored else None

    def load_stored_manifest():
        path = _stored_manifest_path()
        if path is None:
            raise FileNotFoundError("no stored manifest path")
        return load_manifest(path)

    def stored_manifest_digest():
        path = _stored_manifest_path()
        if path is None:
            raise FileNotFoundError("no stored manifest path")
        return raw_manifest_digest(path)

    values: dict[str, object] = {
        "store": index,
        "count_tokens": tiktoken_count,
        "embed": fake_embed,
        "lexical_scorer": bm25_lexical_scorer,
        "load_manifest": load_stored_manifest,
        "raw_manifest_digest": stored_manifest_digest,
        "resolve_source": lambda path: (
            ResolutionState.RESOLVED if path else ResolutionState.HINT_UNAVAILABLE
        ),
        "extract_facets": fake_extract_facets,
        "generate_answer": fake_generate_answer,
        "entail": fake_entail,
        "coverage": fake_coverage,
    }
    values.update(overrides)
    return QueryDependencies(**values)  # type: ignore[arg-type]


def _ingest(records_dir: Path, index: FakeIndex | None = None, dry_run: bool = False):
    index = index or FakeIndex()
    result = ingest_records(
        IngestRequest(
            records_dir=records_dir,
            store_dir=Path("/fake/store"),
            rebuild=False,
            dry_run=dry_run,
        ),
        IngestDependencies(
            load_manifest=lambda: load_manifest(manifest_path(records_dir)),
            read_record=record_loader(records_dir),
            count_tokens=tiktoken_count,
            embed=fake_embed,
            raw_manifest_digest=lambda: raw_manifest_digest(manifest_path(records_dir)),
            require_api_key=lambda: None,
            store=index,
        ),
    )
    return result, index


def test_adapt_ingest_query_locks_ac11_propositions(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    ingest_result, index = _ingest(records_dir)
    assert ingest_result.state == IngestState.COMPLETED
    assert ingest_result.exit_code == 0
    assert index.generation == "gen-fake"
    assert index.chunks

    result = query_index(
        QueryRequest(
            question=(
                "Why was the private beta access gate added, "
                "and what was the alternative?"
            ),
            store_dir=Path("/fake/store"),
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.ANSWERED
    assert result.exit_code == 0
    texts = [sentence.text for sentence in result.sentences]
    assert "Option B covering all four routes was chosen." in texts
    assert "Panel 1 decided which routes the gate covers." in texts
    assert "The two agent routes only (the original proposal)" in " ".join(texts)
    # Every citation points at a DM-0012 chunk.
    assert result.citations
    assert all(citation.record_id == "DM-0012" for citation in result.citations)
    assert all(citation.chunk_id is not None for citation in result.citations)
    # The separately extracted why facet is covered by an entailed sentence.
    why_sentence = next(
        sentence
        for sentence in result.sentences
        if "protect the portfolio" in sentence.text
    )
    assert why_sentence.citation_ids


def test_empty_index_abstains_without_embedding(tmp_path) -> None:
    index = FakeIndex()
    index.generation = "gen-fake"
    index.empty_eligible = True
    result = query_index(
        QueryRequest(
            question="anything at all",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(index, embed=_raise_if_called),
    )
    assert result.state == QueryState.ABSTAINED
    assert result.abstention_stage == AbstentionStage.RETRIEVAL
    assert result.exit_code == 0
    assert result.failure is None


def test_provider_failure_is_never_abstention(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    _, index = _ingest(records_dir)

    def failing_facets(question, attempts=None):
        raise RuntimeError("provider exploded")

    result = query_index(
        QueryRequest(
            question="why?",
            store_dir=Path("/fake/store"),
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(index, extract_facets=failing_facets),
    )
    assert result.state == QueryState.FAILED
    assert result.exit_code == 1
    assert result.abstention_stage is None
    assert result.failure is not None
    assert result.failure.stage == "generation"
    assert result.failure.code == "provider.facets"


def test_pipeline_mismatch_refuses(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    _, index = _ingest(records_dir)
    index.signature = "a-different-signature"
    result = query_index(
        QueryRequest(
            question="why?",
            store_dir=Path("/fake/store"),
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.FAILED
    assert result.exit_code == 1
    assert result.freshness == FreshnessState.INCOMPATIBLE
    assert result.failure is not None
    assert result.failure.code == "pipeline.incompatible"


def test_empty_question_is_usage(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    _, index = _ingest(records_dir)
    result = query_index(
        QueryRequest(
            question="   \t",
            store_dir=Path("/fake/store"),
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.FAILED
    assert result.exit_code == 2
    assert result.failure is not None
    assert result.failure.code == "usage.empty_question"


def test_query_without_active_generation_is_corrupt_init(tmp_path) -> None:
    """A store with no active generation is corrupt initialized state (AC-21)."""
    index = FakeIndex()  # generation left None, as a FORMAT only store presents
    result = query_index(
        QueryRequest(
            question="why?",
            store_dir=Path("/fake/store"),
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.FAILED
    assert result.exit_code == 1
    assert result.failure is not None
    assert result.failure.code == "store.uninitialized"


def _raise_if_called(texts, attempts=None):
    raise AssertionError("embedding must not be called on an empty index")


@pytest.mark.integration
def test_real_store_roundtrip_with_deterministic_embedder(tmp_path) -> None:
    """The real SQLite plus Chroma writer and reader, no provider or key.

    Locks the real store wiring, including the Chroma eligibility filter, the
    parity check, and citation allocation, with a deterministic embedder so no
    API key is needed.
    """
    records_dir = _adapt_dm0012(tmp_path)
    store = tmp_path / "store"
    writer = SqliteChromaIndexWriter(store)
    try:
        ingest_result = ingest_records(
            IngestRequest(
                records_dir=records_dir,
                store_dir=store,
                rebuild=False,
                dry_run=False,
            ),
            IngestDependencies(
                load_manifest=lambda: load_manifest(manifest_path(records_dir)),
                read_record=record_loader(records_dir),
                count_tokens=tiktoken_count,
                embed=fake_embed,
                raw_manifest_digest=lambda: raw_manifest_digest(
                    manifest_path(records_dir)
                ),
                require_api_key=lambda: None,
                store=writer,
            ),
        )
    finally:
        writer.close()
    assert ingest_result.exit_code == 0

    reader = SqliteChromaIndexReader(store)
    assert reader.parity_problems() == []
    assert reader.eligible_tuples()
    result = query_index(
        QueryRequest(
            question=(
                "Why was the private beta access gate added, "
                "and what was the alternative?"
            ),
            store_dir=store,
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(reader),
    )
    assert result.state == QueryState.ANSWERED
    assert any(citation.record_id == "DM-0012" for citation in result.citations)
