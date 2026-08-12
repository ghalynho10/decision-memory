"""Store format 2 and semantic search integrity tests (spec 0008 AC-6, AC-12).

A format 1 store refuses query and points to ``ingest --rebuild``; the real
store writes format 2 with SQLite schema 1; and the application fails, never
abstains, when semantic search returns anything other than exactly the
accepted chunk id set.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_index import FakeIndex, fake_embed
from test_query_roundtrip import _adapt_dm0012, _query_deps

from decision_memory.application.dto import (
    ActiveChunkDescriptor,
    IngestRequest,
    IngestState,
    QueryFilters,
    QueryRequest,
    QueryState,
    RetrievalFailure,
    RetrievalStage,
    SemanticMatches,
)
from decision_memory.application.ingest import IngestDependencies, ingest_records
from decision_memory.application.query import query_index
from decision_memory.infrastructure.index_reader import SqliteChromaIndexReader
from decision_memory.infrastructure.index_store import SqliteChromaIndexWriter
from decision_memory.infrastructure.manifest_reader import (
    load_manifest,
    manifest_path,
    raw_manifest_digest,
    record_loader,
)
from decision_memory.infrastructure.store import read_format
from decision_memory.infrastructure.tokenization import tiktoken_count


def _chunk(chunk_id: str) -> ActiveChunkDescriptor:
    return ActiveChunkDescriptor(
        chunk_id=chunk_id,
        record_id="DM-0012",
        record_title="Title",
        record_status="accepted",
        record_tags=(),
        value_path="body[0]",
        fingerprint="fp",
        ordinal=0,
        text="text",
        provenance=(),
    )


def test_format_one_store_refuses_query(tmp_path) -> None:
    index = FakeIndex()
    index.generation = "gen-fake"
    index.store_format_value = 1
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
    assert result.failure.code == "store.format"
    assert "ingest --rebuild" in result.failure.detail


def test_semantic_mismatched_id_set_is_a_failure(tmp_path) -> None:
    class BrokenIndex(FakeIndex):
        def semantic_search(self, embedding, accepted_chunk_ids):
            return SemanticMatches(("ch_other",), (0.5,))

    index = BrokenIndex()
    index.generation = "gen-fake"
    index.chunks["ch_a"] = _chunk("ch_a")
    index.embeddings["ch_a"] = [0.5] * 8
    with pytest.raises(RetrievalFailure) as excinfo:
        query_index(
            QueryRequest(
                question="why?",
                store_dir=Path("/fake/store"),
                allow_stale=True,
                filters=QueryFilters(),
            ),
            _query_deps(index),
        )
    assert excinfo.value.stage == RetrievalStage.SEMANTIC
    # The partial trace retains the completed filter and lexical sections.
    assert excinfo.value.trace.filters is not None
    assert excinfo.value.trace.lexical is not None
    assert excinfo.value.trace.semantic is None
    assert excinfo.value.trace.fusion is None


def test_semantic_misaligned_distances_is_a_failure(tmp_path) -> None:
    class BrokenIndex(FakeIndex):
        def semantic_search(self, embedding, accepted_chunk_ids):
            return SemanticMatches(("ch_a",), (0.5, 0.6))

    index = BrokenIndex()
    index.generation = "gen-fake"
    index.chunks["ch_a"] = _chunk("ch_a")
    index.embeddings["ch_a"] = [0.5] * 8
    with pytest.raises(RetrievalFailure) as excinfo:
        query_index(
            QueryRequest(
                question="why?",
                store_dir=Path("/fake/store"),
                allow_stale=True,
                filters=QueryFilters(),
            ),
            _query_deps(index),
        )
    assert excinfo.value.stage == RetrievalStage.SEMANTIC


@pytest.mark.integration
def test_real_store_is_format_two_and_semantic_search_exact(tmp_path) -> None:
    """The real writer produces format 2, SQLite schema 1, and exact ids."""
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
    assert ingest_result.state == IngestState.COMPLETED
    assert ingest_result.exit_code == 0
    assert read_format(store) == 2

    reader = SqliteChromaIndexReader(store)
    assert reader.store_format() == 2
    accepted = tuple(chunk.chunk_id for chunk in reader.active_chunks())
    assert accepted
    matches = reader.semantic_search(fake_embed(["question"])[0], accepted)
    assert set(matches.ids) == set(accepted)
    assert len(matches.ids) == len(accepted)
    assert len(matches.distances) == len(matches.ids)
    # Raw Chroma distances may carry tiny float noise at the 0 boundary; the
    # application clamps after validating near range (AC-6).
    assert all(
        distance == distance and -1e-6 <= distance <= 2.0 + 1e-6
        for distance in matches.distances
    )


def _real_ingest(records_dir: Path, store: Path, *, rebuild: bool) -> IngestState:
    writer = SqliteChromaIndexWriter(store)
    try:
        result = ingest_records(
            IngestRequest(
                records_dir=records_dir,
                store_dir=store,
                rebuild=rebuild,
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
    assert result.exit_code == 0
    return result.state


@pytest.mark.integration
def test_rebuild_preserves_format_two_and_format_one_refuses_query(tmp_path) -> None:
    """Rebuild keeps format 2 and SQLite schema 1; a format 1 store refuses."""
    records_dir = _adapt_dm0012(tmp_path)
    store = tmp_path / "store"
    assert _real_ingest(records_dir, store, rebuild=False) == IngestState.COMPLETED
    assert read_format(store) == 2
    assert _real_ingest(records_dir, store, rebuild=True) == IngestState.COMPLETED
    assert read_format(store) == 2

    reader = SqliteChromaIndexReader(store)
    result = query_index(
        QueryRequest(
            question="why?",
            store_dir=store,
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(reader),
    )
    assert result.state == QueryState.ANSWERED

    # A store whose FORMAT file reads 1 refuses query with a rebuild hint.
    (store / "FORMAT").write_text("1\n", encoding="utf-8")
    refused = query_index(
        QueryRequest(
            question="why?",
            store_dir=store,
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(reader),
    )
    assert refused.state == QueryState.FAILED
    assert refused.exit_code == 1
    assert refused.failure is not None
    assert refused.failure.code == "store.format"
    assert "ingest --rebuild" in refused.failure.detail
