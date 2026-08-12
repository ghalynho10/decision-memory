"""Explicit query filter tests (spec 0008 AC-1 to AC-4).

Covers normalization and usage errors (AC-2), the fixed value path selector
matching (AC-3), the snapshot filtering rules with the fixed reason order
(AC-4), and the zero provider empty filter abstention at the query boundary.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_index import FakeIndex
from test_query_roundtrip import _adapt_dm0012, _ingest, _query_deps

from decision_memory.application.dto import (
    AbstentionStage,
    ActiveChunkDescriptor,
    FilterExclusionReason,
    FilterState,
    QueryFilters,
    QueryRequest,
    QueryState,
)
from decision_memory.application.filters import (
    FILTER_STATUSES,
    FIXED_VALUE_PATH_SELECTORS,
    FilterUsageError,
    build_query_filters,
    filter_descriptors,
    matches_value_path,
)
from decision_memory.application.query import query_index


def _chunk(
    chunk_id: str,
    record_id: str,
    status: str | None = None,
    tags: tuple[str, ...] = (),
    value_path: str = "body[0]",
) -> ActiveChunkDescriptor:
    return ActiveChunkDescriptor(
        chunk_id=chunk_id,
        record_id=record_id,
        record_title="Title",
        record_status=status,
        record_tags=tags,
        value_path=value_path,
        fingerprint="fp",
        ordinal=0,
        text="text",
        provenance=(),
    )


def _raise_if_called(texts, attempts=None):
    raise AssertionError("embedding must not be called on an empty filter")


def test_build_query_filters_normalizes_and_sorts() -> None:
    filters = build_query_filters(
        record_ids=["DM-0012", "dm-0012", "DM-0012"],
        statuses=["Accepted", "proposed"],
        tags=[" b ", "a", "b"],
        value_paths=["why[0]", "body[*]"],
    )
    # Record ids and tags stay case sensitive; statuses normalize to lowercase.
    assert filters.record_ids == ("DM-0012", "dm-0012")
    assert filters.statuses == ("accepted", "proposed")
    assert filters.tags == ("a", "b")
    assert filters.value_paths == ("body[*]", "why[0]")


def test_empty_value_is_usage_error() -> None:
    with pytest.raises(FilterUsageError):
        build_query_filters(record_ids=[" "])
    with pytest.raises(FilterUsageError):
        build_query_filters(tags=[""])


def test_unknown_status_is_usage_error() -> None:
    with pytest.raises(FilterUsageError):
        build_query_filters(statuses=["decided"])
    assert set(FILTER_STATUSES) == {
        "proposed",
        "accepted",
        "superseded",
        "rejected",
    }


def test_malformed_value_path_selector_is_usage_error() -> None:
    # A [*] selector that is not one of the fixed selectors is malformed.
    with pytest.raises(FilterUsageError):
        build_query_filters(value_paths=["foo[*]"])
    with pytest.raises(FilterUsageError):
        build_query_filters(value_paths=["body[ * ]"])
    # A value path that does not match the grammar is malformed.
    with pytest.raises(FilterUsageError):
        build_query_filters(value_paths=["body[0"])
    with pytest.raises(FilterUsageError):
        build_query_filters(value_paths=["body[x]"])
    with pytest.raises(FilterUsageError):
        build_query_filters(value_paths=["body[]"])


def test_grammar_valid_but_unmatched_paths_are_not_usage_errors() -> None:
    # A grammar valid path that matches no active chunk is not a usage error
    # (AC-2): it is a valid value that matches nothing.
    filters = build_query_filters(
        value_paths=["body", "body[0].text", "decision.alternatives[0].title"]
    )
    assert filters.value_paths == (
        "body",
        "body[0].text",
        "decision.alternatives[0].title",
    )


def test_fixed_value_path_selectors() -> None:
    assert FIXED_VALUE_PATH_SELECTORS == (
        "decision.alternatives[*]",
        "why[*]",
        "consequences.positive[*]",
        "consequences.negative[*]",
        "body[*]",
    )


def test_matches_value_path_exact_and_star() -> None:
    assert matches_value_path("body[0]", "body[0]")
    assert not matches_value_path("body[0]", "body[1]")
    assert matches_value_path("body[*]", "body[0]")
    assert matches_value_path("body[*]", "body[10]")
    assert matches_value_path("why[*]", "why[2]")
    # Exactly one ASCII decimal index with grammar 0|[1-9][0-9]*; no descendants.
    assert not matches_value_path("body[*]", "body[01]")
    assert not matches_value_path("body[*]", "body[0].text")
    assert not matches_value_path("body[*]", "body")
    assert not matches_value_path("why[0]", "why[00]")


def test_every_active_chunk_gets_a_row_with_no_filters() -> None:
    chunks = [
        _chunk("c1", "DM-0012", status="accepted"),
        _chunk("c2", "DM-0013"),
    ]
    rows = filter_descriptors(chunks, QueryFilters())
    assert len(rows) == 2
    assert all(row.state == FilterState.ACCEPTED for row in rows)
    assert all(row.exclusion_reasons == () for row in rows)


def test_filter_descriptors_reports_every_reason_in_fixed_order() -> None:
    chunks = [
        _chunk("c1", "DM-0012", status="accepted", tags=("billing",)),
        _chunk("c2", "DM-0013", status=None, tags=(), value_path="why[0]"),
        _chunk("c3", "DM-0014", status="rejected", tags=("resume",)),
    ]
    filters = build_query_filters(
        record_ids=["DM-0012"],
        statuses=["accepted"],
        tags=["billing"],
        value_paths=["body[*]"],
    )
    rows = filter_descriptors(chunks, filters)
    by_id = {row.chunk_id: row for row in rows}
    assert by_id["c1"].state == FilterState.ACCEPTED
    assert by_id["c1"].exclusion_reasons == ()
    assert by_id["c2"].state == FilterState.EXCLUDED
    assert by_id["c2"].exclusion_reasons == (
        FilterExclusionReason.RECORD_ID,
        FilterExclusionReason.STATUS,
        FilterExclusionReason.TAG,
        FilterExclusionReason.VALUE_PATH,
    )
    assert by_id["c3"].state == FilterState.EXCLUDED
    assert by_id["c3"].exclusion_reasons == (
        FilterExclusionReason.RECORD_ID,
        FilterExclusionReason.STATUS,
        FilterExclusionReason.TAG,
    )


def test_missing_status_fails_status_constraint() -> None:
    chunks = [_chunk("c1", "DM-0012", status=None)]
    filters = build_query_filters(statuses=["accepted"])
    rows = filter_descriptors(chunks, filters)
    assert rows[0].state == FilterState.EXCLUDED
    assert rows[0].exclusion_reasons == (FilterExclusionReason.STATUS,)


def test_or_within_field_and_across_fields() -> None:
    chunks = [
        _chunk("c1", "DM-0012", tags=("a",)),
        _chunk("c2", "DM-0013", tags=("b",)),
    ]
    filters = build_query_filters(record_ids=["DM-0012", "DM-0013"], tags=["a"])
    rows = filter_descriptors(chunks, filters)
    by_id = {row.chunk_id: row for row in rows}
    # Record ids OR to both, then the tag constraint ANDs: only c1 has tag a.
    assert by_id["c1"].state == FilterState.ACCEPTED
    assert by_id["c2"].state == FilterState.EXCLUDED


def test_valid_empty_filter_abstains_without_provider() -> None:
    index = FakeIndex()
    index.generation = "gen-fake"
    index.chunks["ch_a"] = _chunk(
        "ch_a", "DM-0012", status="accepted", tags=("billing",)
    )
    index.embeddings["ch_a"] = [0.5] * 8
    result = query_index(
        QueryRequest(
            question="anything at all",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=build_query_filters(tags=["resume"]),
        ),
        _query_deps(index, embed=_raise_if_called),
    )
    assert result.state == QueryState.ABSTAINED
    assert result.abstention_stage == AbstentionStage.RETRIEVAL
    assert result.exit_code == 0
    assert result.failure is None
    rows = result.trace.retrieval.filters.rows
    assert len(rows) == 1
    assert rows[0].state == FilterState.EXCLUDED
    assert rows[0].exclusion_reasons == (FilterExclusionReason.TAG,)


def test_matching_record_id_filter_still_answers(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    _, index = _ingest(records_dir)
    result = query_index(
        QueryRequest(
            question="Why was the private beta access gate added?",
            store_dir=Path("/fake/store"),
            allow_stale=False,
            filters=build_query_filters(record_ids=["DM-0012"]),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.ANSWERED
    assert result.exit_code == 0
    assert all(citation.record_id == "DM-0012" for citation in result.citations)
    assert any(
        row.state == FilterState.ACCEPTED for row in result.trace.retrieval.filters.rows
    )


def test_nonmatching_record_id_filter_abstains(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    _, index = _ingest(records_dir)
    result = query_index(
        QueryRequest(
            question="Why was the private beta access gate added?",
            store_dir=Path("/fake/store"),
            allow_stale=False,
            filters=build_query_filters(record_ids=["DM-9999"]),
        ),
        _query_deps(index, embed=_raise_if_called),
    )
    assert result.state == QueryState.ABSTAINED
    assert result.abstention_stage == AbstentionStage.RETRIEVAL
    assert result.exit_code == 0
    assert result.failure is None
