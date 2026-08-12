"""Freshness tests (spec 0007 AC-17, AC-9).

Covers the CURRENT, DRIFT, and UNKNOWN classifications, the default stale
refusal, the ``--allow-stale`` path with its reasons, and the stale version
citation marker. Drift is produced by pointing the stored manifest metadata at
a second manifest whose digest differs from the ingested one, which is exactly
what a changed corpus produces after adapt but before ingest.
"""

from __future__ import annotations

from pathlib import Path

from fake_index import FakeIndex
from spec_factory import INDEX, RATIONALE, make_corpus, write_spec
from test_query_roundtrip import _ingest, _query_deps

from decision_memory.application.adapter import (
    adapt_corpus,
    semantic_manifest_digest,
)
from decision_memory.application.dto import (
    CitationFreshness,
    FreshnessState,
    QueryFilters,
    QueryRequest,
    QueryState,
    StaleReason,
)
from decision_memory.application.query import query_index
from decision_memory.infrastructure.file_reader import write_record_file
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter
from decision_memory.infrastructure.manifest_reader import (
    load_manifest,
    manifest_path,
    raw_manifest_digest,
)


def _adapt(
    corpus: Path,
    specs: list[str],
    out: Path | None = None,
    *,
    index: str = INDEX,
    rationale: str | None = RATIONALE,
) -> Path:
    """Adapt a corpus with the named specs into a records directory."""
    for spec in specs:
        write_spec(corpus, spec, index=index, rationale=rationale)
    records_dir = out if out is not None else corpus / ".decision-memory" / "records"
    outcome = adapt_corpus(
        corpus, JsmasteryAdapter(), write_record_file, output=records_dir
    )
    assert outcome.exit_code == 0
    return records_dir


def _point_at(index: FakeIndex, records_dir: Path, prior_records: Path) -> None:
    """Point the fake's manifest metadata at a newer manifest digest."""
    prior_manifest = load_manifest(manifest_path(prior_records))
    index.set_manifest_metadata(
        str(manifest_path(records_dir)),
        semantic_manifest_digest(prior_manifest),
        raw_manifest_digest(manifest_path(prior_records)),
        "",
    )


def test_fresh_index_answers_current(tmp_path) -> None:
    records_dir = _adapt(make_corpus(tmp_path), ["0012-portfolio"])
    _, index = _ingest(records_dir)
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
    assert result.exit_code == 0
    assert result.freshness == FreshnessState.CURRENT
    assert result.trace.freshness.stale_reasons == ()


