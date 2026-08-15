"""Application: the evaluation harness engine (feature 11, Slice 3).

A fixed battery of correctness fixtures runs against the real corpus to prove
the pipeline end to end: the five defining queries with their known correct
sources, the two further assertions (a rationale summary only answer and an
incremental re ingest), and the claim level unverifiable fixture from spec
0001. The questions and oracles are already fully specified; this module
holds them as data and runs the checks.

The engine is pure application code in the conformance engine's style: it
holds the fixture value objects, the oracle comparison rules, and the
outcome, and receives every external concern (running a query, listing the
proposed records, running the re ingest assertion) as injected callables on a
narrow port. It imports no Typer, Pydantic, OpenAI, or Chroma (AC-18).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from decision_memory.application.dto import (
    AbstentionStage,
    Facet,
    QueryResult,
    QueryState,
    RetrievalFailure,
)
from decision_memory.application.query import NO_EMITTED_SENTENCE_REASON

# The five defining queries (mvp.md, specs 0007 and 0008) with their exact
# wording, and the two further assertions (mvp.md) plus the claim level
# unverifiable fixture (spec 0001 follow up).
QUERY_ONE = "Why was the private beta access gate added, and what was the alternative?"
QUERY_TWO = "What decisions affect resume generation?"
QUERY_THREE = "Which decisions are still provisional rather than ratified?"
QUERY_FOUR = (
    "What was decided about separating server side and browser side "
    "database clients, and why?"
)
QUERY_FIVE = "What changed the original approach to storing uploaded files?"

# Assertion A target: the answer can only come from DM-0006's rationale
# summary. The why list of DM-0006 covers error logging and country
# detection, not the client side refetch versus polling decision, so an
# answered query that cites a rationale_summary chunk proves the field
# survived parse, chunk, embed, retrieve, and generate.
ASSERTION_RATIONALE_QUESTION = (
    "Why does the Adzuna job discovery feature refetch data client side "
    "instead of using a background polling job?"
)

# Spec 0001 fixture: a question whose correct answer needs a specific fact no
# adapted record states, so any confident answer would be a fabricated claim
# the verification step must catch. The honest outcome is abstention.
ASSERTION_UNVERIFIABLE_QUESTION = (
    "What is the exact dollar cost of a single Adzuna API search request?"
)


class FixtureKind(StrEnum):
    """The two fixture kinds the engine knows how to run."""

    QUERY = "query"
    REINGEST = "reingest"


class AbstentionCause(StrEnum):
    """Why a claim verification abstention happened (spec 0010 AC-15).

    ``UNCOVERED_FACET`` means at least one sentence was emitted and at least
    one facet still came back uncovered: the abstention the gates are named
    for. ``NO_EMITTED_SENTENCES`` means no sentence reached coverage at all,
    so the deterministic uncovered rows applied; the query abstained because
    the pipeline produced nothing, which satisfies an ``abstained`` state
    while proving nothing about abstention.
    """

    UNCOVERED_FACET = "uncovered_facet"
    NO_EMITTED_SENTENCES = "no_emitted_sentences"


@dataclass(frozen=True)
class QueryOracle:
    """What a query fixture's result must satisfy to pass.

    ``expected_state`` is answered or abstained. For answered results,
    ``required_record_ids`` must all be cited, and each
    ``required_value_path_prefixes`` entry must match at least one citation
    belonging to a required record (or to the proposed set, when
    ``cite_all_proposed`` is set and no record ids are otherwise required);
    a prefix matched only by an unrelated citation does not satisfy the
    oracle. ``cite_all_proposed`` (query 3) additionally requires every
    proposed record to be cited; the proposed set is resolved through the
    port so the oracle tracks the corpus instead of a hardcoded id.

    Two optional fields carry the spec 0010 AC-15 strengthening, and both
    default to today's behaviour so the JobPilot battery is untouched:

    - ``expected_abstention`` names the cause an abstaining fixture expects.
      It applies only when ``expected_state`` is abstained; ``None`` means no
      constraint, which is what every JobPilot fixture keeps.
    - ``covering_sentence_scope`` narrows value path matching to citations
      belonging to a sentence that a covered coverage row names. Record scope
      alone cannot tell a decision from a caveat drawn from the same record
      once more than one sentence is emitted.
    """

    expected_state: QueryState
    required_record_ids: frozenset[str] = frozenset()
    required_value_path_prefixes: tuple[str, ...] = ()
    cite_all_proposed: bool = False
    expected_abstention: AbstentionCause | None = None
    covering_sentence_scope: bool = False

    def __post_init__(self) -> None:
        """Refuse an abstention cause on an answering oracle.

        An answered result has no abstention cause to read, so the constraint
        could only ever be silently ignored, which is the exact class of
        quietly weakened expectation AC-15 exists to close. The manifest
        loader reports the same thing with a manifest shaped message before
        this ever fires; this is the library level backstop.
        """
        if (
            self.expected_abstention is not None
            and self.expected_state != QueryState.ABSTAINED
        ):
            raise ValueError("expected_abstention applies only to an abstained oracle")


@dataclass(frozen=True)
class EvaluationFixture:
    """One fixture in the battery.

    A query fixture carries ``question`` and ``oracle``. A re ingest fixture
    carries ``reingest_record_id`` and the corpus relative path of the
    ``rationale.md`` to edit. ``classify_failure`` optionally names a
    callable that reads a failing result's existing trace and returns a
    short stage diagnosis appended to the failure detail (the query 4 live
    gate uses it, spec 0010 AC-12).
    """

    id: str
    kind: FixtureKind
    question: str | None = None
    oracle: QueryOracle | None = None
    reingest_record_id: str | None = None
    reingest_rationale_relpath: str | None = None
    classify_failure: Callable[[QueryResult], str | None] | None = None

    def __post_init__(self) -> None:
        """Enforce the per kind required fields at construction time.

        A plain ``raise`` here, not ``assert``: an assert would vanish under
        ``python -O`` and let a malformed fixture reach the runner, where the
        ``question``/``oracle`` or ``reingest_*`` fields being ``None`` would
        surface as a much less legible failure deep in the engine.
        """
        if self.kind == FixtureKind.QUERY:
            if self.question is None or self.oracle is None:
                raise ValueError(
                    f"query fixture {self.id!r} needs both question and oracle"
                )
        else:
            if (
                self.reingest_record_id is None
                or self.reingest_rationale_relpath is None
            ):
                raise ValueError(
                    f"reingest fixture {self.id!r} needs both reingest_record_id "
                    "and reingest_rationale_relpath"
                )


@dataclass(frozen=True)
class ReingestEvidence:
    """The outcome of one incremental re ingest assertion."""

    chunks_changed: bool
    detail: str


@dataclass(frozen=True)
class ProposedRecords:
    """Every proposed record id, plus how many record files could not be read.

    ``unparsed_count`` being nonzero means ``ids`` may be smaller than the
    corpus actually has: a parse failure or a missing id drops a record from
    the set silently rather than raising (see
    ``EvaluationRunner.proposed_record_ids``), so the oracle must treat a
    nonzero count as "this set cannot be trusted", not "nothing more to find".
    """

    ids: frozenset[str] = frozenset()
    unparsed_count: int = 0


@dataclass(frozen=True)
class EvaluationCheck:
    """One executed fixture row, for the report."""

    fixture_id: str
    status: bool
    detail: str
    runs_passed: int = 1
    runs_total: int = 1


@dataclass(frozen=True)
class EvaluationOutcome:
    """The full result of an evaluation run, plus the exit code."""

    checks: tuple[EvaluationCheck, ...] = ()
    passed: int = 0
    failed: int = 0
    exit_code: int = 0


class EvaluationPort(Protocol):
    """The narrow external concerns the engine needs.

    ``run_query`` executes one live query and returns its full traced result.
    ``proposed_record_ids`` returns every record id whose canonical status is
    proposed, plus how many record files it could not read, so query 3's
    oracle derives from the records themselves and can tell a complete set
    from an incomplete one. ``run_reingest`` runs the edit, re adapt, re
    ingest, compare flow and reports whether the target record's chunks
    changed.
    """

    def run_query(self, question: str) -> QueryResult: ...
    def proposed_record_ids(self) -> ProposedRecords: ...
    def run_reingest(
        self, record_id: str, rationale_relpath: str
    ) -> ReingestEvidence: ...

    def record_deviation(
        self, fixture_id: str, run_index: int, result: QueryResult
    ) -> None:
        """Keep the full traced result of a run that missed its expectation.

        Optional, and a no op by default (spec 0010 AC-23), so a port that
        has nowhere to put a trace is unaffected. ``EvaluationCheck`` keeps
        four scalar fields, so a surprising run was previously unattributable
        the moment the command returned: experiment 0013's single answering
        run of query 5 cannot be recovered by any amount of re running.

        The engine calls this only when a run's own oracle result is false,
        which is the same boolean the rate already counts, so no second
        notion of deviation exists. It is the seam for the write, because
        ``_run_query_fixture`` is pure application code and this project
        forbids the application layer from touching the filesystem. An
        implementation must not re derive the pass or fail itself; two
        implementations of one oracle can disagree, which AC-20 refused for
        ``classify_decomposition``.
        """
        return None


def abstention_cause(result: QueryResult) -> AbstentionCause | None:
    """Why this result abstained, read from the existing trace (AC-15).

    No new trace field: the cause is the coverage rows the query already
    records. It is read **only** from a claim verification abstention whose
    coverage tuple is nonempty, and ``None`` means the cause cannot be read
    from this result at all, never "neither applies, so pass".

    That guard is not a formality. A retrieval stage abstention carries an
    empty coverage tuple, and every row of an empty tuple satisfies any test,
    so without it a query that abstained before generation ever ran would
    report as the deterministic no sentence case and quietly satisfy a gate.
    """
    if result.state != QueryState.ABSTAINED:
        return None
    if result.abstention_stage != AbstentionStage.CLAIM_VERIFICATION:
        return None
    coverage = result.trace.verification.coverage
    if not coverage:
        return None
    if all(row.reason == NO_EMITTED_SENTENCE_REASON for row in coverage):
        return AbstentionCause.NO_EMITTED_SENTENCES
    return AbstentionCause.UNCOVERED_FACET


def unsatisfiable_oracles(
    fixtures: Sequence[EvaluationFixture],
    record_value_paths: Mapping[str, frozenset[str]],
) -> tuple[str, ...]:
    """Every expectation the corpus cannot satisfy, before any query runs.

    ``record_value_paths`` maps each adapted record id to the value paths its
    active chunks carry. Checked once after adapt and ingest: every
    ``required_record_ids`` entry must exist in that map, and every
    ``required_value_path_prefixes`` entry must be a prefix of some value
    path on a record the oracle scopes it to.

    A typo'd record id or a prefix no chunk carries would otherwise fail its
    gate forever with nothing to separate a broken pipeline from a wrong
    manifest. Returns the messages rather than raising, so the pure engine
    stays free of an error type and the caller decides how loud to be.
    """
    problems: list[str] = []
    for fixture in fixtures:
        if fixture.kind != FixtureKind.QUERY or fixture.oracle is None:
            continue
        oracle = fixture.oracle
        missing = sorted(oracle.required_record_ids - set(record_value_paths))
        for record_id in missing:
            problems.append(
                f"{fixture.id}: expected record {record_id} is not in the "
                "adapted record set"
            )
        scope = oracle.required_record_ids - frozenset(missing)
        for prefix in oracle.required_value_path_prefixes:
            if not scope:
                continue
            carried = any(
                any(path.startswith(prefix) for path in record_value_paths[record_id])
                for record_id in scope
            )
            if not carried:
                problems.append(
                    f"{fixture.id}: no chunk of "
                    f"{', '.join(sorted(scope))} carries value path prefix "
                    f"{prefix}"
                )
    return tuple(problems)


def _facet_is_reason(facet: Facet) -> bool:
    """Whether a facet asks why, the reason side of query 4 (AC-12).

    A decision facet ("what was decided ...") is not a reason facet. A
    merged facet that folds the why into the question counts as reason, so
    "no non-reason facet exists" detects the merged shape.
    """
    text = facet.text.casefold()
    return "why" in text or "reason" in text


def classify_query4_failure(result: QueryResult) -> str | None:
    """Classify a failing query 4 gate from the existing trace (AC-12).

    Reads GenerationTrace.facets, the coverage rows, and the result state in
    order, using no new trace field. Returns None when the trace is
    consistent (separate decision and reason facets, the decision facet
    uncovered, the query abstained), or one closed disposition:
    ``facet_extraction`` (no separate decision and reason facets),
    ``coverage_directness`` (separate facets but the decision facet was
    wrongly covered), or ``query_state`` (separate facets, the decision
    facet uncovered, yet the result answered). A failed result is none of
    these stages and returns None.
    """
    if result.state == QueryState.FAILED:
        return None
    facets = result.trace.generation.facets
    decision_facets = [facet for facet in facets if not _facet_is_reason(facet)]
    reason_facets = [facet for facet in facets if _facet_is_reason(facet)]
    if not decision_facets or not reason_facets:
        return "facet_extraction"
    decision_id = decision_facets[0].facet_id
    decision_row = next(
        (
            row
            for row in result.trace.verification.coverage
            if row.facet_id == decision_id
        ),
        None,
    )
    if decision_row is not None and decision_row.covered:
        return "coverage_directness"
    if result.state == QueryState.ANSWERED:
        return "query_state"
    return None


# The fixed battery: the five defining queries, the rationale summary
# assertion, the unverifiable claim fixture, and the incremental re ingest
# assertion, in report order.
EVALUATION_FIXTURES: tuple[EvaluationFixture, ...] = (
    EvaluationFixture(
        id="query-1-private-beta-gate",
        kind=FixtureKind.QUERY,
        question=QUERY_ONE,
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0012"}),
            required_value_path_prefixes=("decision.alternatives[",),
        ),
    ),
    EvaluationFixture(
        id="query-2-resume-generation",
        kind=FixtureKind.QUERY,
        question=QUERY_TWO,
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0004", "DM-0019"}),
        ),
    ),
    EvaluationFixture(
        id="query-3-provisional",
        kind=FixtureKind.QUERY,
        question=QUERY_THREE,
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            cite_all_proposed=True,
        ),
    ),
    EvaluationFixture(
        id="query-4-db-clients",
        kind=FixtureKind.QUERY,
        question=QUERY_FOUR,
        # AC-23 pins the cause on both abstention gates: an abstention that
        # happened only because every sentence was dropped stops satisfying
        # them. Both are expected to fail on cause today, and that is the
        # finding rather than a regression. Nothing has ever established that
        # this fixture's 6 of 6 rests on a verdict rather than on the
        # wholesale rejection experiment 0013 found underneath query 5, and
        # examining one and not the other would be choosing which answer to
        # learn.
        oracle=QueryOracle(
            expected_state=QueryState.ABSTAINED,
            expected_abstention=AbstentionCause.UNCOVERED_FACET,
        ),
        classify_failure=classify_query4_failure,
    ),
    EvaluationFixture(
        id="query-5-uploaded-files",
        kind=FixtureKind.QUERY,
        question=QUERY_FIVE,
        oracle=QueryOracle(
            expected_state=QueryState.ABSTAINED,
            expected_abstention=AbstentionCause.UNCOVERED_FACET,
        ),
    ),
    EvaluationFixture(
        id="assertion-rationale-summary",
        kind=FixtureKind.QUERY,
        question=ASSERTION_RATIONALE_QUESTION,
        oracle=QueryOracle(
            expected_state=QueryState.ANSWERED,
            required_record_ids=frozenset({"DM-0006"}),
            required_value_path_prefixes=("rationale_summary",),
        ),
    ),
    EvaluationFixture(
        id="assertion-unverifiable-claim",
        kind=FixtureKind.QUERY,
        question=ASSERTION_UNVERIFIABLE_QUESTION,
        oracle=QueryOracle(expected_state=QueryState.ABSTAINED),
    ),
    EvaluationFixture(
        id="assertion-incremental-reingest",
        kind=FixtureKind.REINGEST,
        reingest_record_id="DM-0006",
        reingest_rationale_relpath=(
            "docs/specs/0006-adzuna-job-discovery/rationale.md"
        ),
    ),
)


def run_evaluation(
    fixtures: Sequence[EvaluationFixture],
    port: EvaluationPort,
    runs: int = 1,
) -> EvaluationOutcome:
    """Run every fixture and aggregate the legible pass or fail outcome.

    Each query fixture runs ``runs`` times so the harness measures the rate
    across runs rather than assuming consecutive passes hold (spec 0008
    Follow up 9). A query fixture passes only when every run passes; the
    check detail reports the observed rate. The re ingest assertion runs once.

    ``runs`` must be at least 1: the CLI already rejects 0 as a usage error,
    but a direct library caller passing 0 would otherwise get a vacuous
    all-pass outcome (``passed == runs`` is ``0 == 0``), the worst possible
    default for a correctness harness.
    """
    if runs < 1:
        raise ValueError("runs must be at least 1")
    checks: list[EvaluationCheck] = []
    passed = 0
    failed = 0
    proposed = (
        port.proposed_record_ids()
        if _needs_proposed_records(fixtures)
        else ProposedRecords()
    )
    for fixture in fixtures:
        if fixture.kind == FixtureKind.QUERY:
            check = _run_query_fixture(fixture, port, proposed, runs)
        else:
            check = _run_reingest_fixture(fixture, port)
        checks.append(check)
        if check.status:
            passed += 1
        else:
            failed += 1
    return EvaluationOutcome(
        checks=tuple(checks),
        passed=passed,
        failed=failed,
        exit_code=1 if failed else 0,
    )


def _needs_proposed_records(fixtures: Sequence[EvaluationFixture]) -> bool:
    """Whether any fixture's oracle needs the proposed record set.

    ``proposed_record_ids`` walks the whole records directory; skip the call
    entirely when no fixture sets ``cite_all_proposed``, so every port
    implementation isn't forced to support it for a battery that never asks.
    """
    return any(
        fixture.kind == FixtureKind.QUERY
        and fixture.oracle is not None
        and fixture.oracle.cite_all_proposed
        for fixture in fixtures
    )


def _run_query_fixture(
    fixture: EvaluationFixture,
    port: EvaluationPort,
    proposed: ProposedRecords,
    runs: int,
) -> EvaluationCheck:
    assert fixture.question is not None and fixture.oracle is not None
    passed = 0
    single_run_detail = ""
    first_failing_detail = ""
    for run_index in range(1, runs + 1):
        try:
            result = port.run_query(fixture.question)
        except RetrievalFailure as failure:
            # No QueryResult exists on this path, so there is no traced
            # result to hand the port; the retrieval stage is already named
            # in the detail below.
            ok, detail = (
                False,
                f"retrieval integrity failure at {failure.stage.value}",
            )
        else:
            ok, detail = _satisfies(result, fixture.oracle, proposed)
            if not ok and fixture.classify_failure is not None:
                stage = fixture.classify_failure(result)
                if stage:
                    detail = f"{detail}; query4 stage: {stage}"
            if not ok:
                # Only the deviating runs, so a clean batch costs nothing and
                # the run this exists for is never the one that goes missing
                # (AC-23).
                port.record_deviation(fixture.id, run_index, result)
        if ok:
            passed += 1
        elif not first_failing_detail:
            # The first non-passing run's detail, not the last run's: under
            # --runs N a fixture can fail on an early run and pass on a
            # later one, and reporting the later (passing) run's detail on a
            # row marked FAIL is self contradictory and discards the reason.
            first_failing_detail = detail
        single_run_detail = detail
    status = passed == runs
    if runs == 1:
        detail = single_run_detail
    else:
        detail = f"{passed}/{runs} runs passed"
        if not status and first_failing_detail:
            detail = f"{detail}; {first_failing_detail}"
    return EvaluationCheck(
        fixture_id=fixture.id,
        status=status,
        detail=detail,
        runs_passed=passed,
        runs_total=runs,
    )


def _run_reingest_fixture(
    fixture: EvaluationFixture, port: EvaluationPort
) -> EvaluationCheck:
    assert fixture.reingest_record_id is not None
    assert fixture.reingest_rationale_relpath is not None
    evidence = port.run_reingest(
        fixture.reingest_record_id, fixture.reingest_rationale_relpath
    )
    return EvaluationCheck(
        fixture_id=fixture.id,
        status=evidence.chunks_changed,
        detail=evidence.detail,
    )


def _satisfies_abstention_cause(
    result: QueryResult, expected: AbstentionCause
) -> tuple[bool, str]:
    """Whether an abstention happened for the cause its oracle names (AC-15).

    An abstention at any stage other than claim verification, or one whose
    coverage tuple is empty, is neither cause: it fails with that state
    named, rather than being reported as the deterministic no sentence case
    on a vacuously satisfied test.
    """
    cause = abstention_cause(result)
    if cause is None:
        stage = (
            result.abstention_stage.value
            if result.abstention_stage is not None
            else "unknown"
        )
        if result.abstention_stage != AbstentionStage.CLAIM_VERIFICATION:
            return (
                False,
                f"abstained at {stage}, which is neither abstention cause; "
                f"expected {expected.value}",
            )
        return (
            False,
            "abstained at claim_verification with no coverage rows, so the "
            f"cause cannot be read; expected {expected.value}",
        )
    if cause != expected:
        return (
            False,
            f"abstained from {cause.value}, expected {expected.value}",
        )
    return True, f"abstained as expected from {cause.value}"


def _covering_citation_ids(result: QueryResult) -> frozenset[str]:
    """Citation ids belonging to a sentence a covered coverage row names.

    The AC-15 covering sentence scope. An answered result's covered rows name
    the sentences that did the covering, and each answer sentence carries the
    citation ids it cites, so the two compose without a new trace field.
    """
    covering_sentences = {
        sentence_id
        for row in result.trace.verification.coverage
        if row.covered
        for sentence_id in row.sentence_ids
    }
    return frozenset(
        citation_id
        for sentence in result.sentences
        if sentence.sentence_id in covering_sentences
        for citation_id in sentence.citation_ids
    )


def _satisfies(
    result: QueryResult, oracle: QueryOracle, proposed: ProposedRecords
) -> tuple[bool, str]:
    """Whether one query result satisfies its oracle, with a legible reason."""
    if oracle.expected_state == QueryState.ABSTAINED:
        if (
            result.state == QueryState.ABSTAINED
            and not result.sentences
            and not result.citations
        ):
            if oracle.expected_abstention is None:
                return True, "abstained as expected"
            return _satisfies_abstention_cause(result, oracle.expected_abstention)
        cited = ", ".join(sorted({c.record_id for c in result.citations}))
        return (
            False,
            "expected abstained, got "
            f"{result.state.value} (citations: {cited or 'none'})",
        )

    if result.state != QueryState.ANSWERED:
        return (
            False,
            f"expected answered, got {result.state.value}",
        )
    cited_ids = {c.record_id for c in result.citations}
    if oracle.cite_all_proposed:
        if proposed.unparsed_count:
            # Not every proposed record could be read, so the set may be
            # smaller than the corpus actually has; a shrunken set can look
            # satisfied on evidence that proves nothing about the records
            # that silently dropped out. Fail loudly rather than checking
            # against a set that might already be incomplete.
            return (
                False,
                f"{proposed.unparsed_count} record file(s) could not be read "
                "while resolving the proposed set; it may be incomplete",
            )
        if not proposed.ids:
            # An empty proposed set is not "nothing to check", it is the
            # oracle's own input having gone missing (a parse regression, an
            # adapter change, or a corpus with no proposed records at all);
            # proposed.ids - cited_ids would otherwise be vacuously satisfied
            # by any answer at all, the same false-positive shape the
            # re-ingest oracle had before it required a non-empty ``after``.
            return (
                False,
                "cite_all_proposed is set but no proposed records were found; "
                "the oracle has nothing to verify against",
            )
        missing_proposed = sorted(proposed.ids - cited_ids)
        if missing_proposed:
            return (
                False,
                "did not cite every proposed record; missing "
                f"{', '.join(missing_proposed)}",
            )
    missing_required = sorted(oracle.required_record_ids - cited_ids)
    if missing_required:
        return (
            False,
            f"missing required records {', '.join(missing_required)} from citations",
        )
    # The set of records a value path prefix must belong to: the explicit
    # required_record_ids when set, else the proposed set when
    # cite_all_proposed is set (so a fixture combining the two, though none
    # ships in the battery today, can't pass on an unrelated record's
    # prefix), else no scope at all (a prefix with neither is matched by any
    # citation, today's only such fixture).
    record_scope = oracle.required_record_ids or (
        proposed.ids if oracle.cite_all_proposed else frozenset()
    )
    # The manifest battery narrows the same rule to the sentence that did the
    # covering (AC-15): a caveat and the decision it caveats can be drawn
    # from the same record, so record scope alone passes an answer whose
    # covering sentence never cites the decision. The JobPilot battery leaves
    # this off and keeps the whole answer semantics unchanged.
    candidates = result.citations
    if oracle.required_value_path_prefixes and oracle.covering_sentence_scope:
        covering_citation_ids = _covering_citation_ids(result)
        if not covering_citation_ids:
            return (
                False,
                "no covered coverage row names a sentence with citations, so "
                "no value path prefix can be checked against the covering "
                "sentence",
            )
        candidates = tuple(
            citation
            for citation in result.citations
            if citation.citation_id in covering_citation_ids
        )
    for prefix in oracle.required_value_path_prefixes:
        # When a record scope applies, the prefix must be matched by one of
        # THOSE records' citations, not merely by some citation somewhere in
        # the answer: otherwise a result that cites the right record for its
        # required_record_ids and an unrelated record for its value path
        # would satisfy both checks without proving what the fixture is
        # actually named for (e.g. assertion-rationale-summary proving
        # DM-0006's own rationale_summary reached the answer, not some other
        # record's).
        if record_scope:
            matched = any(
                c.value_path.startswith(prefix) and c.record_id in record_scope
                for c in candidates
            )
        else:
            matched = any(c.value_path.startswith(prefix) for c in candidates)
        if not matched:
            scope_note = (
                " on the covering sentence" if oracle.covering_sentence_scope else ""
            )
            return (
                False,
                "no required record's citation carries value path prefix "
                f"{prefix}{scope_note}",
            )
    return True, "answered with required citations"
