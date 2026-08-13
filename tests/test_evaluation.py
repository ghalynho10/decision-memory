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
    CoverageRow,
    DiversityTrace,
    Facet,
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
    AbstentionCause,
    EvaluationCheck,
    EvaluationFixture,
    EvaluationPort,
    FixtureKind,
    ProposedRecords,
    QueryOracle,
    ReingestEvidence,
    abstention_cause,
    classify_query4_failure,
    run_evaluation,
    unsatisfiable_oracles,
)
from decision_memory.application.query import NO_EMITTED_SENTENCE_REASON

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
        decomposed=(),
        empty_decompositions=(),
        missing_chunk_refs=(),
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


def _coverage_result(
    facets: tuple[Facet, ...],
    coverage: tuple[CoverageRow, ...],
    state: QueryState,
) -> QueryResult:
    """A query result carrying specific facets and coverage rows in its trace."""
    base = _empty_trace(state)
    trace = QueryTrace(
        freshness=base.freshness,
        retrieval=base.retrieval,
        generation=GenerationTrace(
            facets=facets,
            supersession_notices=(),
            draft_sentences=(),
            cited_chunk_ids=(),
        ),
        verification=VerificationTrace(
            containment=(),
            entailment=(),
            removed_sentences=(),
            coverage=coverage,
            uncovered_facets=tuple(
                facet
                for facet, row in zip(facets, coverage, strict=False)
                if not row.covered
            ),
            decomposed=(),
            empty_decompositions=(),
            rejected_decompositions=(),
            missing_chunk_refs=(),
        ),
        providers=(),
        result=base.result,
    )
    return QueryResult(
        schema_version=2,
        state=state,
        exit_code=0,
        sentences=(),
        citations=(),
        freshness=FreshnessState.CURRENT,
        abstention_stage=(
            AbstentionStage.CLAIM_VERIFICATION
            if state == QueryState.ABSTAINED
            else None
        ),
        trace=trace,
        failure=None,
    )


@dataclass
class FakePort(EvaluationPort):
    """A scripted evaluation port for the unit suite."""

    results: dict[str, QueryResult] | None = None
    proposed: frozenset[str] = frozenset()
    proposed_unparsed_count: int = 0
    reingest_evidence: ReingestEvidence | None = None
    calls: list[str] | None = None

    def run_query(self, question: str) -> QueryResult:
        if self.calls is not None:
            self.calls.append(question)
        if self.results is None:
            raise AssertionError(f"unexpected query: {question}")
        return self.results[question]

    def proposed_record_ids(self) -> ProposedRecords:
        return ProposedRecords(
            ids=self.proposed, unparsed_count=self.proposed_unparsed_count
        )

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


def test_cite_all_proposed_fails_when_some_records_could_not_be_parsed() -> None:
    """A partial shrink of the proposed set must fail loudly, not silently.

    The empty-set guard alone only catches total loss. If one proposed
    record among several silently fails to parse, the remaining ones can
    still all be cited, satisfying ``proposed - cited_ids`` on a set that
    was never complete in the first place.
    """
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(expected_state=QueryState.ANSWERED, cite_all_proposed=True),
    )
    port = FakePort(
        proposed=frozenset({"DM-0015"}),
        proposed_unparsed_count=1,
        results={
            "q": _result(
                QueryState.ANSWERED, (_citation("DM-0015", "decision.chosen"),)
            )
        },
    )
    outcome = run_evaluation((fixture,), port)
    assert outcome.failed == 1
    assert "could not be read" in outcome.checks[0].detail


