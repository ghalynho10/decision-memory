"""End to end adapt run tests (spec 0003).

Covers the manifest, incremental rewriting, dry runs, the output override,
and the exit codes, AC-14, AC-15, AC-17, AC-18, AC-21, AC-25.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fake_adapter import FakeAdapter, fake_source
from spec_factory import RATIONALE, make_corpus, write_spec
from typer.testing import CliRunner

from decision_memory.application.adapter import adapt_corpus
from decision_memory.cli import _print_adapt_report, app
from decision_memory.infrastructure.file_reader import write_record_file
from decision_memory.infrastructure.jsmastery_adapter import (
    ADAPTER_VERSION,
    JsmasteryAdapter,
)

runner = CliRunner()


def _run(corpus: Path, **kwargs: object) -> object:
    return adapt_corpus(corpus, JsmasteryAdapter(), write_record_file, **kwargs)


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


def test_manifest_is_schema_version_two_with_provenance_and_hint(tmp_path) -> None:
    # spec 0007 AC-2 and AC-19: the output manifest is schema version 2, every
    # entry carries record and entry digests plus field_sources, and the
    # source_root_hint is the absolute resolved corpus root.
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    outcome = _run(corpus)
    assert outcome.exit_code == 0
    manifest = json.loads(
        (_records_dir(corpus) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["schema_version"] == 2
    assert manifest["source_root_hint"] == corpus.resolve().as_posix()
    entry = manifest["entries"][0]
    assert entry["record_digest"]
    assert entry["entry_digest"]
    assert entry["field_sources"]["title"]


def test_manifest_field_sources_match_the_adapter_output(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    _run(corpus)
    manifest = json.loads(
        (_records_dir(corpus) / "manifest.json").read_text(encoding="utf-8")
    )
    entry = manifest["entries"][0]
    assert entry["field_sources"]["decision.chosen"] == [
        {"path": "docs/specs/0001-first/index.md", "section": "Decision"}
    ]
    assert entry["field_sources"]["context.problem"] == [
        {"path": "docs/specs/0001-first/rationale.md", "section": "Context"}
    ]


def test_record_and_entry_digests_are_stable_and_detect_change(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    spec_dir = write_spec(corpus, "0001-first")
    _run(corpus)
    manifest_path = _records_dir(corpus) / "manifest.json"
    first = json.loads(manifest_path.read_text(encoding="utf-8"))
    first_entry = first["entries"][0]
    index_path = spec_dir / "index.md"
    index_path.write_text(
        index_path.read_text(encoding="utf-8").replace(
            "Build an internal state machine",
            "Build an internal state machine v2",
        ),
        encoding="utf-8",
    )
    _run(corpus)
    second = json.loads(manifest_path.read_text(encoding="utf-8"))
    second_entry = second["entries"][0]
    assert second_entry["record_digest"] != first_entry["record_digest"]
    assert second_entry["entry_digest"] != first_entry["entry_digest"]


def test_previous_v1_manifest_rewrites_everything_with_warning(tmp_path) -> None:
    # spec 0007 AC-2: an older schema version 1 manifest (no schema_version)
    # cannot support incremental skip decisions, so adapt rewrites every record
    # into the new schema and reports the warning.
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    records_dir = _records_dir(corpus)
    records_dir.mkdir(parents=True)
    (records_dir / "manifest.json").write_text(
        json.dumps({"entries": []}), encoding="utf-8"
    )
    outcome = _run(corpus)
    assert outcome.exit_code == 0
    assert outcome.manifest_warning is not None
    assert "schema version 2" in outcome.manifest_warning
    manifest = json.loads((records_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert [record.state for record in outcome.records] == ["written"]


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


def test_fingerprint_changes_when_adapter_version_changes(
    tmp_path, monkeypatch
) -> None:
    # covers AC-13's adapter version half: same files, different digest, so a
    # mapping change invalidates every prior fingerprint.
    import decision_memory.infrastructure.jsmastery_adapter as adapter_module

    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    adapter = JsmasteryAdapter()
    spec = adapter.discover(corpus).specs[0]
    before = adapter.fingerprint(spec)
    monkeypatch.setattr(adapter_module, "ADAPTER_VERSION", "9")
    after = adapter.fingerprint(spec)
    assert before != after


def test_adapt_corpus_writes_through_the_injected_writer(tmp_path) -> None:
    # proves the layering fix: the use case writes via the injected writer
    # port and never touches the filesystem itself.
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    written: list[tuple[object, Path]] = []

    def fake_writer(record: object, path: Path) -> None:
        written.append((record, path))

    outcome = adapt_corpus(corpus, JsmasteryAdapter(), fake_writer)
    assert outcome.exit_code == 0
    assert len(written) == 1
    assert written[0][1].name == "DM-0001.md"
    # The directory exists (the manifest write creates it), but no record file
    # reached the disk through the real writer.
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
    assert "corpus path does not exist or is not a directory" in result.stdout


def test_adapt_corpus_without_docs_specs_reports_the_missing_structure(
    tmp_path,
) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    result = runner.invoke(app, ["adapt", str(corpus)])
    assert result.exit_code == 3
    assert "no docs/specs/ directory" in result.stdout


# --- Spec 0005 third party adapter behavior (AC-1, AC-4, AC-15, AC-20) ---


def _valid_corpus(tmp_path) -> dict[str, dict[str, object]]:
    """Corpus data whose records are valid: title, chosen, why, resolving evidence."""
    return {
        "DM-0001": {
            "title": "First decision",
            "chosen": "Option one",
            "why": ["It is better"],
            "evidence": "docs/dm-0001.md",
        }
    }


def test_jsmastery_adapter_exposes_identity_and_version() -> None:
    adapter = JsmasteryAdapter()
    assert adapter.adapter_id == "jsmastery-specs"
    assert adapter.adapter_version == ADAPTER_VERSION


def test_third_party_adapter_runs_through_adapt_corpus(tmp_path) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    fake_source(tmp_path, "DM-0001", "docs/dm-0001.md")
    adapter = FakeAdapter(
        adapter_id="vendor", adapter_version="2", corpus=_valid_corpus(tmp_path)
    )
    outcome = adapt_corpus(corpus, adapter, write_record_file)
    assert outcome.exit_code == 0
    assert [record.state for record in outcome.records] == ["written"]
    assert outcome.adapter_id == "vendor"
    assert outcome.adapter_version == "2"
    manifest = json.loads(
        (_records_dir(corpus) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["adapter_version"] == "2"


def test_adapt_report_prints_adapter_identity_near_the_start(tmp_path, capsys) -> None:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    adapter = FakeAdapter(corpus=_valid_corpus(tmp_path))
    outcome = adapt_corpus(corpus, adapter, write_record_file)
    _print_adapt_report(outcome)
    first_line = capsys.readouterr().out.splitlines()[0]
    assert first_line.startswith("adapter: fake 1")


def test_manifest_version_is_the_loaded_adapter_version(tmp_path) -> None:
    # AC-15: the manifest carries the adapter's own version, not a hard coded one.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    adapter = FakeAdapter(
        adapter_id="vendor", adapter_version="42", corpus=_valid_corpus(tmp_path)
    )
    adapt_corpus(corpus, adapter, write_record_file)
    manifest = json.loads(
        (_records_dir(corpus) / "manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["adapter_version"] == "42"


def test_corpus_error_exits_three_and_names_the_missing_structure(tmp_path) -> None:
    # AC-20: the adapter names its own missing layout and the run maps it to 3.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    adapter = FakeAdapter(corpus_error="no decisions/ directory")
    outcome = adapt_corpus(corpus, adapter, write_record_file)
    assert outcome.exit_code == 3
    assert outcome.corpus_error == "no decisions/ directory"


def test_discover_exception_exits_one_and_names_the_phase(tmp_path) -> None:
    # AC-9: an adapter execution failure exits 1 with the failed phase named.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    adapter = FakeAdapter(discover_error=RuntimeError("bad layout walk"))
    outcome = adapt_corpus(corpus, adapter, write_record_file)
    assert outcome.exit_code == 1
    assert outcome.failure is not None
    assert outcome.failure.operation == "discover"
    assert outcome.failure.exception_type == "RuntimeError"
    assert "bad layout walk" in outcome.failure.message


def test_parse_exception_marks_that_source_failed_and_continues(tmp_path) -> None:
    # AC-8: a parse exception stops that source, later sources still run.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    fake_source(tmp_path, "DM-0001", "docs/dm-0001.md")
    fake_source(tmp_path, "DM-0002", "docs/dm-0002.md")
    adapter = FakeAdapter(
        corpus={
            **_valid_corpus(tmp_path),
            "DM-0002": {
                "title": "Second",
                "chosen": "Option two",
                "why": ["Also better"],
                "evidence": "docs/dm-0002.md",
            },
        },
        parse_errors={"DM-0001": ValueError("unexpected body")},
    )
    outcome = adapt_corpus(corpus, adapter, write_record_file)
    assert outcome.exit_code == 1
    states = {record.id: record for record in outcome.records}
    assert states["DM-0001"].state == "failed"
    assert states["DM-0001"].failure is not None
    assert states["DM-0001"].failure.operation == "parse"
    assert states["DM-0002"].state == "written"
    assert (_records_dir(corpus) / "DM-0002.md").is_file()


def test_fingerprint_exception_skips_parse_for_that_source(tmp_path) -> None:
    # AC-8: when fingerprint raises, parse does not run for that source.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    adapter = FakeAdapter(
        corpus=_valid_corpus(tmp_path),
        fingerprint_errors={"DM-0001": OSError("fingerprint read failed")},
    )
    outcome = adapt_corpus(corpus, adapter, write_record_file)
    assert outcome.exit_code == 1
    record = outcome.records[0]
    assert record.state == "failed"
    assert record.failure is not None
    assert record.failure.operation == "fingerprint"


def test_keyboard_interrupt_from_parse_propagates_unchanged(tmp_path) -> None:
    # AC-8: KeyboardInterrupt and other BaseException subclasses keep normal
    # process behavior; they are never converted into an adapter failure.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    adapter = FakeAdapter(
        corpus=_valid_corpus(tmp_path),
        parse_errors={"DM-0001": KeyboardInterrupt()},
    )
    with pytest.raises(KeyboardInterrupt):
        adapt_corpus(corpus, adapter, write_record_file)
