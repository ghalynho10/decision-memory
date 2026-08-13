"""Live integration test for the evaluation harness (feature 11, Slice 3).

Runs the full ``evaluate`` flow against the real JobPilot corpus with real
OpenAI providers: adapt, ingest a fresh store, run the fixed battery, and
confirm the report is legible and the exit code reflects the outcome. Marked
integration and skipped unless both ``OPENAI_API_KEY`` and
``DECISION_MEMORY_JOBPILOT_DIR`` are set, so the default suites never touch
the network (same contract as test_query_live.py).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from decision_memory.application.evaluation import (
    EVALUATION_FIXTURES,
    run_evaluation,
)
from decision_memory.infrastructure.evaluation_runner import EvaluationRunner

pytestmark = pytest.mark.integration

_REQUIRED = {"OPENAI_API_KEY", "DECISION_MEMORY_JOBPILOT_DIR"}


@pytest.mark.skipif(
    not _REQUIRED.issubset(os.environ),
    reason="requires OPENAI_API_KEY and DECISION_MEMORY_JOBPILOT_DIR",
)
def test_evaluate_runs_battery_against_real_jobpilot(tmp_path: Path) -> None:
    """The harness runs every fixture against the real corpus, legibly.

    Adapts JobPilot, ingests a fresh store, runs the five defining queries
    plus the two assertions, and returns an outcome whose checks cover every
    fixture in fixed order. Some fixtures are known live blockers carried
    from feature 10 (the query 4 fabrication and query 2 DM-0004 coverage
    omission), so the exit code may legitimately be 1; the harness's contract
    is legible pass or fail, not a guaranteed all green run.
    """
    corpus = Path(os.environ["DECISION_MEMORY_JOBPILOT_DIR"])
    records_dir = tmp_path / "records"
    store_dir = tmp_path / "store"
    runner = EvaluationRunner(corpus, records_dir, store_dir)

    adapt_outcome = runner.adapt()
    assert adapt_outcome.exit_code == 0, adapt_outcome

    ingest_result = runner.ingest(rebuild=True)
    assert ingest_result.exit_code == 0, ingest_result

    outcome = run_evaluation(EVALUATION_FIXTURES, runner, runs=1)
    assert len(outcome.checks) == len(EVALUATION_FIXTURES)
    assert [check.fixture_id for check in outcome.checks] == [
        fixture.id for fixture in EVALUATION_FIXTURES
    ]
    assert outcome.passed + outcome.failed == len(EVALUATION_FIXTURES)
    assert outcome.exit_code == (1 if outcome.failed else 0)

    # Every check has a legible detail; none is the empty string.
    for check in outcome.checks:
        assert check.detail, check.fixture_id

    # The rationale summary assertion (assertion A) is the durable new one:
    # it runs and reports a legible pass or fail, so the harness proves the
    # rationale_summary field survived parse through generate. The check
    # exists, has a boolean status, and a nonempty detail.
    rationale_check = next(
        check
        for check in outcome.checks
        if check.fixture_id == "assertion-rationale-summary"
    )
    assert isinstance(rationale_check.status, bool)
    assert rationale_check.detail
