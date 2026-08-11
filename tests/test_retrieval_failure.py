"""Typed retrieval failure tests (spec 0008 AC-9, AC-10).

A scorer, store, fusion, or diversity anomaly raises ``RetrievalFailure`` with
the closed terminal stage and the partial trace completed before the failure;
it is never packaged as an abstention or a ``QueryResult``. The CLI exits 1
and renders the completed sections only in debug mode.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_index import FakeIndex
from test_query_roundtrip import _query_deps
from typer.testing import CliRunner

from decision_memory.application.dto import (
    ActiveChunkDescriptor,
    FilterRow,
    FilterState,
    FilterTrace,
    FreshnessState,
    FreshnessTrace,
    PartialQueryTrace,
    QueryFilters,
    QueryRequest,
    RetrievalFailure,
    RetrievalStage,
)
from decision_memory.application.query import query_index

runner = CliRunner()


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


class _BoomScorer:
    def __call__(self, query_tokens, document_tokens):
        raise RuntimeError("scorer exploded")


def test_scorer_failure_raises_typed_retrieval_failure(tmp_path) -> None:
    index = FakeIndex()
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
            _query_deps(index, lexical_scorer=_BoomScorer()),
        )
    assert excinfo.value.stage == RetrievalStage.LEXICAL
    # The filter section completed; the lexical section and later are absent.
    assert excinfo.value.trace.filters is not None
    assert excinfo.value.trace.lexical is None
    assert excinfo.value.trace.semantic is None
    assert excinfo.value.trace.fusion is None
    assert excinfo.value.trace.diversity is None


def test_cli_exits_one_and_renders_partial_trace_debug(
    tmp_path, monkeypatch, capsys
) -> None:
    from decision_memory import cli

    def _boom(request, deps):
        partial = PartialQueryTrace(
            freshness=FreshnessTrace(
                state=FreshnessState.CURRENT,
                stored_pipeline_signature="s",
                running_pipeline_signature="s",
                records_manifest_path=None,
                manifest_available=False,
                start_semantic_digest=None,
                end_semantic_digest=None,
                start_raw_digest=None,
                end_raw_digest=None,
                fingerprints=(),
                stale_reasons=(),
            ),
            filters=FilterTrace(
                rows=(
                    FilterRow(
                        "ch_a",
                        "DM-0012",
                        "accepted",
                        (),
                        "body[0]",
                        FilterState.ACCEPTED,
                        (),
                    ),
                )
            ),
            lexical=None,
            semantic=None,
            fusion=None,
            diversity=None,
            providers=(),
        )
        raise RetrievalFailure(RetrievalStage.SEMANTIC, partial)

    monkeypatch.setattr(cli, "query_index", _boom)
    store = tmp_path / "store"
    store.mkdir()
    result = runner.invoke(cli.app, ["query", "why?", "--store", str(store), "--debug"])
    assert result.exit_code == 1
    assert "error retrieval semantic" in result.output
    assert "Filter" in result.output
    assert "ch_a" in result.output
    assert "Lexical" not in result.output


def test_cli_retrieval_failure_without_debug_prints_error_only(
    tmp_path, monkeypatch
) -> None:
    from decision_memory import cli

    def _boom(request, deps):
        raise RetrievalFailure(RetrievalStage.FUSION, None)  # type: ignore[arg-type]

    monkeypatch.setattr(cli, "query_index", _boom)
    store = tmp_path / "store"
    store.mkdir()
    result = runner.invoke(cli.app, ["query", "why?", "--store", str(store)])
    assert result.exit_code == 1
    assert "error retrieval fusion" in result.output
    assert "Filter" not in result.output
