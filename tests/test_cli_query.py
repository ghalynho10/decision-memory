"""CLI tests for the ingest and query commands (spec 0007 AC-1)."""

from __future__ import annotations

from pathlib import Path

from spec_factory import make_corpus
from test_adapter_parse import REAL_PANEL_INDEX, REAL_PANEL_RATIONALE
from typer.testing import CliRunner

from decision_memory.application.adapter import adapt_corpus
from decision_memory.cli import app
from decision_memory.infrastructure.file_reader import write_record_file
from decision_memory.infrastructure.index_lock import store_lock
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter

runner = CliRunner()


def _adapt_dm0012(tmp_path) -> Path:
    corpus = make_corpus(tmp_path)
    spec_dir = corpus / "docs" / "specs" / "0012-portfolio"
    spec_dir.mkdir()
    (spec_dir / "index.md").write_text(REAL_PANEL_INDEX, encoding="utf-8")
    (spec_dir / "rationale.md").write_text(REAL_PANEL_RATIONALE, encoding="utf-8")
    outcome = adapt_corpus(corpus, JsmasteryAdapter(), write_record_file)
    assert outcome.exit_code == 0
    return corpus / ".decision-memory" / "records"


def test_ingest_cli_dry_run_prints_plan_without_writes(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    store = tmp_path / "store"
    result = runner.invoke(
        app,
        ["ingest", str(records_dir), "--store", str(store), "--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert "plan: added 1, updated 0, unchanged 0, removed 0, failed 0" in result.output
    assert "added DM-0012" in result.output
    assert "result: completed" in result.output
    assert "dry run, no provider calls or writes" in result.output
    # No store directory was created by the dry run.
    assert not store.exists()


def test_ingest_cli_missing_records_dir_exits_three(tmp_path) -> None:
    result = runner.invoke(
        app, ["ingest", str(tmp_path / "missing"), "--store", str(tmp_path / "s")]
    )
    assert result.exit_code == 3


def test_ingest_cli_no_resolved_records_dir_is_usage(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["ingest"])
    assert result.exit_code == 2


def test_query_cli_missing_store_exits_three(tmp_path) -> None:
    result = runner.invoke(
        app, ["query", "why?", "--store", str(tmp_path / "no-store")]
    )
    assert result.exit_code == 3


def test_ingest_cli_debug_prints_chunk_plan(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    result = runner.invoke(
        app,
        [
            "ingest",
            str(records_dir),
            "--store",
            str(tmp_path / "s"),
            "--dry-run",
            "--debug",
        ],
    )
    assert result.exit_code == 0
    assert "chunk " in result.output
    assert "evidence_tokens=" in result.output
    assert "embedding_tokens=" in result.output


def test_query_cli_locked_store_exits_one(tmp_path) -> None:
    store = tmp_path / "store"
    store.mkdir()
    with store_lock(store, exclusive=True):
        result = runner.invoke(app, ["query", "why?", "--store", str(store)])
    assert result.exit_code == 1
    assert "locked" in result.output


def test_ingest_cli_locked_store_exits_one(tmp_path) -> None:
    records_dir = _adapt_dm0012(tmp_path)
    store = tmp_path / "store"
    with store_lock(store, exclusive=True):
        result = runner.invoke(app, ["ingest", str(records_dir), "--store", str(store)])
    assert result.exit_code == 1
    assert "locked" in result.output
