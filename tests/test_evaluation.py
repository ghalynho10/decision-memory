"""Unit tests for the evaluation harness engine (feature 11).

The engine is pure application code, so these tests drive it with a fake
``EvaluationPort`` that returns scripted query results and re ingest evidence.
No provider, store, or filesystem is involved. The fixture battery, oracle
comparison, run rate, and exit code contract are locked here.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from decision_memory.application.dto import (
    AbstentionStage,
    AnswerSentence,
    Citation,
    CitationFreshness,
    CitationKind,
    DiversityTrace,
    FilterTrace,
    FreshnessState,
    FreshnessTrace,
    FusionTrace,
    GenerationTrace,
    LexicalTrace,
    PartialQueryTrace,
    QueryResult,
    QueryState,
    QueryTrace,
    ResolutionState,
    ResultTrace,
    RetrievalFailure,
    RetrievalSettings,
    RetrievalStage,
    RetrievalTrace,
    SemanticTrace,
    VerificationTrace,
)
from decision_memory.application.evaluation import (
    EVALUATION_FIXTURES,
    EvaluationFixture,
    EvaluationPort,
    FixtureKind,
    QueryOracle,
    ReingestEvidence,
    run_evaluation,
)

# ---------------------------------------------------------------------------
# A minimal but valid QueryResult, with empty traces so the engine can read it
# ---------------------------------------------------------------------------


def _empty_trace(state: QueryState) -> QueryTrace:
    freshness = FreshnessTrace(
        state=FreshnessState.CURRENT,
        stored_pipeline_signature="sig",
        running_pipeline_signature="sig",
        records_manifest_path=None,
        manifest_available=True,
        start_semantic_digest=None,
        end_semantic_digest=None,
        start_raw_digest=None,
        end_raw_digest=None,
        fingerprints=(),
        stale_reasons=(),
    )
    retrieval = RetrievalTrace(
        filters=FilterTrace(rows=()),
        lexical=LexicalTrace(rows=()),
        semantic=SemanticTrace(rows=()),
        fusion=FusionTrace(candidates=()),
        diversity=DiversityTrace(accepted_chunk_ids=(), accepted_limit=8, record_cap=2),
        settings=RetrievalSettings(
            tokenizer_version="v1",
            stopword_set="v1",
            stopword_digest="d",
            bm25_variant="BM25Okapi",
            bm25_parameters="k1=1.5,b=0.75",
            lexical_limit=24,
            semantic_limit=24,
            rrf_constant=60,
            accepted_limit=8,
            diversity_cap=2,
            collection_metric="cosine",
            relevance_floor=None,
        ),
    )
    generation = GenerationTrace(
        facets=(),
        supersession_notices=(),
        draft_sentences=(),
        cited_chunk_ids=(),
    )
    verification = VerificationTrace(
        containment=(),
        entailment=(),
        removed_sentences=(),
        coverage=(),
        uncovered_facets=(),
    )
    return QueryTrace(
        freshness=freshness,
        retrieval=retrieval,
        generation=generation,
        verification=verification,
        providers=(),
        result=ResultTrace(
            state=state,
            abstention_stage=(
                AbstentionStage.RETRIEVAL if state == QueryState.ABSTAINED else None
            ),
            citations=(),
            stale_markers=(),
        ),
    )


def _citation(record_id: str, value_path: str) -> Citation:
    return Citation(
        citation_id="C1",
        kind=CitationKind.CHUNK,
        evidence_id=f"evidence-{record_id}",
        record_id=record_id,
        chunk_id=f"ch_{record_id}",
        value_path=value_path,
        relative_path=f"docs/specs/{record_id}/index.md",
        section="Rationale",
        resolution=ResolutionState.RESOLVED,
        freshness=CitationFreshness.CURRENT,
    )


def _sentence(text: str, *citation_ids: str) -> AnswerSentence:
    return AnswerSentence(sentence_id="S1", text=text, citation_ids=citation_ids)


def _result(
    state: QueryState,
    citations: tuple[Citation, ...] = (),
    sentences: tuple[AnswerSentence, ...] = (),
) -> QueryResult:
    return QueryResult(
        schema_version=2,
        state=state,
        exit_code=0,
        sentences=sentences,
        citations=citations,
        freshness=FreshnessState.CURRENT,
        abstention_stage=(
            AbstentionStage.RETRIEVAL if state == QueryState.ABSTAINED else None
        ),
        trace=_empty_trace(state),
        failure=None,
    )


@dataclass
class FakePort(EvaluationPort):
    """A scripted evaluation port for the unit suite."""

    results: dict[str, QueryResult] | None = None
    proposed: frozenset[str] = frozenset()
    reingest_evidence: ReingestEvidence | None = None
    calls: list[str] | None = None

    def run_query(self, question: str) -> QueryResult:
        if self.calls is not None:
            self.calls.append(question)
        if self.results is None:
            raise AssertionError(f"unexpected query: {question}")
        return self.results[question]

    def proposed_record_ids(self) -> frozenset[str]:
        return self.proposed

    def run_reingest(self, record_id: str, rationale_relpath: str) -> ReingestEvidence:
        if self.reingest_evidence is None:
            raise AssertionError("unexpected re-ingest call")
        return self.reingest_evidence


# ---------------------------------------------------------------------------
# Fixture battery sanity
# ---------------------------------------------------------------------------


def test_battery_has_eight_fixtures_in_fixed_order() -> None:
    assert len(EVALUATION_FIXTURES) == 8
    ids = [fixture.id for fixture in EVALUATION_FIXTURES]
    assert ids == [
        "query-1-private-beta-gate",
        "query-2-resume-generation",
        "query-3-provisional",
        "query-4-db-clients",
        "query-5-uploaded-files",
        "assertion-rationale-summary",
        "assertion-unverifiable-claim",
        "assertion-incremental-reingest",
    ]
    # Query fixtures carry a question and an oracle; the re-ingest fixture
    # carries its target record and rationale path.
    for fixture in EVALUATION_FIXTURES:
        if fixture.kind == FixtureKind.QUERY:
            assert fixture.question
            assert fixture.oracle is not None
        else:
            assert fixture.reingest_record_id
            assert fixture.reingest_rationale_relpath


def test_query_fixture_needs_question_and_oracle() -> None:
    with pytest.raises(ValueError, match="question and oracle"):
        EvaluationFixture(id="f", kind=FixtureKind.QUERY)


def test_reingest_fixture_needs_record_id_and_rationale_path() -> None:
    with pytest.raises(ValueError, match="reingest_record_id"):
        EvaluationFixture(id="f", kind=FixtureKind.REINGEST)


def test_run_evaluation_rejects_zero_runs() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(expected_state=QueryState.ABSTAINED),
    )
    with pytest.raises(ValueError, match="runs must be at least 1"):
        run_evaluation((fixture,), FakePort(), runs=0)


# ---------------------------------------------------------------------------
# Oracle comparison: answered fixtures
# ---------------------------------------------------------------------------


def test_answered_fixture_passes_when_required_record_cited() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0012"}),
        ),
    )
    port = FakePort(
        results={"q": _result(QueryState.ANSWERED, (_citation("DM-0012", "why[0]"),))}
    )
    outcome = run_evaluation((fixture,), port)
    assert outcome.passed == 1
    assert outcome.failed == 0
    assert outcome.exit_code == 0
    assert outcome.checks[0].status is True


def test_answered_fixture_fails_when_required_record_missing() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0012", "DM-0019"}),
        ),
    )
    port = FakePort(
        results={"q": _result(QueryState.ANSWERED, (_citation("DM-0012", "why[0]"),))}
    )
    outcome = run_evaluation((fixture,), port)
    assert outcome.passed == 0
    assert outcome.failed == 1
    assert outcome.exit_code == 1
    assert "DM-0019" in outcome.checks[0].detail


def test_answered_fixture_fails_when_value_path_prefix_missing() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0012"}),
            required_value_path_prefixes=("decision.alternatives[",),
        ),
    )
    port = FakePort(
        results={
            "q": _result(
                QueryState.ANSWERED,
                (_citation("DM-0012", "why[0]"),),
            )
        }
    )
    outcome = run_evaluation((fixture,), port)
    assert outcome.failed == 1
    assert "decision.alternatives[" in outcome.checks[0].detail


def test_answered_fixture_requires_proposed_records() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            cite_all_proposed=True,
        ),
    )
    # Only DM-0015 is proposed; the answer must cite it.
    port = FakePort(
        proposed=frozenset({"DM-0015"}),
        results={
            "q": _result(
                QueryState.ANSWERED,
                (_citation("DM-0015", "decision.chosen"),),
            )
        },
    )
    outcome = run_evaluation((fixture,), port)
    assert outcome.passed == 1

    # A missing proposed record fails the fixture.
    port2 = FakePort(
        proposed=frozenset({"DM-0015"}),
        results={
            "q": _result(
                QueryState.ANSWERED,
                (_citation("DM-0001", "decision.chosen"),),
            )
        },
    )
    outcome2 = run_evaluation((fixture,), port2)
    assert outcome2.failed == 1
    assert "DM-0015" in outcome2.checks[0].detail


def test_cite_all_proposed_fails_when_proposed_set_is_empty() -> None:
    """An empty proposed set must not vacuously pass.

    ``proposed - cited_ids`` is empty whenever ``proposed`` is empty, no
    matter what was cited; an empty set usually means the oracle's own input
    went missing (a parse regression, an adapter change), not that there is
    nothing left to check.
    """
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(expected_state=QueryState.ANSWERED, cite_all_proposed=True),
    )
    port = FakePort(
        proposed=frozenset(),
        results={"q": _result(QueryState.ANSWERED, (_citation("DM-0001", "why[0]"),))},
    )
    outcome = run_evaluation((fixture,), port)
    assert outcome.failed == 1
    assert "no proposed records were found" in outcome.checks[0].detail


def test_value_path_prefix_must_belong_to_a_required_record() -> None:
    """A prefix match on an unrelated citation must not satisfy the oracle.

    required_record_ids and required_value_path_prefixes used to be checked
    independently, so a citation for the required record plus a citation for
    an entirely different record carrying the required prefix would pass —
    proving only that both things appeared somewhere in the answer, not that
    the required record's own field reached it.
    """
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0006"}),
            required_value_path_prefixes=("rationale_summary",),
        ),
    )
    port = FakePort(
        results={
            "q": _result(
                QueryState.ANSWERED,
                (
                    _citation("DM-0006", "why[0]"),
                    _citation("DM-0099", "rationale_summary"),
                ),
            )
        }
    )
    outcome = run_evaluation((fixture,), port)
    assert outcome.failed == 1
    assert (
        "no required record's citation carries value path prefix"
        in outcome.checks[0].detail
    )


def test_failed_state_fails_an_answered_fixture() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(expected_state=QueryState.ANSWERED),
    )
    port = FakePort(results={"q": _result(QueryState.FAILED)})
    outcome = run_evaluation((fixture,), port)
    assert outcome.failed == 1
    assert "expected answered" in outcome.checks[0].detail


# ---------------------------------------------------------------------------
# Oracle comparison: abstained fixtures
# ---------------------------------------------------------------------------


def test_abstained_fixture_passes_when_abstained() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(expected_state=QueryState.ABSTAINED),
    )
    port = FakePort(results={"q": _result(QueryState.ABSTAINED)})
    outcome = run_evaluation((fixture,), port)
    assert outcome.passed == 1
    assert outcome.checks[0].detail == "abstained as expected"


def test_abstained_fixture_fails_when_answered() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(expected_state=QueryState.ABSTAINED),
    )
    port = FakePort(
        results={
            "q": _result(
                QueryState.ANSWERED,
                (_citation("DM-0007", "why[0]"),),
                (_sentence("fabricated", "C1"),),
            )
        }
    )
    outcome = run_evaluation((fixture,), port)
    assert outcome.failed == 1
    assert "expected abstained" in outcome.checks[0].detail
    assert "DM-0007" in outcome.checks[0].detail


# ---------------------------------------------------------------------------
# Re-ingest assertion
# ---------------------------------------------------------------------------


def test_reingest_assertion_passes_when_chunks_changed() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.REINGEST,
        reingest_record_id="DM-0006",
        reingest_rationale_relpath="docs/specs/0006/rationale.md",
    )
    port = FakePort(reingest_evidence=ReingestEvidence(True, "chunks changed 3 -> 5"))
    outcome = run_evaluation((fixture,), port)
    assert outcome.passed == 1
    assert outcome.checks[0].detail == "chunks changed 3 -> 5"


def test_reingest_assertion_fails_when_chunks_unchanged() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.REINGEST,
        reingest_record_id="DM-0006",
        reingest_rationale_relpath="docs/specs/0006/rationale.md",
    )
    port = FakePort(reingest_evidence=ReingestEvidence(False, "chunks did not change"))
    outcome = run_evaluation((fixture,), port)
    assert outcome.failed == 1
    assert outcome.checks[0].status is False


# ---------------------------------------------------------------------------
# Run rate and the full outcome contract
# ---------------------------------------------------------------------------


def test_runs_measures_rate_across_repeated_queries() -> None:
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0012"}),
        ),
    )
    good = _result(QueryState.ANSWERED, (_citation("DM-0012", "why[0]"),))
    bad = _result(QueryState.ANSWERED, (_citation("DM-0001", "why[0]"),))
    port = FakePort(
        results={"q": good},
    )
    outcome = run_evaluation((fixture,), port, runs=3)
    assert outcome.passed == 1
    assert outcome.checks[0].runs_passed == 3
    assert outcome.checks[0].runs_total == 3

    # One failing run among three fails the fixture but records the rate.
    queue: list[QueryResult] = [good, bad, good]

    class FlakyPort(FakePort):
        def run_query(self, question: str) -> QueryResult:
            return queue.pop(0)

    outcome2 = run_evaluation((fixture,), FlakyPort(), runs=3)
    assert outcome2.failed == 1
    assert outcome2.checks[0].runs_passed == 2
    assert outcome2.checks[0].runs_total == 3
    assert "2/3 runs passed" in outcome2.checks[0].detail
    # The failing run is the middle one (index 1); the detail must name why
    # that run failed, not repeat the last (passing) run's detail on a row
    # marked FAIL.
    assert "missing required records DM-0012" in outcome2.checks[0].detail
    assert "answered with required citations" not in outcome2.checks[0].detail


def test_retrieval_failure_becomes_a_failed_fixture_not_a_crash() -> None:
    """A RetrievalFailure must not abort the whole battery.

    ``query_index`` raises RetrievalFailure rather than returning it as a
    QueryResult (AC-9); the engine must catch it at the port boundary so one
    integrity failure produces a legible FAIL row instead of an unhandled
    exception that discards every fixture already run.
    """
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(expected_state=QueryState.ANSWERED),
    )
    partial_trace = PartialQueryTrace(
        freshness=_empty_trace(QueryState.ANSWERED).freshness,
        filters=None,
        lexical=None,
        semantic=None,
        fusion=None,
        diversity=None,
        providers=(),
    )

    class FailingPort(FakePort):
        def run_query(self, question: str) -> QueryResult:
            raise RetrievalFailure(RetrievalStage.SEMANTIC, partial_trace)

    outcome = run_evaluation((fixture,), FailingPort())
    assert outcome.passed == 0
    assert outcome.failed == 1
    assert outcome.exit_code == 1
    assert "retrieval integrity failure at semantic" in outcome.checks[0].detail


def test_full_battery_exit_code_zero_only_when_all_pass() -> None:
    answered_good: dict[str, QueryResult] = {}
    for fixture in EVALUATION_FIXTURES:
        if fixture.kind == FixtureKind.QUERY:
            if fixture.oracle and fixture.oracle.expected_state == QueryState.ANSWERED:
                if fixture.oracle.cite_all_proposed:
                    record_ids = ["DM-0015"]
                else:
                    record_ids = sorted(
                        fixture.oracle.required_record_ids or {"DM-0001"}
                    )
                prefix = (
                    next(iter(fixture.oracle.required_value_path_prefixes))
                    if fixture.oracle.required_value_path_prefixes
                    else "why[0]"
                )
                answered_good[fixture.question or ""] = _result(
                    QueryState.ANSWERED,
                    tuple(_citation(record_id, prefix) for record_id in record_ids),
                )
            else:
                answered_good[fixture.question or ""] = _result(QueryState.ABSTAINED)
    port = FakePort(
        proposed=frozenset({"DM-0015"}),
        results=answered_good,
        reingest_evidence=ReingestEvidence(True, "chunks changed"),
    )
    outcome = run_evaluation(EVALUATION_FIXTURES, port)
    assert outcome.passed == len(EVALUATION_FIXTURES)
    assert outcome.failed == 0
    assert outcome.exit_code == 0
