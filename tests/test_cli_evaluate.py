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

import json
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
from decision_memory.infrastructure.index_lock import LockError
from decision_memory.infrastructure.store import write_active

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
        return SimpleNamespace(exit_code=0, failure=None)


def _all_pass_outcome() -> EvaluationOutcome:
    """Every battery fixture passes, in the fixed engine order."""
    checks = tuple(
        EvaluationCheck(fixture_id=fixture.id, status=True, detail="scripted")
        for fixture in EVALUATION_FIXTURES
    )
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


def test_evaluate_runs_too_high_is_a_usage_error(tmp_path: Path) -> None:
    """A typo like --runs 500 must not fire thousands of live queries."""
    corpus = make_corpus(tmp_path)
    result = runner.invoke(app, ["evaluate", str(corpus), "--runs", "21"])
    assert result.exit_code == 2
    assert "--runs must be at most 20" in result.stdout


def test_evaluate_runs_validated_before_the_missing_corpus_check(
    tmp_path: Path,
) -> None:
    """A usage error must win over a missing-corpus error, not lose to it."""
    result = runner.invoke(app, ["evaluate", str(tmp_path / "nope"), "--runs", "0"])
    assert result.exit_code == 2
    assert "--runs must be at least 1" in result.stdout


def test_evaluate_lock_conflict_during_the_battery_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A lock conflict mid battery must not crash with an unhandled traceback."""
    corpus = make_corpus(tmp_path)
    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _FakeRunner)

    def _raise_lock_error(*args: object, **kwargs: object) -> EvaluationOutcome:
        raise LockError("lock conflict")

    monkeypatch.setattr("decision_memory.cli.run_evaluation", _raise_lock_error)
    result = _invoke_evaluate(corpus, tmp_path)
    assert result.exit_code == 1
    assert "store is locked by another ingest or query" in result.stdout


def test_evaluate_warns_when_records_dir_is_not_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user supplied --records that already has content must not be silent."""
    corpus = make_corpus(tmp_path)
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    (records_dir / "stale.md").write_text("stale", encoding="utf-8")
    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _FakeRunner)
    monkeypatch.setattr(
        "decision_memory.cli.run_evaluation",
        lambda *args, **kwargs: _all_pass_outcome(),
    )
    result = _invoke_evaluate(corpus, tmp_path)
    assert result.exit_code == 0
    assert f"warning: {records_dir} is not empty" in result.stdout


def test_evaluate_warns_when_store_has_an_active_generation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A user supplied --store that already has an index must not be silent."""
    corpus = make_corpus(tmp_path)
    store_dir = tmp_path / "store"
    write_active(store_dir, "gen-1")
    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _FakeRunner)
    monkeypatch.setattr(
        "decision_memory.cli.run_evaluation",
        lambda *args, **kwargs: _all_pass_outcome(),
    )
    result = _invoke_evaluate(corpus, tmp_path)
    assert result.exit_code == 0
    assert f"warning: {store_dir} already has an active generation" in result.stdout


def test_evaluate_default_paths_are_labelled_temporary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Defaulted --records/--store are cleaned up on exit; the report says so."""
    corpus = make_corpus(tmp_path)
    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _FakeRunner)
    monkeypatch.setattr(
        "decision_memory.cli.run_evaluation",
        lambda *args, **kwargs: _all_pass_outcome(),
    )
    result = runner.invoke(app, ["evaluate", str(corpus)])
    assert result.exit_code == 0
    assert "(temporary, removed on exit)" in result.stdout
    assert "warning:" not in result.stdout


def test_evaluate_warns_when_configured_adapter_is_not_the_built_in_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A configured third party adapter must be visibly ignored, not silent.

    The battery's fixtures cite record ids from the built in adapter's
    corpus; evaluate never wires a configured adapter through, so a mismatch
    must be a loud warning rather than a confusing wrong-adapter run.
    """
    corpus = make_corpus(tmp_path)
    (tmp_path / ".decision-memory.yml").write_text(
        "adapter: vendor.runtime:adapter\n", encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _FakeRunner)
    monkeypatch.setattr(
        "decision_memory.cli.run_evaluation",
        lambda *args, **kwargs: _all_pass_outcome(),
    )
    result = _invoke_evaluate(corpus, tmp_path)
    assert result.exit_code == 0
    assert "warning: evaluate is calibrated to the built in adapter" in result.stdout
    assert "vendor.runtime:adapter" in result.stdout


def test_evaluate_missing_api_key_fails_loudly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    corpus = make_corpus(tmp_path)
    _write_one_spec(corpus)
    result = _invoke_evaluate(corpus, tmp_path)
    assert result.exit_code == 1
    assert "ingest failed: error planning provider.key: OPENAI_API_KEY is not set" in (
        result.stdout
    )
    assert "hint: set OPENAI_API_KEY to build the index" in result.stdout


def test_evaluate_other_ingest_failure_names_its_real_cause(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A non key ingest failure must not be misattributed to a missing key."""
    corpus = make_corpus(tmp_path)
    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _FakeRunner)
    failure = SimpleNamespace(stage="store", code="store.parity", detail="boom")
    monkeypatch.setattr(
        _FakeRunner,
        "ingest",
        lambda self, rebuild: SimpleNamespace(exit_code=1, failure=failure),
    )
    result = _invoke_evaluate(corpus, tmp_path)
    assert result.exit_code == 1
    assert "error store store.parity: boom" in result.stdout
    assert "OPENAI_API_KEY" not in result.stdout


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
    outcome = EvaluationOutcome(checks=(failing,), passed=0, failed=1, exit_code=1)
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
    checks = (
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
    )
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


