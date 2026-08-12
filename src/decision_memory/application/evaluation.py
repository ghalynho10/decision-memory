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

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from decision_memory.application.dto import QueryResult, QueryState, RetrievalFailure

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


@dataclass(frozen=True)
class QueryOracle:
    """What a query fixture's result must satisfy to pass.

    ``expected_state`` is answered or abstained. For answered results,
    ``required_record_ids`` must all be cited, and each
    ``required_value_path_prefixes`` entry must match at least one citation.
    ``cite_all_proposed`` (query 3) additionally requires every proposed
    record to be cited; the proposed set is resolved through the port so the
    oracle tracks the corpus instead of a hardcoded id.
    """

    expected_state: QueryState
    required_record_ids: frozenset[str] = frozenset()
    required_value_path_prefixes: tuple[str, ...] = ()
    cite_all_proposed: bool = False


@dataclass(frozen=True)
class EvaluationFixture:
    """One fixture in the battery.

    A query fixture carries ``question`` and ``oracle``. A re ingest fixture
    carries ``reingest_record_id`` and the corpus relative path of the
    ``rationale.md`` to edit.
    """

    id: str
    kind: FixtureKind
    question: str | None = None
    oracle: QueryOracle | None = None
    reingest_record_id: str | None = None
    reingest_rationale_relpath: str | None = None

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
    proposed, so query 3's oracle derives from the records themselves.
    ``run_reingest`` runs the edit, re adapt, re ingest, compare flow and
    reports whether the target record's chunks changed.
    """

    def run_query(self, question: str) -> QueryResult: ...
    def proposed_record_ids(self) -> frozenset[str]: ...
    def run_reingest(
        self, record_id: str, rationale_relpath: str
    ) -> ReingestEvidence: ...


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
        oracle=QueryOracle(expected_state=QueryState.ABSTAINED),
    ),
    EvaluationFixture(
        id="query-5-uploaded-files",
        kind=FixtureKind.QUERY,
        question=QUERY_FIVE,
        oracle=QueryOracle(expected_state=QueryState.ABSTAINED),
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
        port.proposed_record_ids() if _needs_proposed_records(fixtures) else frozenset()
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
    proposed: frozenset[str],
    runs: int,
) -> EvaluationCheck:
    assert fixture.question is not None and fixture.oracle is not None
    passed = 0
    single_run_detail = ""
    first_failing_detail = ""
    for _ in range(runs):
        try:
            result = port.run_query(fixture.question)
        except RetrievalFailure as failure:
            ok, detail = (
                False,
                f"retrieval integrity failure at {failure.stage.value}",
            )
        else:
            ok, detail = _satisfies(result, fixture.oracle, proposed)
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


def _satisfies(
    result: QueryResult, oracle: QueryOracle, proposed: frozenset[str]
) -> tuple[bool, str]:
    """Whether one query result satisfies its oracle, with a legible reason."""
    if oracle.expected_state == QueryState.ABSTAINED:
        if (
            result.state == QueryState.ABSTAINED
            and not result.sentences
            and not result.citations
        ):
            return True, "abstained as expected"
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
        if not proposed:
            # An empty proposed set is not "nothing to check", it is the
            # oracle's own input having gone missing (a parse regression, an
            # adapter change, or a corpus with no proposed records at all);
            # cited_ids - proposed would otherwise be vacuously satisfied by
            # any answer at all, the same false-positive shape the re-ingest
            # oracle had before it required a non-empty ``after``.
            return (
                False,
                "cite_all_proposed is set but no proposed records were found; "
                "the oracle has nothing to verify against",
            )
        missing = sorted(proposed - cited_ids)
        if missing:
            return (
                False,
                f"did not cite every proposed record; missing {', '.join(missing)}",
            )
    missing = sorted(oracle.required_record_ids - cited_ids)
    if missing:
        return (
            False,
            f"missing required records {', '.join(missing)} from citations",
        )
    for prefix in oracle.required_value_path_prefixes:
        # When specific records are required, the prefix must be matched by
        # one of THOSE records' citations, not merely by some citation
        # somewhere in the answer: otherwise a result that cites the right
        # record for its required_record_ids and an unrelated record for its
        # value path would satisfy both checks without proving what the
        # fixture is actually named for (e.g. assertion-rationale-summary
        # proving DM-0006's own rationale_summary reached the answer, not
        # some other record's).
        if oracle.required_record_ids:
            matched = any(
                c.value_path.startswith(prefix)
                and c.record_id in oracle.required_record_ids
                for c in result.citations
            )
        else:
            matched = any(c.value_path.startswith(prefix) for c in result.citations)
        if not matched:
            return (
                False,
                f"no required record's citation carries value path prefix {prefix}",
            )
    return True, "answered with required citations"