def test_value_path_prefix_matched_against_proposed_set() -> None:
    """cite_all_proposed plus a prefix must not pass on an unrelated citation.

    No shipped fixture combines the two, but the co-location rule that
    closed this hole for required_record_ids must also hold when the record
    scope comes from the proposed set instead.
    """
    fixture = EvaluationFixture(
        id="f",
        kind=FixtureKind.QUERY,
        question="q",
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            cite_all_proposed=True,
            required_value_path_prefixes=("decision.chosen",),
        ),
    )
    port = FakePort(
        proposed=frozenset({"DM-0015"}),
        results={
            "q": _result(
                QueryState.ANSWERED,
                (
                    _citation("DM-0015", "why[0]"),
                    _citation("DM-0099", "decision.chosen"),
                ),
            )
        },
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


# ---------------------------------------------------------------------------
# Query 4 failure classification (spec 0010 AC-12)
# ---------------------------------------------------------------------------


_QUERY4_FACETS = (
    Facet(
        "F1",
        "What was decided about separating server side and browser side "
        "database clients?",
    ),
    Facet("F2", "Why were the database clients separated?"),
)


def test_classify_query4_merged_facet_reports_facet_extraction() -> None:
    merged = (
        Facet(
            "F1",
            "What was decided about separating server side and browser side "
            "database clients, and why?",
        ),
    )
    result = _coverage_result(merged, (), QueryState.ANSWERED)
    assert classify_query4_failure(result) == "facet_extraction"


def test_classify_query4_wrongly_covered_decision_reports_coverage_directness() -> None:
    coverage = (
        CoverageRow("F1", True, "a grounded reason", ("S1.1",)),
        CoverageRow("F2", True, "a reason", ("S1.1",)),
    )
    result = _coverage_result(_QUERY4_FACETS, coverage, QueryState.ANSWERED)
    assert classify_query4_failure(result) == "coverage_directness"


def test_classify_query4_uncovered_decision_answered_reports_query_state() -> None:
    coverage = (
        CoverageRow("F1", False, "no kept answer sentence", ()),
        CoverageRow("F2", True, "a reason", ("S1.1",)),
    )
    result = _coverage_result(_QUERY4_FACETS, coverage, QueryState.ANSWERED)
    assert classify_query4_failure(result) == "query_state"


def test_classify_query4_consistent_abstention_is_none() -> None:
    coverage = (
        CoverageRow("F1", False, "no kept answer sentence", ()),
        CoverageRow("F2", False, "no kept answer sentence", ()),
    )
    result = _coverage_result(_QUERY4_FACETS, coverage, QueryState.ABSTAINED)
    assert classify_query4_failure(result) is None


def test_classify_query4_failed_state_is_none() -> None:
    result = _coverage_result((), (), QueryState.FAILED)
    assert classify_query4_failure(result) is None


def test_query4_fixture_failure_detail_names_the_stage() -> None:
    """A failing query 4 fixture report names the diagnosed stage (AC-12)."""
    fixture = next(f for f in EVALUATION_FIXTURES if f.id == "query-4-db-clients")
    coverage = (
        CoverageRow("F1", True, "a grounded reason", ("S1.1",)),
        CoverageRow("F2", True, "a reason", ("S1.1",)),
    )
    result = _coverage_result(_QUERY4_FACETS, coverage, QueryState.ANSWERED)
    port = FakePort(results={fixture.question or "": result})
    outcome = run_evaluation((fixture,), port)
    assert outcome.failed == 1
    assert "query4 stage: coverage_directness" in outcome.checks[0].detail


# ---------------------------------------------------------------------------
# The manifest battery oracle: co located citations and a named abstention
# cause (spec 0010 AC-15)
# ---------------------------------------------------------------------------


def _cited(citation_id: str, record_id: str, value_path: str) -> Citation:
    """A citation with its own id, so a sentence can name a specific one."""
    return Citation(
        citation_id=citation_id,
        kind=CitationKind.CHUNK,
        evidence_id=f"evidence-{citation_id}",
        record_id=record_id,
        chunk_id=f"ch_{citation_id}",
        value_path=value_path,
        relative_path=f"docs/specs/{record_id}/index.md",
        section="Decision",
        resolution=ResolutionState.RESOLVED,
        freshness=CitationFreshness.CURRENT,
    )


def _answered_result(
    sentences: tuple[AnswerSentence, ...],
    citations: tuple[Citation, ...],
    coverage: tuple[CoverageRow, ...],
) -> QueryResult:
    """An answered result carrying sentences, citations, and coverage rows."""
    base = _empty_trace(QueryState.ANSWERED)
    trace = QueryTrace(
        freshness=base.freshness,
        retrieval=base.retrieval,
        generation=base.generation,
        verification=VerificationTrace(
            containment=(),
            entailment=(),
            removed_sentences=(),
            coverage=coverage,
            uncovered_facets=(),
        ),
        providers=(),
        result=base.result,
    )
    return QueryResult(
        schema_version=2,
        state=QueryState.ANSWERED,
        exit_code=0,
        sentences=sentences,
        citations=citations,
        freshness=FreshnessState.CURRENT,
        abstention_stage=None,
        trace=trace,
        failure=None,
    )


def _abstained_result(
    coverage: tuple[CoverageRow, ...],
    stage: AbstentionStage = AbstentionStage.CLAIM_VERIFICATION,
) -> QueryResult:
    """An abstained result at a chosen stage with chosen coverage rows."""
    base = _empty_trace(QueryState.ABSTAINED)
    trace = QueryTrace(
        freshness=base.freshness,
        retrieval=base.retrieval,
        generation=base.generation,
        verification=VerificationTrace(
            containment=(),
            entailment=(),
            removed_sentences=(),
            coverage=coverage,
            uncovered_facets=(),
        ),
        providers=(),
        result=ResultTrace(
            state=QueryState.ABSTAINED,
            abstention_stage=stage,
            citations=(),
            stale_markers=(),
        ),
    )
    return QueryResult(
        schema_version=2,
        state=QueryState.ABSTAINED,
        exit_code=0,
        sentences=(),
        citations=(),
        freshness=FreshnessState.CURRENT,
        abstention_stage=stage,
        trace=trace,
        failure=None,
    )


def _run_one(fixture: EvaluationFixture, result: QueryResult) -> EvaluationCheck:
    port = FakePort(results={fixture.question or "": result})
    return run_evaluation((fixture,), port).checks[0]


def _query_fixture(oracle: QueryOracle, question: str = "q") -> EvaluationFixture:
    return EvaluationFixture(
        id="manifest-query", kind=FixtureKind.QUERY, question=question, oracle=oracle
    )


def test_abstention_cause_reads_no_emitted_sentences_from_the_reason_constant() -> None:
    """Every coverage row carrying the deterministic reason means no sentence
    reached coverage at all (AC-15). The constant has one home in query.py so
    the reader and the writer cannot drift apart."""
    coverage = (
        CoverageRow("F1", False, NO_EMITTED_SENTENCE_REASON, ()),
        CoverageRow("F2", False, NO_EMITTED_SENTENCE_REASON, ()),
    )
    assert (
        abstention_cause(_abstained_result(coverage))
        == AbstentionCause.NO_EMITTED_SENTENCES
    )


def test_abstention_cause_reads_uncovered_facet_when_a_sentence_was_judged() -> None:
    coverage = (
        CoverageRow("F1", True, "states the decision", ("S1",)),
        CoverageRow("F2", False, "no sentence states why", ()),
    )
    assert (
        abstention_cause(_abstained_result(coverage)) == AbstentionCause.UNCOVERED_FACET
    )


def test_abstention_cause_is_unreadable_from_an_empty_coverage_tuple() -> None:
    """The guard that stops a vacuous pass (AC-15).

    A retrieval stage abstention carries an empty coverage tuple, and every
    row of an empty tuple satisfies any test, so without this guard a query
    that abstained before generation ever ran would report as the
    deterministic no sentence case and quietly satisfy the gate.
    """
    assert abstention_cause(_abstained_result((), AbstentionStage.RETRIEVAL)) is None
    assert (
        abstention_cause(_abstained_result((), AbstentionStage.CLAIM_VERIFICATION))
        is None
    )


def test_abstention_cause_is_none_for_a_non_abstained_result() -> None:
    assert abstention_cause(_answered_result((), (), ())) is None


def test_expected_cause_passes_only_when_the_cause_matches() -> None:
    fixture = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ABSTAINED,
            expected_abstention=AbstentionCause.UNCOVERED_FACET,
        )
    )
    uncovered = _abstained_result(
        (
            CoverageRow("F1", True, "states the decision", ("S1",)),
            CoverageRow("F2", False, "no sentence states why", ()),
        )
    )
    check = _run_one(fixture, uncovered)
    assert check.status
    assert "uncovered_facet" in check.detail

    collapsed = _abstained_result(
        (CoverageRow("F1", False, NO_EMITTED_SENTENCE_REASON, ()),)
    )
    check = _run_one(fixture, collapsed)
    assert not check.status
    assert "abstained from no_emitted_sentences" in check.detail


