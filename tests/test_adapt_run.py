"""End to end adapt run tests (spec 0003).

Covers the manifest, incremental rewriting, dry runs, the output override,
and the exit codes, AC-14, AC-15, AC-17, AC-18, AC-21, AC-25.
"""

from __future__ import annotations

import json
from pathlib import Path

from spec_factory import RATIONALE, make_corpus, write_spec
from typer.testing import CliRunner

from decision_memory.application.adapter import adapt_corpus
from decision_memory.cli import app
from decision_memory.infrastructure.jsmastery_adapter import (
    ADAPTER_VERSION,
    JsmasteryAdapter,
)

runner = CliRunner()


def _run(corpus: Path, **kwargs: object) -> object:
    return adapt_corpus(corpus, JsmasteryAdapter(), ADAPTER_VERSION, **kwargs)


def _records_dir(corpus: Path) -> Path:
    return corpus / ".decision-memory" / "records"


def test_first_run_writes_records_and_manifest(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    write_spec(corpus, "0002-second")
    outcome = _run(corpus)
    assert outcome.exit_code == 0
    records_dir = _records_dir(corpus)
    assert (records_dir / "DM-0001.md").is_file()
    assert (records_dir / "DM-0002.md").is_file()
    manifest = json.loads((records_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["adapter_version"] == ADAPTER_VERSION
    assert manifest["generated_at"]
    assert [entry["id"] for entry in manifest["entries"]] == ["DM-0001", "DM-0002"]
    for entry in manifest["entries"]:
        assert entry["fingerprint"]
        assert entry["contributing_files"]
        assert entry["record_path"] == f"{entry['id']}.md"
    assert sorted(record.state for record in outcome.records) == ["written", "written"]


def test_second_run_rewrites_only_changed(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    spec_dir = write_spec(corpus, "0001-first")
    _run(corpus)
    record_path = _records_dir(corpus) / "DM-0001.md"
    first_text = record_path.read_text(encoding="utf-8")
    first_mtime = record_path.stat().st_mtime_ns
    outcome_two = _run(corpus)
    assert [record.state for record in outcome_two.records] == ["unchanged"]
    assert record_path.stat().st_mtime_ns == first_mtime
    (spec_dir / "rationale.md").write_text(
        RATIONALE + "\nA later refinement.\n", encoding="utf-8"
    )
    outcome_three = _run(corpus)
    assert [record.state for record in outcome_three.records] == ["rewritten"]
    assert record_path.read_text(encoding="utf-8") != first_text


def test_deleted_record_is_restored_even_when_the_fingerprint_matches(
    tmp_path,
) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    _run(corpus)
    record_path = _records_dir(corpus) / "DM-0001.md"
    original = record_path.read_text(encoding="utf-8")

    # The manifest still lists the record, so the fingerprint matches, but
    # the file itself is gone. Skipping the write here would leave the
    # manifest pointing at nothing.
    record_path.unlink()

    outcome = _run(corpus)
    assert [record.state for record in outcome.records] == ["rewritten"]
    assert outcome.exit_code == 0
    assert record_path.is_file()
    assert record_path.read_text(encoding="utf-8") == original


def test_dry_run_reports_a_missing_record_without_restoring_it(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    _run(corpus)
    record_path = _records_dir(corpus) / "DM-0001.md"
    record_path.unlink()

    outcome = _run(corpus, dry_run=True)
    assert [record.state for record in outcome.records] == ["rewritten"]
    assert not record_path.is_file()


def test_dry_run_writes_nothing_on_first_run(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    outcome = _run(corpus, dry_run=True)
    assert outcome.exit_code == 0
    assert [record.state for record in outcome.records] == ["written"]
    assert not _records_dir(corpus).exists()


def test_dry_run_leaves_existing_files_untouched(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    _run(corpus)
    record_path = _records_dir(corpus) / "DM-0001.md"
    manifest_path = _records_dir(corpus) / "manifest.json"
    record_before = record_path.read_bytes()
    manifest_before = manifest_path.read_bytes()
    _run(corpus, dry_run=True)
    assert record_path.read_bytes() == record_before
    assert manifest_path.read_bytes() == manifest_before


def test_output_option_overrides_default_directory(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    out_dir = tmp_path / "elsewhere"
    outcome = _run(corpus, output=out_dir)
    assert outcome.exit_code == 0
    assert (out_dir / "DM-0001.md").is_file()
    assert not _records_dir(corpus).exists()
    result = runner.invoke(
        app,
        ["validate", str(out_dir / "DM-0001.md"), "--project-root", str(corpus)],
    )
    assert result.exit_code == 0
    assert "valid record, no violations" in result.stdout


def test_missing_corpus_exits_three(tmp_path) -> None:
    outcome = _run(tmp_path / "nope")
    assert outcome.exit_code == 3


def test_corpus_without_docs_specs_exits_three(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    outcome = _run(corpus)
    assert outcome.exit_code == 3


def test_failing_spec_exits_one_and_writes_nothing_for_it(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    rationale = RATIONALE.split("## Rationale")[0]
    write_spec(corpus, "0001-first", rationale=rationale)
    outcome = _run(corpus)
    assert outcome.exit_code == 1
    assert [record.state for record in outcome.records] == ["failed"]
    assert not (_records_dir(corpus) / "DM-0001.md").exists()


def test_adapt_command_reports_and_exits_zero(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    result = runner.invoke(app, ["adapt", str(corpus)])
    assert result.exit_code == 0
    assert "written DM-0001" in result.stdout
    assert "manifest" in result.stdout or "output:" in result.stdout


def test_adapt_dry_run_flag_reports_and_writes_nothing(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    result = runner.invoke(app, ["adapt", str(corpus), "--dry-run"])
    assert result.exit_code == 0
    assert "dry run" in result.stdout
    assert not _records_dir(corpus).exists()


def test_adapt_missing_corpus_exits_three(tmp_path) -> None:
    result = runner.invoke(app, ["adapt", str(tmp_path / "nope")])
    assert result.exit_code == 3
    assert "no docs/specs" in result.stdout