def test_record_added_drift_refuses_then_allow_stale(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    records_dir = _adapt(corpus, ["0012-portfolio"])
    _, index = _ingest(records_dir)
    # A newer manifest adds a second record (same 0012 content, new id).
    newer = _adapt(make_corpus(tmp_path / "two"), ["0012-portfolio", "0013-portfolio"])
    _point_at(index, newer, records_dir)

    refused = query_index(
        QueryRequest(
            question="Why was the private beta access gate added?",
            store_dir=Path("/fake/store"),
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert refused.state == QueryState.FAILED
    assert refused.exit_code == 1
    assert refused.failure is not None
    assert refused.failure.code == "stale.refused"
    assert refused.freshness == FreshnessState.DRIFT

    allowed = query_index(
        QueryRequest(
            question="Why was the private beta access gate added?",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert allowed.state == QueryState.ANSWERED
    assert allowed.freshness == FreshnessState.DRIFT
    assert StaleReason.RECORD_ADDED in allowed.trace.freshness.stale_reasons


def test_record_changed_drift_reports_changed(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    records_dir = _adapt(corpus, ["0012-portfolio"])
    _, index = _ingest(records_dir)
    changed_index = INDEX.replace(
        "private projects need a gate", "public pages need a gate"
    )
    newer = _adapt(
        make_corpus(tmp_path / "changed"),
        ["0012-portfolio"],
        index=changed_index,
    )
    _point_at(index, newer, records_dir)
    allowed = query_index(
        QueryRequest(
            question="Why was the private beta access gate added?",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert allowed.state == QueryState.ANSWERED
    assert allowed.freshness == FreshnessState.DRIFT
    assert StaleReason.RECORD_CHANGED in allowed.trace.freshness.stale_reasons


def test_record_removed_drift_reports_removed(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    records_dir = _adapt(corpus, ["0012-portfolio", "0013-portfolio"])
    _, index = _ingest(records_dir)
    # The newer manifest drops one record entirely.
    newer = _adapt(make_corpus(tmp_path / "one"), ["0012-portfolio"])
    _point_at(index, newer, records_dir)
    allowed = query_index(
        QueryRequest(
            question="Why was the private beta access gate added?",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert allowed.state == QueryState.ANSWERED
    assert allowed.freshness == FreshnessState.DRIFT
    assert StaleReason.RECORD_REMOVED in allowed.trace.freshness.stale_reasons


def test_unknown_manifest_is_stale(tmp_path) -> None:
    index = FakeIndex()
    index.generation = "gen-fake"
    index.empty_eligible = True
    result = query_index(
        QueryRequest(
            question="anything at all",
            store_dir=Path("/fake/store"),
            allow_stale=False,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.FAILED
    assert result.exit_code == 1
    assert result.failure is not None
    assert result.failure.code == "stale.refused"
    assert result.freshness == FreshnessState.UNKNOWN
    assert result.trace.freshness.stale_reasons == (StaleReason.MANIFEST_UNAVAILABLE,)


def test_failed_ingest_reports_failed(tmp_path) -> None:
    records_dir = _adapt(make_corpus(tmp_path), ["0012-portfolio"])
    _, index = _ingest(records_dir)
    manifest = load_manifest(manifest_path(records_dir))
    digest = manifest.entries[0].entry_digest
    index.mark_failed("DM-0012", "fp", "fp", "provider.embedding", digest)
    result = query_index(
        QueryRequest(
            question="Why was the private beta access gate added?",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.ANSWERED
    assert result.freshness == FreshnessState.DRIFT
    assert StaleReason.FAILED_INGEST in result.trace.freshness.stale_reasons


def test_failed_update_marks_citation_stale_version(tmp_path) -> None:
    records_dir = _adapt(make_corpus(tmp_path), ["0012-portfolio"])
    _, index = _ingest(records_dir)
    manifest = load_manifest(manifest_path(records_dir))
    digest = manifest.entries[0].entry_digest
    # A failed update: the desired fingerprint advanced, the active one did not.
    index.mark_failed("DM-0012", "fp-new", "fp-old", "provider.embedding", digest)
    result = query_index(
        QueryRequest(
            question="Why was the private beta access gate added?",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.ANSWERED
    assert result.citations
    assert any(
        citation.freshness == CitationFreshness.STALE_VERSION
        for citation in result.citations
    )


def test_record_changed_uses_entry_digest_not_fingerprint(tmp_path) -> None:
    """AC-17: RECORD_CHANGED fires on an entry digest change even when the
    ledger fingerprint is unchanged, proving freshness compares entry digests."""
    records_dir = _adapt(make_corpus(tmp_path), ["0012-portfolio"])
    _, index = _ingest(records_dir)
    manifest = load_manifest(manifest_path(records_dir))
    entry = manifest.entries[0]
    # Baseline: the ledger agrees with the manifest on both dimensions.
    assert index.ledger_fingerprints()[entry.id] == entry.fingerprint
    assert index.ledger_entry_digests()[entry.id] == entry.entry_digest
    # Only the entry digest diverges; the fingerprint is unchanged.
    index.entry_digests[entry.id] = "digest-X"
    # Force the reasons path by storing a divergent semantic digest that still
    # points at the same manifest on disk.
    index.set_manifest_metadata(
        str(manifest_path(records_dir)),
        "different-semantic-digest",
        raw_manifest_digest(manifest_path(records_dir)),
        "",
    )
    result = query_index(
        QueryRequest(
            question="Why was the private beta access gate added?",
            store_dir=Path("/fake/store"),
            allow_stale=True,
            filters=QueryFilters(),
        ),
        _query_deps(index),
    )
    assert result.state == QueryState.ANSWERED
    assert result.freshness == FreshnessState.DRIFT
    assert StaleReason.RECORD_CHANGED in result.trace.freshness.stale_reasons