def test_expected_cause_fails_loudly_on_an_abstention_at_another_stage() -> None:
    """An abstention at retrieval is neither cause, and fails with the stage
    named rather than passing on a state only match (AC-15)."""
    fixture = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ABSTAINED,
            expected_abstention=AbstentionCause.NO_EMITTED_SENTENCES,
        )
    )
    check = _run_one(fixture, _abstained_result((), AbstentionStage.RETRIEVAL))
    assert not check.status
    assert "abstained at retrieval" in check.detail

    check = _run_one(fixture, _abstained_result((), AbstentionStage.CLAIM_VERIFICATION))
    assert not check.status
    assert "no coverage rows" in check.detail


def test_an_abstaining_oracle_without_a_cause_keeps_todays_behaviour() -> None:
    """Every JobPilot fixture leaves ``expected_abstention`` unset, so a state
    only abstention still passes and nothing already built moves."""
    fixture = _query_fixture(QueryOracle(expected_state=QueryState.ABSTAINED))
    check = _run_one(fixture, _abstained_result((), AbstentionStage.RETRIEVAL))
    assert check.status
    assert check.detail == "abstained as expected"


def test_an_answering_oracle_cannot_carry_an_abstention_cause() -> None:
    with pytest.raises(ValueError):
        QueryOracle(
            expected_state=QueryState.ANSWERED,
            expected_abstention=AbstentionCause.UNCOVERED_FACET,
        )


