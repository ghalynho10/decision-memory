"""Supersession tests (spec 0007 AC-18).

The jsmastery adapter emits no supersedes against JobPilot, so the live path
is recorded as untested there. These tests prove the built path with a
synthetic corpus that does carry ``**Supersedes**``: the store derives links
and evidence on ingest, the reader serves successor notices, a cycle fails
ingest, and the application renders the deterministic disclosure sentence with
a supersession citation.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_index import FakeIndex, fake_embed
from spec_factory import make_corpus, write_spec
from test_adapter_parse import REAL_PANEL_INDEX, REAL_PANEL_RATIONALE
from test_query_roundtrip import _adapt_dm0012, _ingest, _query_deps

from decision_memory.application.adapter import (
    Manifest,
    ManifestEntry,
    adapt_corpus,
)
from decision_memory.application.canonical import SourceReference
from decision_memory.application.dto import (
    CitationKind,
    IngestRequest,
    IngestState,
    QueryFilters,
    QueryRequest,
    QueryState,
    ResolutionState,
    SupersessionNotice,
)
from decision_memory.application.ingest import IngestDependencies, ingest_records
from decision_memory.application.query import (
    _render_disclosures,
    query_index,
)
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

SUPERSEDES_INDEX = """\
# 0013. Billing alert settings

**Date**: 2026-08-10
**Status**: Accepted
**Supersedes**: DM-0012

## Decision

**Chosen option**: Option 1: Send email on threshold

## Options considered

**Option 1:** Send email on threshold
**Pros**: Simple.
**Cons**: Email fatigue.

**Option 2:** No alert
**Pros**: Quiet.
**Cons**: Missed spikes.

## Rationale

The server route is the boundary.
"""


def _adapt_two(
    tmp_path,
    dm12_index: str = REAL_PANEL_INDEX,
    dm13_index: str = SUPERSEDES_INDEX,
) -> Path:
    corpus = make_corpus(tmp_path)
    write_spec(
        corpus,
        "0012-portfolio",
        index=dm12_index,
        rationale=REAL_PANEL_RATIONALE,
    )
    write_spec(corpus, "0013-portfolio", index=dm13_index)
    records = corpus / ".decision-memory" / "records"
    outcome = adapt_corpus(
        corpus, JsmasteryAdapter(), write_record_file, output=records
    )
    assert outcome.exit_code == 0
    return records


def _real_ingest(records_dir: Path, store: Path) -> IngestState:
    writer = SqliteChromaIndexWriter(store)
    try:
        result = ingest_records(
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
    return result


@pytest.mark.integration
def test_store_derives_links_and_serves_notices(tmp_path) -> None:
    records_dir = _adapt_two(tmp_path)
    store = tmp_path / "store"
    result = _real_ingest(records_dir, store)
    assert result.state == IngestState.COMPLETED
    assert result.exit_code == 0

    reader = SqliteChromaIndexReader(store)
    notices = reader.supersession_notices("DM-0012")
    assert len(notices) == 1
    notice = notices[0]
    assert notice.successor_id == "DM-0013"
    assert notice.successor_title == "Billing alert settings"
    assert notice.successor_status == "accepted"
    assert notice.metadata_evidence_id.startswith("mev_")
    # DM-0013 is a successor, not a predecessor: it has no outgoing notices.
    assert reader.supersession_notices("DM-0013") == ()


@pytest.mark.integration
def test_supersession_cycle_fails_ingest(tmp_path) -> None:
    dm12_index = REAL_PANEL_INDEX.replace(
        "**Status**: Accepted",
        "**Status**: Accepted\n**Supersedes**: DM-0013",
    )
    # DM-0013 supersedes DM-0012 and DM-0012 supersedes DM-0013: a cycle.
    records_dir = _adapt_two(tmp_path, dm12_index=dm12_index)
    result = _real_ingest(records_dir, tmp_path / "store")
    assert result.state == IngestState.FAILED
    assert result.exit_code == 1
    assert result.failure is not None
    assert result.failure.code == "supersession.invalid"
    assert "supersedes.cycle" in result.failure.detail


def test_query_renders_deterministic_disclosure(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    index = FakeIndex()
    _, index = _ingest(records_dir, index=index)
    index.supersession_notices_map["DM-0012"] = [
        SupersessionNotice(
            predecessor_id="DM-0012",
            successor_id="DM-0013",
            successor_title="Billing alert settings",
            successor_status="Accepted",
            successor_date=None,
            metadata_evidence_id="mev_abc",
        )
    ]
    result = query_index(
        QueryRequest(
            question="Why was the private beta access gate added?",
            store_dir=Path("/fake/store"),
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.ANSWERED
    texts = [sentence.text for sentence in result.sentences]
    assert any(
        text.startswith("This decision was later changed by Billing alert settings")
        for text in texts
    )
    supersession_citations = [
        citation
        for citation in result.citations
        if citation.kind == CitationKind.SUPERSESSION
    ]
    assert len(supersession_citations) == 1
    citation = supersession_citations[0]
    assert citation.evidence_id == "mev_abc"
    assert citation.record_id == "DM-0013"
    assert citation.chunk_id is None
    assert citation.value_path == "supersedes"
    # The disclosure sentence is cited to the supersession evidence.
    assert any(
        citation.citation_id in sentence.citation_ids
        for sentence in result.sentences
        if sentence.text.startswith("This decision was later changed by")
    )


def test_render_disclosures_uses_supersedes_provenance() -> None:
    manifest = Manifest(
        schema_version=2,
        adapter_version="5",
        source_root_hint="/tmp/corpus",
        entries=[
            ManifestEntry(
                id="DM-0013",
                fingerprint="f",
                contributing_files=["docs/specs/0013-portfolio/index.md"],
                record_path="DM-0013.md",
                record_digest="r",
                entry_digest="e",
                field_sources={
                    "supersedes": [
                        SourceReference(
                            "docs/specs/0013-portfolio/index.md", "preamble"
                        )
                    ]
                },
            )
        ],
    )
    notices = (
        SupersessionNotice(
            predecessor_id="DM-0012",
            successor_id="DM-0013",
            successor_title="Billing alert settings",
            successor_status="Accepted",
            successor_date=None,
            metadata_evidence_id="mev_x",
        ),
    )
    sentences, citations = _render_disclosures(
        manifest,
        notices,
        lambda path: ResolutionState.RESOLVED,
        frozenset(),
        start_at=3,
    )
    assert len(sentences) == 1
    assert len(citations) == 1
    citation = citations[0]
    assert citation.citation_id == "C4"
    assert citation.kind == CitationKind.SUPERSESSION
    assert citation.relative_path == "docs/specs/0013-portfolio/index.md"
    assert citation.section == "preamble"
    assert citation.resolution == ResolutionState.RESOLVED
    assert sentences[0].text == (
        "This decision was later changed by Billing alert settings (DM-0013)."
    )
    assert sentences[0].citation_ids == ("C4",)
