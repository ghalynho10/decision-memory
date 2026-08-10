"""Ingest use case tests with deterministic fakes (spec 0007 AC-3, AC-7).

Covers the fresh index happy path, dry run with no provider call or write,
tampered record digest detection, and the provenance completeness check.
"""

from __future__ import annotations

from pathlib import Path

from fake_index import FakeIndex, fake_embed
from spec_factory import make_corpus
from test_adapter_parse import REAL_PANEL_INDEX, REAL_PANEL_RATIONALE

from decision_memory.application.adapter import adapt_corpus
from decision_memory.application.chunking import missing_provenance
from decision_memory.application.dto import (
    IngestRequest,
    IngestState,
    RecordAction,
)
from decision_memory.application.ingest import IngestDependencies, ingest_records
from decision_memory.domain.records import CanonicalDecisionRecord
from decision_memory.infrastructure.file_reader import write_record_file
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


def _ingest(records_dir: Path, dry_run: bool = False, embed=fake_embed):
    index = FakeIndex()
    calls: list[list[str]] = []

    def counting_embed(texts):
        calls.append(list(texts))
        return embed(texts)

    deps = IngestDependencies(
        load_manifest=lambda: load_manifest(manifest_path(records_dir)),
        read_record=record_loader(records_dir),
        count_tokens=tiktoken_count,
        embed=counting_embed,
        raw_manifest_digest=lambda: raw_manifest_digest(manifest_path(records_dir)),
        store=index,
    )
    result = ingest_records(
        IngestRequest(
            records_dir=records_dir,
            store_dir=Path("/fake/store"),
            rebuild=False,
            dry_run=dry_run,
        ),
        deps,
    )
    return result, index, calls


def test_ingest_adds_all_records_and_activates(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    result, index, calls = _ingest(records_dir)
    assert result.state == IngestState.COMPLETED
    assert result.exit_code == 0
    assert [record.record_id for record in result.records] == ["DM-0012"]
    assert result.records[0].action == RecordAction.ADDED
    assert result.records[0].chunks
    assert calls
    assert index.generation == "gen-fake"
    assert index.chunks


def test_ingest_dry_run_makes_no_provider_call_or_write(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    result, index, calls = _ingest(records_dir, dry_run=True)
    assert result.state == IngestState.COMPLETED
    assert result.exit_code == 0
    assert calls == []
    assert index.generation is None
    assert index.chunks == {}


def test_ingest_tampered_record_fails_that_record(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    record_path = records_dir / "DM-0012.md"
    original = record_path.read_text(encoding="utf-8")
    record_path.write_text(original.replace("Accepted", "Proposed"), encoding="utf-8")
    result, _, _ = _ingest(records_dir)
    assert result.state == IngestState.PARTIAL
    assert result.exit_code == 1
    assert result.records[0].action == RecordAction.FAILED
    assert result.records[0].failure_code == "digest.record_mismatch"


def test_ingest_without_records_dir_is_exit_three(tmp_path) -> None:
    missing = tmp_path / "missing"
    index = FakeIndex()
    result = ingest_records(
        IngestRequest(
            records_dir=missing,
            store_dir=Path("/fake/store"),
            rebuild=False,
            dry_run=False,
        ),
        IngestDependencies(
            load_manifest=lambda: None,
            read_record=lambda record_id: CanonicalDecisionRecord(),
            count_tokens=tiktoken_count,
            embed=fake_embed,
            raw_manifest_digest=lambda: "",
            store=index,
        ),
    )
    assert result.state == IngestState.FAILED
    assert result.exit_code == 3


def test_missing_provenance_names_every_path() -> None:
    from decision_memory.domain.records import Decision

    record = CanonicalDecisionRecord(
        id="DM-X",
        title="A title",
        decision=Decision(chosen="The chosen option"),
        why=["A reason"],
    )
    missing = missing_provenance(record, {})
    assert "title" in missing
    assert "decision.chosen" in missing
    assert "why[0]" in missing