def test_covering_sentence_scope_rejects_a_caveat_from_the_right_record() -> None:
    """The failure this criterion exists to close (AC-15).

    Both sentences cite ``DM-0008``, and the answer carries a
    ``decision.chosen`` citation, so state plus record id plus a whole answer
    value path check all pass. Only the covering sentence narrowing sees that
    the sentence which covered the decision facet cites a caveat instead.
    """
    citations = (
        _cited("C1", "DM-0008", "decision.chosen"),
        _cited("C2", "DM-0008", "consequences.negative[0]"),
    )
    sentences = (
        AnswerSentence("S1", "The evidence does not establish a floor.", ("C2",)),
        AnswerSentence("S2", "Hybrid retrieval was chosen.", ("C1",)),
    )
    coverage = (CoverageRow("F1", True, "reads as the decision", ("S1",)),)
    result = _answered_result(sentences, citations, coverage)

    whole_answer = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0008"}),
            required_value_path_prefixes=("decision.chosen",),
        )
    )
    assert _run_one(whole_answer, result).status

    scoped = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0008"}),
            required_value_path_prefixes=("decision.chosen",),
            covering_sentence_scope=True,
        )
    )
    check = _run_one(scoped, result)
    assert not check.status
    assert "on the covering sentence" in check.detail


def test_covering_sentence_scope_passes_when_the_covering_sentence_cites_it() -> None:
    citations = (
        _cited("C1", "DM-0008", "decision.chosen"),
        _cited("C2", "DM-0008", "consequences.negative[0]"),
    )
    sentences = (
        AnswerSentence("S1", "The evidence does not establish a floor.", ("C2",)),
        AnswerSentence("S2", "Hybrid retrieval was chosen.", ("C1",)),
    )
    coverage = (CoverageRow("F1", True, "states the decision", ("S2",)),)
    scoped = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0008"}),
            required_value_path_prefixes=("decision.chosen",),
            covering_sentence_scope=True,
        )
    )
    assert _run_one(scoped, _answered_result(sentences, citations, coverage)).status


