"""Write free corpus validation tests (spec 0005 AC-5 to AC-9).

Covers the mode split between record and corpus validation, the distinct
violation versus exception result kinds, failure containment, and the no write
guarantee.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_adapter import FakeAdapter, fake_source
from spec_factory import make_corpus, write_spec
from typer.testing import CliRunner

from decision_memory.application.corpus_validation import validate_corpus
from decision_memory.cli import app

runner = CliRunner()


def _valid_corpus(tmp_path: Path) -> dict[str, dict[str, object]]:
    fake_source(tmp_path, "DM-0001", "docs/dm-0001.md")
    return {
        "DM-0001": {
            "title": "First decision",
            "chosen": "Option one",
            "why": ["It is better"],
            "evidence": "docs/dm-0001.md",
        }
    }


def _violating_corpus(tmp_path: Path) -> dict[str, dict[str, object]]:
    fake_source(tmp_path, "DM-0001", "docs/dm-0001.md")
    return {
        "DM-0001": {
            "title": "",
            "chosen": "Option one",
            "why": ["It is better"],
            "evidence": "docs/dm-0001.md",
        }
    }


class TestValidateCorpus:
    def test_valid_corpus_exits_zero(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        adapter = FakeAdapter(corpus=_valid_corpus(tmp_path))
        outcome = validate_corpus(corpus, adapter)
        assert outcome.exit_code == 0
        assert [result.kind for result in outcome.results] == ["ok"]
        assert outcome.adapter_id == "fake"

    def test_invalid_root_exits_three(self, tmp_path: Path) -> None:
        adapter = FakeAdapter()
        outcome = validate_corpus(tmp_path / "nope", adapter)
        assert outcome.exit_code == 3
        assert "corpus path" in (outcome.corpus_error or "")

    def test_corpus_error_exits_three(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        adapter = FakeAdapter(corpus_error="no decisions/ directory")
        outcome = validate_corpus(corpus, adapter)
        assert outcome.exit_code == 3
        assert outcome.corpus_error == "no decisions/ directory"

    def test_violation_is_a_distinct_kind_and_exits_one(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        adapter = FakeAdapter(corpus=_violating_corpus(tmp_path))
        outcome = validate_corpus(corpus, adapter)
        assert outcome.exit_code == 1
        result = outcome.results[0]
        assert result.kind == "violation"
        assert result.failure is None
        assert any(v.rule == "required.missing" for v in result.violations)

    def test_parse_exception_is_a_distinct_kind_and_later_sources_run(
        self,
        tmp_path: Path,
    ) -> None:
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
        outcome = validate_corpus(corpus, adapter)
        assert outcome.exit_code == 1
        by_id = {result.id: result for result in outcome.results}
        assert by_id["DM-0001"].kind == "exception"
        assert by_id["DM-0001"].failure is not None
        assert by_id["DM-0001"].failure.operation == "parse"
        assert by_id["DM-0002"].kind == "ok"

    def test_fingerprint_exception_skips_parse(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        adapter = FakeAdapter(
            corpus=_valid_corpus(tmp_path),
            fingerprint_errors={"DM-0001": OSError("read failed")},
        )
        outcome = validate_corpus(corpus, adapter)
        assert outcome.exit_code == 1
        result = outcome.results[0]
        assert result.kind == "exception"
        assert result.failure is not None
        assert result.failure.operation == "fingerprint"

    def test_discover_exception_stops_the_run(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        adapter = FakeAdapter(discover_error=RuntimeError("bad walk"))
        outcome = validate_corpus(corpus, adapter)
        assert outcome.exit_code == 1
        assert outcome.results == []
        assert outcome.discovery_failure is not None
        assert outcome.discovery_failure.operation == "discover"


class TestValidateCliModeSplit:
    def test_file_validation_is_unchanged(self, tmp_path: Path) -> None:
        record = tmp_path / "record.md"
        record.write_text(
            "---\n"
            'id: "0001"\n'
            "title: A decision\n"
            "status: accepted\n"
            "decision:\n"
            "  chosen: Chosen\n"
            "why:\n"
            "  - Because\n"
            "evidence:\n"
            "  - kind: file\n"
            "    target: source.md\n"
            "---\n",
            encoding="utf-8",
        )
        (tmp_path / "source.md").write_text("source", encoding="utf-8")
        result = runner.invoke(
            app, ["validate", str(record), "--project-root", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "valid record, no violations" in result.stdout

    def test_adapter_with_a_file_is_a_usage_error(self, tmp_path: Path) -> None:
        record = tmp_path / "record.md"
        record.write_text("not a record", encoding="utf-8")
        result = runner.invoke(
            app,
            ["validate", str(record), "--adapter", "jsmastery-specs"],
        )
        assert result.exit_code == 2
        assert "--adapter" in result.stdout

    def test_directory_runs_corpus_validation_without_writing(
        self,
        tmp_path: Path,
    ) -> None:
        corpus = make_corpus(tmp_path)
        write_spec(corpus, "0001-first")
        result = runner.invoke(app, ["validate", str(corpus)])
        assert result.exit_code == 0
        assert "adapter: jsmastery-specs" in result.stdout
        assert "ok DM-0001" in result.stdout
        # AC-6: corpus validation writes no records or manifest.
        assert not (corpus / ".decision-memory").exists()

    def test_directory_with_adapter_option_loads_the_named_adapter(
        self,
        tmp_path: Path,
    ) -> None:
        corpus = make_corpus(tmp_path)
        write_spec(corpus, "0001-first")
        result = runner.invoke(
            app, ["validate", str(corpus), "--adapter", "jsmastery-specs"]
        )
        assert result.exit_code == 0
        assert "adapter: jsmastery-specs" in result.stdout

    def test_invalid_corpus_exits_three(self, tmp_path: Path) -> None:
        result = runner.invoke(app, ["validate", str(tmp_path / "nope")])
        assert result.exit_code == 3
        assert "corpus path" in result.stdout

    def test_no_argument_is_a_usage_error(self) -> None:
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 2


def test_base_exception_propagates_and_is_not_converted(tmp_path: Path) -> None:
    # AC-8: in corpus validation too, KeyboardInterrupt keeps normal process
    # behavior; it is never recorded as a source exception result.
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    adapter = FakeAdapter(
        corpus=_valid_corpus(tmp_path),
        parse_errors={"DM-0001": KeyboardInterrupt()},
    )
    with pytest.raises(KeyboardInterrupt):
        validate_corpus(corpus, adapter)
