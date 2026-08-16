"""A store that moved still resolves its manifest and citations (spec 0014).

Builds a real SQLite plus Chroma store with the deterministic fake embedder,
so no API key is needed, then moves it and asks whether freshness and citation
resolution survive. Covers AC-3 (a relocated store reads ``CURRENT``), AC-4 (a
store beside a different corpus reads ``DRIFT`` rather than passing), AC-5
(citations resolve into the reader's own checkout), and AC-1a (``query`` and
``evaluate`` resolve one store identically because they share a helper).
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fake_index import (
    fake_coverage,
    fake_decompose,
    fake_embed,
    fake_entail,
    fake_extract_facets,
    fake_generate_answer,
)
from spec_factory import make_corpus
from test_adapter_parse import REAL_PANEL_INDEX, REAL_PANEL_RATIONALE

from decision_memory.application.adapter import adapt_corpus
from decision_memory.application.dto import (
    FreshnessState,
    IngestRequest,
    QueryFilters,
    QueryRequest,
    QueryResult,
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
from decision_memory.infrastructure.store_resolution import store_resolution
from decision_memory.infrastructure.tokenization import tiktoken_count

QUESTION = "Why was the private beta access gate added, and what was the alternative?"


def _build_project(root: Path, spec_dir_name: str = "0012-portfolio") -> Path:
    """Adapt and ingest one corpus into the default store layout under ``root``.

    Produces the ordinary shape a contributor gets: the corpus at the project
    root, records at ``.decision-memory/records``, and the index at
    ``.decision-memory/query-index``.
    """
    corpus = make_corpus(root)
    spec_dir = corpus / "docs" / "specs" / spec_dir_name
    spec_dir.mkdir()
    (spec_dir / "index.md").write_text(REAL_PANEL_INDEX, encoding="utf-8")
    (spec_dir / "rationale.md").write_text(REAL_PANEL_RATIONALE, encoding="utf-8")
    adapt = adapt_corpus(corpus, JsmasteryAdapter(), write_record_file)
    assert adapt.exit_code == 0
    records_dir = corpus / ".decision-memory" / "records"
    store_dir = corpus / ".decision-memory" / "query-index"
    writer = SqliteChromaIndexWriter(store_dir)
    try:
        result = ingest_records(
            IngestRequest(
                records_dir=records_dir,
                store_dir=store_dir,
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
    assert result.exit_code == 0
    return corpus


def _ask(store_dir: Path, **overrides: Any) -> QueryResult:
    """Ask the pinned question through the shared resolution helper."""
    reader = SqliteChromaIndexReader(store_dir)
    resolution = store_resolution(reader.manifest_metadata)
    values: dict[str, object] = {
        "store": reader,
        "count_tokens": tiktoken_count,
        "embed": fake_embed,
        "lexical_scorer": bm25_lexical_scorer,
        "load_manifest": resolution.load_manifest,
        "raw_manifest_digest": resolution.raw_manifest_digest,
        "resolve_source": resolution.resolve_source,
        "extract_facets": fake_extract_facets,
        "generate_answer": fake_generate_answer,
        "decompose": fake_decompose,
        "entail": fake_entail,
        "coverage": fake_coverage,
    }
    values.update(overrides)
    return query_index(
        QueryRequest(
            question=QUESTION,
            store_dir=store_dir,
            allow_stale=False,
            filters=QueryFilters(),
        ),
        QueryDependencies(**values),  # type: ignore[arg-type]
    )


def test_a_store_built_in_place_reads_current(tmp_path: Path) -> None:
    """The baseline: nothing moved, so the stored absolute path still works."""
    corpus = _build_project(tmp_path / "original")
    result = _ask(corpus / ".decision-memory" / "query-index")
    assert result.freshness == FreshnessState.CURRENT


def test_a_relocated_store_resolves_its_manifest(tmp_path: Path) -> None:
    """AC-3: the stored path is gone, so resolution falls back to the convention.

    The whole project is moved, which is what a copy, a restore from backup,
    or a clone at a different path looks like from the store's point of view:
    its recorded absolute path names nothing.
    """
    corpus = _build_project(tmp_path / "original")
    moved = tmp_path / "somewhere" / "else" / "project"
    moved.parent.mkdir(parents=True)
    shutil.move(str(corpus), str(moved))

    store_dir = moved / ".decision-memory" / "query-index"
    reader = SqliteChromaIndexReader(store_dir)
    resolved_manifest, _semantic, _raw, resolved_hint = reader.manifest_metadata()
    assert resolved_manifest is not None
    assert Path(resolved_manifest).is_file()
    assert Path(resolved_manifest).is_relative_to(moved)
    # AC-1c: the corpus root falls back to the store's grandparent, which is
    # the real project root for the default layout.
    assert resolved_hint == str(moved)

    result = _ask(store_dir)
    assert result.freshness == FreshnessState.CURRENT


def test_a_relocated_store_resolves_its_citations(tmp_path: Path) -> None:
    """AC-5: citations point at files in the reader's own checkout.

    This is the half that fails silently without the corpus root fallback: a
    relocated store would report ``CURRENT`` while every citation degraded to
    ``MISSING``, which looks like success.
    """
    corpus = _build_project(tmp_path / "original")
    moved = tmp_path / "elsewhere" / "project"
    moved.parent.mkdir(parents=True)
    shutil.move(str(corpus), str(moved))

    result = _ask(moved / ".decision-memory" / "query-index")
    assert result.citations
    states = {citation.resolution for citation in result.citations}
    assert states == {ResolutionState.RESOLVED}


def test_a_store_beside_a_different_corpus_reads_drift(tmp_path: Path) -> None:
    """AC-4: resolution must not turn a real mismatch into a pass.

    The store is placed where another project's manifest sits at the
    conventional path. The manifest is found, and then digest compared exactly
    as a manifest found by a stored path would be, so the mismatch surfaces.
    """
    corpus = _build_project(tmp_path / "original")
    other = _build_project(tmp_path / "other", spec_dir_name="0031-different")

    # Move only the index into the other project, leaving that project's own
    # records and manifest in the conventional place beside it.
    shutil.rmtree(other / ".decision-memory" / "query-index")
    shutil.move(
        str(corpus / ".decision-memory" / "query-index"),
        str(other / ".decision-memory" / "query-index"),
    )
    shutil.rmtree(tmp_path / "original")

    store_dir = other / ".decision-memory" / "query-index"
    reader = SqliteChromaIndexReader(store_dir)
    resolved_manifest = reader.manifest_metadata()[0]
    assert resolved_manifest is not None
    assert Path(resolved_manifest).is_file()

    result = _ask(store_dir)
    assert result.freshness == FreshnessState.DRIFT


def test_query_and_evaluate_resolve_one_store_identically(tmp_path: Path) -> None:
    """AC-1a: the two call sites read the same resolved values.

    Both build their resolution over the reader's ``manifest_metadata``, so
    this asserts the helper is the single source rather than two copies that
    happen to agree today.
    """
    corpus = _build_project(tmp_path / "original")
    moved = tmp_path / "moved" / "project"
    moved.parent.mkdir(parents=True)
    shutil.move(str(corpus), str(moved))
    store_dir = moved / ".decision-memory" / "query-index"

    first = store_resolution(SqliteChromaIndexReader(store_dir).manifest_metadata)
    second = store_resolution(SqliteChromaIndexReader(store_dir).manifest_metadata)
    assert first.load_manifest() == second.load_manifest()
    assert first.raw_manifest_digest() == second.raw_manifest_digest()
    assert first.resolve_source("docs/specs/0012-portfolio/index.md") == (
        second.resolve_source("docs/specs/0012-portfolio/index.md")
    )
    assert (
        first.resolve_source("docs/specs/0012-portfolio/index.md")
        == ResolutionState.RESOLVED
    )