def test_covering_sentence_scope_keeps_the_record_scope_too() -> None:
    """A covering sentence citing the right value path on the wrong record
    does not satisfy the oracle; co location means both."""
    citations = (_cited("C1", "DM-0009", "decision.chosen"),)
    sentences = (AnswerSentence("S1", "Another record's decision.", ("C1",)),)
    coverage = (CoverageRow("F1", True, "states a decision", ("S1",)),)
    scoped = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0009"}),
            required_value_path_prefixes=("decision.chosen",),
            covering_sentence_scope=True,
        )
    )
    assert _run_one(scoped, _answered_result(sentences, citations, coverage)).status

    wrong_record = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0008"}),
            required_value_path_prefixes=("decision.chosen",),
            covering_sentence_scope=True,
        )
    )
    check = _run_one(wrong_record, _answered_result(sentences, citations, coverage))
    assert not check.status
    assert "DM-0008" in check.detail


def test_covering_sentence_scope_fails_when_no_covered_row_names_a_sentence() -> None:
    """Not measured, rather than silently satisfied: an answered result whose
    covered rows name no sentence with citations cannot be checked."""
    citations = (_cited("C1", "DM-0008", "decision.chosen"),)
    sentences = (AnswerSentence("S1", "Hybrid retrieval was chosen.", ("C1",)),)
    coverage = (CoverageRow("F1", False, "not covered", ()),)
    scoped = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0008"}),
            required_value_path_prefixes=("decision.chosen",),
            covering_sentence_scope=True,
        )
    )
    check = _run_one(scoped, _answered_result(sentences, citations, coverage))
    assert not check.status
    assert "no covered coverage row names a sentence" in check.detail


def test_the_jobpilot_battery_keeps_the_whole_answer_semantics() -> None:
    """Nothing already built moves: no built in fixture opts into either new
    field (AC-15)."""
    for fixture in EVALUATION_FIXTURES:
        if fixture.oracle is None:
            continue
        assert fixture.oracle.expected_abstention is None, fixture.id
        assert fixture.oracle.covering_sentence_scope is False, fixture.id


# ---------------------------------------------------------------------------
# Unsatisfiable oracles are reported before any query runs (spec 0010 AC-15)
# ---------------------------------------------------------------------------


def test_unsatisfiable_oracles_names_a_record_absent_from_the_corpus() -> None:
    fixture = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0099"}),
        )
    )
    problems = unsatisfiable_oracles(
        (fixture,), {"DM-0008": frozenset({"decision.chosen"})}
    )
    assert len(problems) == 1
    assert "DM-0099" in problems[0]


def test_unsatisfiable_oracles_names_a_prefix_no_chunk_carries() -> None:
    fixture = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0008"}),
            required_value_path_prefixes=("decision.chosen",),
        )
    )
    problems = unsatisfiable_oracles(
        (fixture,), {"DM-0008": frozenset({"rationale_summary"})}
    )
    assert len(problems) == 1
    assert "decision.chosen" in problems[0]


def test_a_satisfiable_battery_reports_nothing() -> None:
    fixture = _query_fixture(
        QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0008"}),
            required_value_path_prefixes=("decision.chosen",),
        )
    )
    abstaining = EvaluationFixture(
        id="reason",
        kind=FixtureKind.QUERY,
        question="why",
        oracle=QueryOracle(
            expected_state=QueryState.ABSTAINED,
            expected_abstention=AbstentionCause.UNCOVERED_FACET,
        ),
    )
    paths = {"DM-0008": frozenset({"decision.chosen", "decision.alternatives[0]"})}
    assert unsatisfiable_oracles((fixture, abstaining), paths) == ()
