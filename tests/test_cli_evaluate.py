"""CLI tests for the evaluate command (feature 11, Slice 3).

Locks the harness mechanics at the command boundary: the fixed fixture
order in the report, the exit code mapping (0 all pass, 1 any fail, 2
usage, 3 missing corpus), the per fixture run rate line under --runs N,
the missing key fail loudly path, and the missing corpus path.

None of these tests pins any live fixture's pass or fail: the engine seam
is scripted, and the engine's oracle logic is locked separately in
test_evaluation.py. Today's stochastic live results are deliberately not
baked in here.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from spec_factory import make_corpus
from test_adapter_parse import REAL_PANEL_INDEX, REAL_PANEL_RATIONALE
from typer.testing import CliRunner, Result

from decision_memory.application.evaluation import (
    EVALUATION_FIXTURES,
    EvaluationCheck,
    EvaluationOutcome,
)
from decision_memory.cli import app

runner = CliRunner()

_FIXTURE_LINE = re.compile(r"^(PASS|FAIL) ([^ :]+)")


class _FakeRunner:
    """Stand in for EvaluationRunner: adapt and ingest succeed, no providers."""

    def __init__(self, corpus_root: Path, records_dir: Path, store_dir: Path) -> None:
        self.corpus_root = corpus_root
        self.records_dir = records_dir
        self.store_dir = store_dir
        self.adapt_called = False
        self.ingest_called = False

    def adapt(self) -> SimpleNamespace:
        self.adapt_called = True
        return SimpleNamespace(exit_code=0)

    def ingest(self, rebuild: bool) -> SimpleNamespace:
        self.ingest_called = True
        return SimpleNamespace(exit_code=0)


def _all_pass_outcome() -> EvaluationOutcome:
    """Every battery fixture passes, in the fixed engine order."""
    checks = [
        EvaluationCheck(fixture_id=fixture.id, status=True, detail="scripted")
        for fixture in EVALUATION_FIXTURES
    ]
    return EvaluationOutcome(checks=checks, passed=len(checks), failed=0, exit_code=0)


def _write_one_spec(corpus: Path) -> None:
    """Write one valid jsmastery spec so the real adapter adapts cleanly."""
    spec_dir = corpus / "docs" / "specs" / "0012-portfolio"
    spec_dir.mkdir(parents=True)
    (spec_dir / "index.md").write_text(REAL_PANEL_INDEX, encoding="utf-8")
    (spec_dir / "rationale.md").write_text(REAL_PANEL_RATIONALE, encoding="utf-8")


def _invoke_evaluate(
    corpus: Path,
    tmp_path: Path,
    *extra: str,
) -> Result:
    """Invoke evaluate against a corpus with deterministic temp dirs."""
    return runner.invoke(
        app,
        [
            "evaluate",
            str(corpus),
            "--records",
            str(tmp_path / "records"),
            "--store",
            str(tmp_path / "store"),
            *extra,
        ],
    )


# ---------------------------------------------------------------------------
# Exit codes: 3 missing corpus, 2 usage error, 1 missing key
# ---------------------------------------------------------------------------


def test_evaluate_missing_corpus_exits_three(tmp_path: Path) -> None:
    result = runner.invoke(app, ["evaluate", str(tmp_path / "nope")])
    assert result.exit_code == 3
    assert "corpus path does not exist or is not a directory" in result.stdout


def test_evaluate_runs_zero_is_a_usage_error(tmp_path: Path) -> None:
    corpus = make_corpus(tmp_path)
    result = runner.invoke(app, ["evaluate", str(corpus), "--runs", "0"])
    assert result.exit_code == 2
    assert "--runs must be at least 1" in result.stdout


def test_evaluate_missing_api_key_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    corpus = make_corpus(tmp_path)
    _write_one_spec(corpus)
    result = _invoke_evaluate(corpus, tmp_path)
    assert result.exit_code == 1
    assert "ingest failed; the harness needs OPENAI_API_KEY to build the index" in (
        result.stdout
    )


# ---------------------------------------------------------------------------
# Report grammar and exit mapping with a scripted engine seam
# ---------------------------------------------------------------------------


def test_evaluate_all_pass_exits_zero_and_reports_in_fixed_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = make_corpus(tmp_path)
    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _FakeRunner)
    monkeypatch.setattr(
        "decision_memory.cli.run_evaluation",
        lambda *args, **kwargs: _all_pass_outcome(),
    )
    result = _invoke_evaluate(corpus, tmp_path)

    assert result.exit_code == 0
    fixture_lines = [
        line for line in result.stdout.splitlines() if _FIXTURE_LINE.match(line)
    ]
    reported_ids = [
        match.group(2)
        for line in fixture_lines
        for match in [_FIXTURE_LINE.match(line)]
        if match is not None
    ]
    assert reported_ids == [fixture.id for fixture in EVALUATION_FIXTURES]
    assert all(line.startswith("PASS ") for line in fixture_lines)
    assert "result: 8 passed, 0 failed" in result.stdout
    assert "final: passed" in result.stdout


def test_evaluate_any_failure_exits_one_and_marks_final_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = make_corpus(tmp_path)
    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _FakeRunner)
    failing = EvaluationCheck(
        fixture_id="assertion-unverifiable-claim",
        status=False,
        detail="scripted failure",
    )
    outcome = EvaluationOutcome(checks=[failing], passed=0, failed=1, exit_code=1)
    monkeypatch.setattr(
        "decision_memory.cli.run_evaluation",
        lambda *args, **kwargs: outcome,
    )
    result = _invoke_evaluate(corpus, tmp_path)

    assert result.exit_code == 1
    assert "FAIL assertion-unverifiable-claim: scripted failure" in result.stdout
    assert "result: 0 passed, 1 failed" in result.stdout
    assert "final: failed" in result.stdout


def test_evaluate_runs_three_renders_per_fixture_rate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus = make_corpus(tmp_path)
    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _FakeRunner)
    checks = [
        EvaluationCheck(
            fixture_id="query-a",
            status=True,
            detail="3/3 runs passed",
            runs_passed=3,
            runs_total=3,
        ),
        EvaluationCheck(
            fixture_id="query-b",
            status=False,
            detail="2/3 runs passed",
            runs_passed=2,
            runs_total=3,
        ),
    ]
    outcome = EvaluationOutcome(checks=checks, passed=1, failed=1, exit_code=1)
    monkeypatch.setattr(
        "decision_memory.cli.run_evaluation",
        lambda *args, **kwargs: outcome,
    )
    result = _invoke_evaluate(corpus, tmp_path, "--runs", "3")

    assert result.exit_code == 1
    assert "PASS query-a (3/3 runs): 3/3 runs passed" in result.stdout
    assert "FAIL query-b (2/3 runs): 2/3 runs passed" in result.stdout
    assert "result: 1 passed, 1 failed" in result.stdout
    assert "final: failed" in result.stdout
