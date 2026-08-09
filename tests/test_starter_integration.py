"""Starter adapter integration (spec 0005 AC-19).

Exercises the documented third party path end to end: the CLI loads the
starter by its selector through the real importlib loader, corpus validation
reports both fixtures, and adaptation writes a valid record. This is an
integration test, excluded from the default fast unit run.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from decision_memory.cli import app

runner = CliRunner()

_FIXTURES = (
    Path(__file__).resolve().parent.parent
    / "examples"
    / "starter-adapter"
    / "decisions"
)


@pytest.mark.integration
class TestStarterThroughTheLoader:
    def test_corpus_validation_reports_both_fixtures(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        shutil.copytree(_FIXTURES, corpus / "decisions")
        result = runner.invoke(
            app,
            [
                "validate",
                str(corpus),
                "--adapter",
                "starter_adapter.adapter:adapter",
            ],
        )
        assert result.exit_code == 0
        assert "adapter: starter-adapter 1" in result.stdout
        assert "ok valid" in result.stdout
        assert "skipped" in result.stdout
        # Corpus validation writes nothing.
        assert not (corpus / ".decision-memory").exists()

    def test_adapt_writes_a_valid_record(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        shutil.copytree(_FIXTURES, corpus / "decisions")
        out_dir = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "adapt",
                str(corpus),
                "--adapter",
                "starter_adapter.adapter:adapter",
                "--output",
                str(out_dir),
            ],
        )
        assert result.exit_code == 0
        assert "adapter: starter-adapter 1" in result.stdout
        assert "written valid" in result.stdout
        record = out_dir / "valid.md"
        assert record.is_file()
        assert "title: Use Postgres for the catalog" in record.read_text(
            encoding="utf-8"
        )

    def test_missing_decisions_directory_exits_three(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        result = runner.invoke(
            app,
            [
                "validate",
                str(corpus),
                "--adapter",
                "starter_adapter.adapter:adapter",
            ],
        )
        assert result.exit_code == 3
        assert "no decisions/ directory" in result.stdout