# ---------------------------------------------------------------------------
# --battery: a fixture battery loaded from a manifest (spec 0010 AC-15)
# ---------------------------------------------------------------------------


def _battery_manifest(tmp_path: Path) -> Path:
    """A minimal well formed battery manifest in its own corpus directory."""
    fixture_root = tmp_path / "fixture"
    _write_one_spec(fixture_root)
    manifest = fixture_root / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "source_commit": "abc1234",
                "generated": "2026-08-13",
                "excluded_specs": ["0010-abstention-verification-reliability"],
                "files": [],
                "queries": [
                    {
                        "id": "decision",
                        "text": "What was decided?",
                        "expected_record": "DM-0012",
                        "expected_state": "answered",
                        "expected_value_paths": ["decision.chosen"],
                        "expected_abstention": None,
                    },
                    {
                        "id": "reason",
                        "text": "Why?",
                        "expected_record": None,
                        "expected_state": "abstained",
                        "expected_value_paths": [],
                        "expected_abstention": "uncovered_facet",
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    return manifest


class _BatteryRunner(_FakeRunner):
    """The fake runner plus the value paths the satisfiability check reads."""

    value_paths: dict[str, frozenset[str]] = {
        "DM-0012": frozenset({"decision.chosen", "rationale_summary"})
    }

    def record_value_paths(self) -> dict[str, frozenset[str]]:
        return dict(self.value_paths)


def test_battery_runs_the_manifest_fixtures_not_the_built_in_ones(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The manifest's queries become the battery, and its parent directory is
    the corpus root (spec 0010 AC-15)."""
    manifest = _battery_manifest(tmp_path)
    seen: dict[str, object] = {}

    def _capture(fixtures: object, port: object, runs: int = 1) -> EvaluationOutcome:
        seen["fixtures"] = fixtures
        seen["corpus_root"] = getattr(port, "corpus_root", None)
        checks = tuple(
            EvaluationCheck(fixture_id=fixture.id, status=True, detail="scripted")
            for fixture in fixtures  # type: ignore[attr-defined]
        )
        return EvaluationOutcome(
            checks=checks, passed=len(checks), failed=0, exit_code=0
        )

    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _BatteryRunner)
    monkeypatch.setattr("decision_memory.cli.run_evaluation", _capture)
    result = runner.invoke(app, ["evaluate", "--battery", str(manifest)])
    assert result.exit_code == 0, result.stdout
    assert [f.id for f in seen["fixtures"]] == ["decision", "reason"]  # type: ignore[union-attr]
    assert seen["corpus_root"] == manifest.parent
    assert "PASS decision" in result.stdout


def test_battery_with_an_explicit_corpus_argument_is_a_usage_error(
    tmp_path: Path,
) -> None:
    """A battery run against the wrong corpus adapts and ingests happily and
    then fails on record ids, which looks like a broken pipeline and is not
    one; the pair is refused instead."""
    manifest = _battery_manifest(tmp_path)
    result = runner.invoke(
        app, ["evaluate", str(tmp_path / "elsewhere"), "--battery", str(manifest)]
    )
    assert result.exit_code == 2
    assert "takes its corpus root from the manifest's parent directory" in result.stdout


def test_battery_manifest_error_is_a_usage_error(tmp_path: Path) -> None:
    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"queries": []}', encoding="utf-8")
    result = runner.invoke(app, ["evaluate", "--battery", str(manifest)])
    assert result.exit_code == 2
    assert "battery manifest error:" in result.stdout


def test_an_unsatisfiable_battery_oracle_stops_before_any_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A typo'd record id or a prefix no chunk carries would otherwise fail
    the gate forever with nothing to separate a broken pipeline from a wrong
    manifest (spec 0010 AC-15)."""
    manifest = _battery_manifest(tmp_path)

    class _WrongCorpus(_BatteryRunner):
        value_paths = {"DM-0012": frozenset({"rationale_summary"})}

    def _never(*args: object, **kwargs: object) -> EvaluationOutcome:
        raise AssertionError("no query may run once an oracle is unsatisfiable")

    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _WrongCorpus)
    monkeypatch.setattr("decision_memory.cli.run_evaluation", _never)
    result = runner.invoke(app, ["evaluate", "--battery", str(manifest)])
    assert result.exit_code == 2
    assert "unsatisfiable oracle: decision" in result.stdout
    assert "decision.chosen" in result.stdout


def test_the_built_in_battery_is_never_checked_for_satisfiability(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing the JobPilot battery runs through moves: its oracles are code,
    and turning one failing fixture into a whole run usage error would change
    what a live run reports."""
    corpus = make_corpus(tmp_path)
    monkeypatch.setattr("decision_memory.cli.EvaluationRunner", _FakeRunner)
    monkeypatch.setattr(
        "decision_memory.cli.run_evaluation",
        lambda *args, **kwargs: _all_pass_outcome(),
    )
    # _FakeRunner has no record_value_paths at all, so reaching the check
    # would raise AttributeError rather than pass quietly.
    result = _invoke_evaluate(corpus, tmp_path)
    assert result.exit_code == 0
