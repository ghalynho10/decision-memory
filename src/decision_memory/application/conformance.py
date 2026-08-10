"""Application: the adapter conformance engine (spec 0006).

One engine runs a battery of checks against any ``SourceAdapter`` and a
declarative manifest of cases. The engine is pure application code: it holds
the plain manifest and outcome value objects, a narrow fixture workspace port,
and the deterministic check flow from the spec's emission matrix.

Manifest file loading and the human report live in infrastructure and the CLI,
so this module imports only the standard library and the application and
domain types it already depends on. In particular it imports no Typer,
Pydantic, PyYAML, pytest, ``tempfile``, or ``shutil`` (AC-18): every
filesystem operation goes through the injected ``ConformanceFixturePort``.
"""

from __future__ import annotations

import dataclasses
import inspect
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from decision_memory.application.adapter import (
    AdaptationResult,
    DiscoveredSpec,
    DiscoveryResult,
    SourceAdapter,
)
from decision_memory.application.canonical import (
    SourceReference,
    normalize_field_sources,
)
from decision_memory.domain.records import CanonicalDecisionRecord, Severity, Violation


class ConformanceCategory(StrEnum):
    """The five fixed manifest categories (spec 0006 AC-3)."""

    VALID = "valid"
    SKIP = "skip"
    WRONG_HEADING = "wrong_heading"
    MISSING_REQUIRED_FIELD = "missing_required_field"
    COLLISION = "collision"


class Variant(StrEnum):
    """Report coordinates naming the workspace copy being checked."""

    ORIGINAL = "original"
    FINGERPRINT_PROBE = "fingerprint_probe"
    EMPTY = "empty"
    INVALID_UTF8 = "invalid_utf8"


class MutationKind(StrEnum):
    """The one suite mutation applied to a generated workspace copy."""

    EMPTY = "empty"
    INVALID_UTF8 = "invalid_utf8"
    FINGERPRINT_PROBE = "fingerprint_probe"


class EntryKind(StrEnum):
    """A snapshot entry kind."""

    FILE = "file"
    DIRECTORY = "directory"


# ---------------------------------------------------------------------------
# Declarative manifest value objects (loaded by infrastructure, never edited)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ViolationExpectation:
    """One expected violation: severity, stable rule, and canonical field."""

    severity: Severity
    rule: str
    field: str


@dataclass(frozen=True)
class FieldSourceExpectation:
    """One expected source location for a canonical value."""

    path: str
    section: str


@dataclass(frozen=True)
class ResultExpectation:
    """The complete expected parse result for one source.

    ``field_sources`` is optional: when None the comparison skips provenance
    checking; when set it must match the adapter's exact field_sources map,
    so a conformance case can lock the new schema version 2 contract (spec
    0007 AC-2).
    """

    record: CanonicalDecisionRecord | None
    attempted_fields: frozenset[str]
    unresolved_mention_count: int
    violations: tuple[ViolationExpectation, ...]
    field_sources: dict[str, tuple[FieldSourceExpectation, ...]] | None = None


@dataclass(frozen=True)
class SourceExpectation:
    """One expected discovered source."""

    id: str
    root: Path
    contributing_files: tuple[Path, ...]
    required_files: tuple[Path, ...]
    result: ResultExpectation


@dataclass(frozen=True)
class SkipExpectation:
    """One expected skip, matched by exact path."""

    path: Path


@dataclass(frozen=True)
class CollisionExpectation:
    """One expected id collision and the path the adapter selected."""

    id: str
    paths: tuple[Path, ...]
    used: Path


@dataclass(frozen=True)
class DiscoveryExpectation:
    """The complete expected discovery result for one case."""

    sources: tuple[SourceExpectation, ...]
    skips: tuple[SkipExpectation, ...]
    collisions: tuple[CollisionExpectation, ...]


@dataclass(frozen=True)
class ConformanceCase:
    """One isolated case: a copied corpus and its expected behavior."""

    id: str
    category: ConformanceCategory
    corpus: Path
    subject_path: Path | None
    target_fields: frozenset[str]
    expect: DiscoveryExpectation


@dataclass(frozen=True)
class ConformanceManifest:
    """The validated declarative manifest, resolved to plain application data."""

    schema_version: int
    cases: tuple[ConformanceCase, ...]


# ---------------------------------------------------------------------------
# Fixture workspace value objects and the port
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SnapshotEntry:
    """One entry in a corpus snapshot, ordered by relative POSIX path."""

    path: Path
    kind: EntryKind
    permissions: int
    content: bytes | None


@dataclass(frozen=True)
class CorpusSnapshot:
    """A full before or after picture of a copied corpus."""

    entries: tuple[SnapshotEntry, ...]


@dataclass(frozen=True)
class Workspace:
    """One isolated case or generated variant copy, with its baseline."""

    root: Path
    variant: Variant
    mutation_path: Path | None = None
    mutation_kind: MutationKind | None = None
    baseline: CorpusSnapshot | None = None


@dataclass(frozen=True)
class FixtureFailure:
    """A typed infrastructure failure returned through the fixture port."""

    operation: str
    exception_type: str
    message: str
    last_known_path: Path | None = None


class ConformanceFixturePort(Protocol):
    """The narrow filesystem port the engine needs (AC-18).

    Every operation returns a typed failure instead of raising, so the engine
    can emit ``fixture.*`` checks and continue. The application never touches
    the filesystem itself.
    """

    def open_case(self, case_id: str, corpus: Path) -> Workspace | FixtureFailure: ...
    def open_variant(
        self,
        case_id: str,
        corpus: Path,
        target: Path,
        mutation: MutationKind,
    ) -> Workspace | FixtureFailure: ...
    def snapshot(self, root: Path) -> CorpusSnapshot | FixtureFailure: ...
    def preserve(self, root: Path) -> Path | FixtureFailure: ...
    def cleanup(self, workspace: Workspace) -> None | FixtureFailure: ...


# ---------------------------------------------------------------------------
# Report value objects and the outcome
# ---------------------------------------------------------------------------


@dataclass
class CheckResult:
    """One executed check row.

    Not frozen so the engine can attach the preserved artifact path to the
    first failed check of a workspace after preservation succeeds.
    """

    rule: str
    status: bool
    detail: str = ""
    case_id: str | None = None
    source_id: str | None = None
    path: Path | None = None
    operation: str | None = None
    variant: Variant | None = None
    artifact_path: Path | None = None


@dataclass(frozen=True)
class ConformanceOutcome:
    """The full result of a conformance run, plus the exit code (AC-16)."""

    adapter_id: str
    adapter_version: str
    checks: list[CheckResult]
    passed: int
    failed: int
    exit_code: int


# ---------------------------------------------------------------------------
# Comparison helpers (spec 0006 AC-4, AC-5)
# ---------------------------------------------------------------------------

SourceShape = tuple[str, str, tuple[str, ...]]
SkipShape = tuple[str, ...]
CollisionShape = tuple[str, tuple[str, ...], str]
DiscoveryShape = tuple[tuple[SourceShape, ...], SkipShape, tuple[CollisionShape, ...]]
FieldSourceShape = dict[str, tuple[tuple[str, str], ...]]
AdaptationShape = tuple[
    CanonicalDecisionRecord | None,
    frozenset[str],
    int,
    tuple[tuple[str, str, str], ...],
    str,
    FieldSourceShape,
]


def _rel_or_raw(root: Path, path: Path) -> str:
    """A path as a corpus relative POSIX string, or the raw path when outside."""
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _source_shape(spec: DiscoveredSpec) -> SourceShape:
    root = _rel_or_raw(spec.corpus_root, spec.root)
    files = tuple(_rel_or_raw(spec.corpus_root, p) for p in spec.contributing_files)
    return (spec.id, root, files)


def _discovery_shape(result: DiscoveryResult, corpus_root: Path) -> DiscoveryShape:
    sources = tuple(_source_shape(spec) for spec in result.specs)
    skips = tuple(_rel_or_raw(corpus_root, s.path) for s in result.skipped)
    collisions = tuple(
        (
            c.id,
            tuple(_rel_or_raw(corpus_root, p) for p in c.paths),
            _rel_or_raw(corpus_root, c.used),
        )
        for c in result.collisions
    )
    return (sources, skips, collisions)


def _expected_shape(expect: DiscoveryExpectation) -> DiscoveryShape:
    sources = tuple(
        (
            s.id,
            s.root.as_posix(),
            tuple(p.as_posix() for p in s.contributing_files),
        )
        for s in expect.sources
    )
    skips = tuple(s.path.as_posix() for s in expect.skips)
    collisions = tuple(
        (
            c.id,
            tuple(p.as_posix() for p in c.paths),
            c.used.as_posix(),
        )
        for c in expect.collisions
    )
    return (sources, skips, collisions)


def _discovery_difference(
    result: DiscoveryResult, corpus_root: Path, expect: DiscoveryExpectation
) -> str | None:
    """A concise message naming the first discovery mismatch, else None."""
    actual = _discovery_shape(result, corpus_root)
    expected = _expected_shape(expect)
    if actual[0] != expected[0]:
        return "discovered sources differ from the expectation"
    if actual[1] != expected[1]:
        return "skipped paths differ from the expectation"
    if any(not skip.reason.strip() for skip in result.skipped):
        return "a skip has an empty reason"
    if actual[2] != expected[2]:
        return "collisions differ from the expectation"
    return None


def _violation_triple(violation: Violation) -> tuple[str, str, str]:
    return (violation.severity.value, violation.rule, violation.field)


def _field_sources_shape(
    field_sources: dict[str, list[SourceReference]],
) -> FieldSourceShape:
    return {
        path: tuple((ref.path, ref.section) for ref in refs)
        for path, refs in normalize_field_sources(field_sources).items()
    }


def _adaptation_shape(result: AdaptationResult) -> AdaptationShape:
    return (
        result.record,
        frozenset(result.attempted_fields),
        result.unresolved_mention_count,
        tuple(_violation_triple(v) for v in result.violations),
        result.fingerprint,
        _field_sources_shape(result.field_sources),
    )


def _record_difference(
    actual: CanonicalDecisionRecord | None,
    expected: CanonicalDecisionRecord | None,
) -> str:
    if actual is None or expected is None:
        return "record presence differs"
    for entry in dataclasses.fields(actual):
        actual_value = getattr(actual, entry.name)
        expected_value = getattr(expected, entry.name)
        if actual_value != expected_value:
            if expected_value is None and actual_value is not None:
                return f"unexpected field {entry.name}"
            return f"field {entry.name} differs"
    return "records differ"


def _result_difference(
    actual: AdaptationResult, expected: ResultExpectation
) -> str | None:
    """A concise message naming the first result mismatch, else None."""
    if actual.record != expected.record:
        return _record_difference(actual.record, expected.record)
    if set(actual.attempted_fields) != set(expected.attempted_fields):
        return "attempted fields differ"
    if actual.unresolved_mention_count != expected.unresolved_mention_count:
        return "unresolved mention count differs"
    actual_triples = tuple(_violation_triple(v) for v in actual.violations)
    expected_triples = tuple(
        (v.severity.value, v.rule, v.field) for v in expected.violations
    )
    if actual_triples != expected_triples:
        return "violations differ"
    if expected.field_sources is not None:
        expected_shape: FieldSourceShape = {
            path: tuple((ref.path, ref.section) for ref in refs)
            for path, refs in expected.field_sources.items()
        }
        if _field_sources_shape(actual.field_sources) != expected_shape:
            return "field sources differ"
    return None


def _is_confident(result: AdaptationResult) -> bool:
    """Confident output: a record with no error severity violation (AC-7)."""
    if result.record is None:
        return False
    return not any(v.severity == Severity.ERROR for v in result.violations)


def _path_problems(result: DiscoveryResult, root: Path) -> list[str]:
    """AC-11 path and identity invariants for one discovery result."""
    problems: list[str] = []
    seen: set[str] = set()
    for spec in result.specs:
        if not spec.id.strip():
            problems.append("a source has an empty id")
        elif spec.id in seen:
            problems.append(f"duplicate source id {spec.id!r}")
        seen.add(spec.id)
        if spec.corpus_root != root:
            problems.append(f"{spec.id}: corpus_root is not the copied case root")
        if not _is_inside(spec.root, root) or not spec.root.exists():
            problems.append(f"{spec.id}: root is missing or outside the corpus")
        if not spec.contributing_files:
            problems.append(f"{spec.id}: no contributing files")
        else:
            for contrib in spec.contributing_files:
                if not _is_inside(contrib, root) or not contrib.exists():
                    problems.append(
                        f"{spec.id}: contributing file {contrib} "
                        "is missing or outside the corpus"
                    )
    return problems


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _coord_variant(variant: Variant) -> Variant | None:
    """The original workspace prints no variant coordinate (normative example)."""
    return None if variant == Variant.ORIGINAL else variant


def _failure_detail(failure: FixtureFailure) -> str:
    return f"{failure.operation} {failure.exception_type}: {failure.message}"


# ---------------------------------------------------------------------------
# The engine
# ---------------------------------------------------------------------------


@dataclass
class _Collector:
    checks: list[CheckResult] = field(default_factory=list)
    passed: int = 0
    failed: int = 0

    def pass_check(
        self,
        rule: str,
        *,
        case_id: str | None = None,
        source_id: str | None = None,
        path: Path | None = None,
        operation: str | None = None,
        variant: Variant | None = None,
    ) -> CheckResult:
        check = CheckResult(
            rule=rule,
            status=True,
            case_id=case_id,
            source_id=source_id,
            path=path,
            operation=operation,
            variant=variant,
        )
        self.checks.append(check)
        self.passed += 1
        return check

    def fail_check(
        self,
        rule: str,
        detail: str,
        *,
        case_id: str | None = None,
        source_id: str | None = None,
        path: Path | None = None,
        operation: str | None = None,
        variant: Variant | None = None,
    ) -> CheckResult:
        check = CheckResult(
            rule=rule,
            status=False,
            detail=detail,
            case_id=case_id,
            source_id=source_id,
            path=path,
            operation=operation,
            variant=variant,
        )
        self.checks.append(check)
        self.failed += 1
        return check


@dataclass
class _Session:
    """One workspace's run state: the copy, its case, and its failures."""

    workspace: Workspace
    case_id: str
    variant: Variant
    failed: list[CheckResult] = field(default_factory=list)


class _Engine:
    def __init__(
        self,
        adapter: SourceAdapter,
        manifest: ConformanceManifest,
        fixtures: ConformanceFixturePort,
    ) -> None:
        self.adapter = adapter
        self.manifest = manifest
        self.fixtures = fixtures
        self.collector = _Collector()
        self.adapter_id = ""
        self.adapter_version = ""
        self.signatures_ok = True
        self._baseline: dict[str, str] = {}

    def run(self) -> ConformanceOutcome:
        self._contract_checks()
        if self.signatures_ok:
            for case in self.manifest.cases:
                self._run_case(case)
        return ConformanceOutcome(
            adapter_id=self.adapter_id,
            adapter_version=self.adapter_version,
            checks=self.collector.checks,
            passed=self.collector.passed,
            failed=self.collector.failed,
            exit_code=1 if self.collector.failed else 0,
        )

    # -- contract phase ----------------------------------------------------

    def _contract_checks(self) -> None:
        try:
            adapter_id = self.adapter.adapter_id
            adapter_version = self.adapter.adapter_version
        except Exception as exc:  # noqa: BLE001 - adapter property failure (AC-9)
            self.collector.fail_check(
                "contract.metadata", f"metadata access raised {type(exc).__name__}"
            )
            self.signatures_ok = False
            return
        self.adapter_id = adapter_id if isinstance(adapter_id, str) else ""
        self.adapter_version = (
            adapter_version if isinstance(adapter_version, str) else ""
        )
        if not isinstance(adapter_id, str) or not adapter_id:
            self.collector.fail_check(
                "contract.metadata", "adapter_id must be a nonempty string"
            )
            self.signatures_ok = False
            return
        if not isinstance(adapter_version, str) or not adapter_version:
            self.collector.fail_check(
                "contract.metadata", "adapter_version must be a nonempty string"
            )
            self.signatures_ok = False
            return
        self.collector.pass_check("contract.metadata")
        for method in ("discover", "parse", "fingerprint"):
            self._signature_check(method)

    def _signature_check(self, method: str) -> None:
        fn = getattr(self.adapter, method)
        try:
            signature = inspect.signature(fn)
        except (TypeError, ValueError) as exc:
            self.collector.fail_check(
                "contract.signature",
                f"cannot inspect {method}: {exc}",
                operation=method,
            )
            self.signatures_ok = False
            return
        parameters = list(signature.parameters.values())
        if not parameters:
            self.collector.fail_check(
                "contract.signature",
                f"{method} has no parameter to receive the input",
                operation=method,
            )
            self.signatures_ok = False
            return
        first = parameters[0]
        if first.kind not in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
        ):
            self.collector.fail_check(
                "contract.signature",
                f"the first parameter of {method} must accept the input positionally",
                operation=method,
            )
            self.signatures_ok = False
            return
        for parameter in parameters[1:]:
            if (
                parameter.kind
                in (
                    inspect.Parameter.POSITIONAL_ONLY,
                    inspect.Parameter.POSITIONAL_OR_KEYWORD,
                )
                and parameter.default is inspect.Parameter.empty
            ):
                self.collector.fail_check(
                    "contract.signature",
                    f"{method} has extra required positional "
                    f"parameter {parameter.name}",
                    operation=method,
                )
                self.signatures_ok = False
                return
            if (
                parameter.kind == inspect.Parameter.KEYWORD_ONLY
                and parameter.default is inspect.Parameter.empty
            ):
                self.collector.fail_check(
                    "contract.signature",
                    f"{method} has required keyword only parameter {parameter.name}",
                    operation=method,
                )
                self.signatures_ok = False
                return
        self.collector.pass_check("contract.signature", operation=method)

    # -- case phase --------------------------------------------------------

    def _run_case(self, case: ConformanceCase) -> None:
        session = self._prepare(case, Variant.ORIGINAL, None, None)
        if session is None:
            return
        self._baseline = {}
        result = self._run_discovery(session, case, original=True)
        if result is not None and result.corpus_error is None:
            self._source_checks(session, case, result)
            self._result_confidence(session, case, result)
            self._fingerprint_probes(case, session, result)
            self._corruption_variants(case)
        self._finish(session)

    # -- workspace lifecycle ------------------------------------------------

    def _prepare(
        self,
        case: ConformanceCase,
        variant: Variant,
        target: Path | None,
        mutation: MutationKind | None,
    ) -> _Session | None:
        if variant == Variant.ORIGINAL:
            workspace = self.fixtures.open_case(case.id, case.corpus)
        else:
            assert target is not None and mutation is not None
            workspace = self.fixtures.open_variant(
                case.id, case.corpus, target, mutation
            )
        if isinstance(workspace, FixtureFailure):
            check = self.collector.fail_check(
                "fixture.prepare",
                _failure_detail(workspace),
                case_id=case.id,
                path=target,
                variant=_coord_variant(variant),
            )
            self._preserve_failed_root(
                case.id, variant, workspace.last_known_path, check
            )
            return None
        self.collector.pass_check(
            "fixture.prepare",
            case_id=case.id,
            path=target,
            variant=_coord_variant(variant),
        )
        return _Session(workspace=workspace, case_id=case.id, variant=variant)

    def _preserve_failed_root(
        self,
        case_id: str,
        variant: Variant,
        last_known_root: Path | None,
        owner: CheckResult,
    ) -> None:
        """Preserve a root that survives a preparation failure, if any (AC-17)."""
        if last_known_root is None:
            return
        result = self.fixtures.preserve(last_known_root)
        if isinstance(result, FixtureFailure):
            check = self.collector.fail_check(
                "fixture.preserve",
                _failure_detail(result),
                case_id=case_id,
                variant=_coord_variant(variant),
            )
            if result.last_known_path is not None:
                check.artifact_path = result.last_known_path
            return
        self.collector.pass_check(
            "fixture.preserve", case_id=case_id, variant=_coord_variant(variant)
        )
        owner.artifact_path = result

    def _finish(self, session: _Session) -> None:
        """Snapshot, compare, then cleanup or preserve one workspace."""
        workspace = session.workspace
        snapshot = self.fixtures.snapshot(workspace.root)
        if isinstance(snapshot, FixtureFailure):
            check = self.collector.fail_check(
                "fixture.snapshot",
                _failure_detail(snapshot),
                case_id=session.case_id,
                variant=_coord_variant(session.variant),
            )
            session.failed.append(check)
        else:
            self.collector.pass_check(
                "fixture.snapshot",
                case_id=session.case_id,
                variant=_coord_variant(session.variant),
            )
            if workspace.baseline is None or snapshot != workspace.baseline:
                check = self.collector.fail_check(
                    "fixture.unchanged",
                    "adapter modified the copied corpus",
                    case_id=session.case_id,
                    variant=_coord_variant(session.variant),
                )
                session.failed.append(check)
            else:
                self.collector.pass_check(
                    "fixture.unchanged",
                    case_id=session.case_id,
                    variant=_coord_variant(session.variant),
                )
        if session.failed:
            result = self.fixtures.preserve(workspace.root)
            if isinstance(result, FixtureFailure):
                check = self.collector.fail_check(
                    "fixture.preserve",
                    _failure_detail(result),
                    case_id=session.case_id,
                    variant=_coord_variant(session.variant),
                )
                if result.last_known_path is not None:
                    check.artifact_path = result.last_known_path
            else:
                self.collector.pass_check(
                    "fixture.preserve",
                    case_id=session.case_id,
                    variant=_coord_variant(session.variant),
                )
                session.failed[0].artifact_path = result
            return
        cleanup = self.fixtures.cleanup(workspace)
        if isinstance(cleanup, FixtureFailure):
            check = self.collector.fail_check(
                "fixture.cleanup",
                _failure_detail(cleanup),
                case_id=session.case_id,
                variant=_coord_variant(session.variant),
            )
            if cleanup.last_known_path is not None:
                check.artifact_path = cleanup.last_known_path
        else:
            self.collector.pass_check(
                "fixture.cleanup",
                case_id=session.case_id,
                variant=_coord_variant(session.variant),
            )

    def _fail(
        self,
        session: _Session,
        rule: str,
        detail: str,
        *,
        source_id: str | None = None,
        path: Path | None = None,
        operation: str | None = None,
    ) -> CheckResult:
        check = self.collector.fail_check(
            rule,
            detail,
            case_id=session.case_id,
            source_id=source_id,
            path=path,
            operation=operation,
            variant=_coord_variant(session.variant),
        )
        session.failed.append(check)
        return check

    def _pass(
        self,
        session: _Session,
        rule: str,
        *,
        source_id: str | None = None,
        path: Path | None = None,
        operation: str | None = None,
    ) -> None:
        self.collector.pass_check(
            rule,
            case_id=session.case_id,
            source_id=source_id,
            path=path,
            operation=operation,
            variant=_coord_variant(session.variant),
        )

    def _adapter_exception(
        self,
        session: _Session,
        operation: str,
        exc: Exception,
        *,
        source_id: str | None = None,
        path: Path | None = None,
    ) -> None:
        detail = f"{type(exc).__name__}: {exc}"
        check = self.collector.fail_check(
            "adapter.exception",
            detail,
            case_id=session.case_id,
            source_id=source_id,
            path=path,
            operation=operation,
            variant=_coord_variant(session.variant),
        )
        session.failed.append(check)

    # -- discovery ----------------------------------------------------------

    def _run_discovery(
        self, session: _Session, case: ConformanceCase, *, original: bool
    ) -> DiscoveryResult | None:
        """Discover once on a workspace, emitting result type and invariants.

        Returns the discovery result, or None when discovery failed or was not
        usable. A failure requests preservation and omits dependent checks.
        """
        try:
            result = self.adapter.discover(session.workspace.root)
        except Exception as exc:  # noqa: BLE001 - adapter execution failure (AC-9)
            self._adapter_exception(session, "discover", exc)
            return None
        if type(result) is not DiscoveryResult:
            self._fail(
                session,
                "contract.result_type",
                f"discover returned {type(result).__name__}, expected DiscoveryResult",
                operation="discover",
            )
            return None
        self._pass(session, "contract.result_type", operation="discover")
        if result.corpus_error is not None:
            self._fail(
                session,
                "discovery.corpus_usable",
                f"corpus error: {result.corpus_error}",
            )
            return result
        self._pass(session, "discovery.corpus_usable")
        if original:
            difference = _discovery_difference(
                result, session.workspace.root, case.expect
            )
            if difference is not None:
                self._fail(session, "discovery.exact", difference)
            else:
                self._pass(session, "discovery.exact")
        problems = _path_problems(result, session.workspace.root)
        if problems:
            self._fail(session, "discovery.paths", "; ".join(problems))
        else:
            self._pass(session, "discovery.paths")
        if original:
            try:
                repeated = self.adapter.discover(session.workspace.root)
            except Exception as exc:  # noqa: BLE001 - adapter execution failure (AC-9)
                self._adapter_exception(session, "discover", exc)
            else:
                if type(repeated) is not DiscoveryResult or _discovery_shape(
                    repeated, session.workspace.root
                ) != _discovery_shape(result, session.workspace.root):
                    self._fail(
                        session,
                        "operation.deterministic",
                        "discover returned different results on repeat",
                        operation="discover",
                    )
                else:
                    self._pass(session, "operation.deterministic", operation="discover")
        return result

    @staticmethod
    def _find_spec(result: DiscoveryResult, source_id: str) -> DiscoveredSpec | None:
        for spec in result.specs:
            if spec.id == source_id:
                return spec
        return None

    # -- per source checks --------------------------------------------------

    def _source_checks(
        self, session: _Session, case: ConformanceCase, result: DiscoveryResult
    ) -> None:
        for expected in case.expect.sources:
            spec = self._find_spec(result, expected.id)
            if spec is None:
                continue
            self._source_checks_one(session, case, spec, expected)

    def _source_checks_one(
        self,
        session: _Session,
        case: ConformanceCase,
        spec: DiscoveredSpec,
        expected: SourceExpectation,
    ) -> None:
        fingerprint_ok, fingerprint = self._fingerprint_direct(
            session, spec, expected.id
        )
        parsed, parse_ok = self._parse_direct(session, spec, expected.id)
        if parse_ok and parsed is not None:
            difference = _result_difference(parsed, expected.result)
            if difference is not None:
                self._fail(session, "result.exact", difference, source_id=expected.id)
            else:
                self._pass(session, "result.exact", source_id=expected.id)
        if (
            parse_ok
            and parsed is not None
            and fingerprint_ok
            and fingerprint is not None
        ):
            if not parsed.fingerprint or parsed.fingerprint != fingerprint:
                self._fail(
                    session,
                    "fingerprint.consistency",
                    "parse fingerprint differs from the direct fingerprint",
                    source_id=expected.id,
                )
            else:
                self._pass(session, "fingerprint.consistency", source_id=expected.id)
                self._baseline[expected.id] = fingerprint

    def _fingerprint_direct(
        self, session: _Session, spec: DiscoveredSpec, source_id: str
    ) -> tuple[bool, str | None]:
        """Direct and repeated fingerprint calls with their checks."""
        try:
            first = self.adapter.fingerprint(spec)
        except Exception as exc:  # noqa: BLE001 - adapter execution failure (AC-9)
            self._adapter_exception(session, "fingerprint", exc, source_id=source_id)
            return False, None
        if type(first) is not str:
            self._fail(
                session,
                "contract.result_type",
                f"fingerprint returned {type(first).__name__}, expected str",
                operation="fingerprint",
                source_id=source_id,
            )
            return False, None
        self._pass(
            session,
            "contract.result_type",
            operation="fingerprint",
            source_id=source_id,
        )
        try:
            repeated = self.adapter.fingerprint(spec)
        except Exception as exc:  # noqa: BLE001 - adapter execution failure (AC-9)
            self._adapter_exception(session, "fingerprint", exc, source_id=source_id)
            return False, None
        if type(repeated) is not str or first != repeated:
            self._fail(
                session,
                "operation.deterministic",
                "fingerprint changed between calls",
                operation="fingerprint",
                source_id=source_id,
            )
            return False, None
        self._pass(
            session,
            "operation.deterministic",
            operation="fingerprint",
            source_id=source_id,
        )
        return True, first

    def _parse_direct(
        self, session: _Session, spec: DiscoveredSpec, source_id: str
    ) -> tuple[AdaptationResult | None, bool]:
        """Parse twice on the original source, emitting type and determinism."""
        try:
            first = self.adapter.parse(spec)
        except Exception as exc:  # noqa: BLE001 - adapter execution failure (AC-9)
            self._adapter_exception(session, "parse", exc, source_id=source_id)
            return None, False
        if type(first) is not AdaptationResult:
            self._fail(
                session,
                "contract.result_type",
                f"parse returned {type(first).__name__}, expected AdaptationResult",
                operation="parse",
                source_id=source_id,
            )
            return None, False
        self._pass(
            session, "contract.result_type", operation="parse", source_id=source_id
        )
        try:
            repeated = self.adapter.parse(spec)
        except Exception as exc:  # noqa: BLE001 - adapter execution failure (AC-9)
            self._adapter_exception(session, "parse", exc, source_id=source_id)
            return None, False
        if type(repeated) is not AdaptationResult or _adaptation_shape(
            first
        ) != _adaptation_shape(repeated):
            self._fail(
                session,
                "operation.deterministic",
                "parse changed between calls",
                operation="parse",
                source_id=source_id,
            )
            return None, False
        self._pass(
            session, "operation.deterministic", operation="parse", source_id=source_id
        )
        return first, True

    def _parse_for_check(
        self, session: _Session, spec: DiscoveredSpec, *, path: Path | None = None
    ) -> AdaptationResult | None:
        """Parse once in a generated workspace, emitting type and exception."""
        try:
            parsed = self.adapter.parse(spec)
        except Exception as exc:  # noqa: BLE001 - adapter execution failure (AC-9)
            self._adapter_exception(session, "parse", exc, path=path)
            return None
        if type(parsed) is not AdaptationResult:
            self._fail(
                session,
                "contract.result_type",
                f"parse returned {type(parsed).__name__}, expected AdaptationResult",
                operation="parse",
                path=path,
            )
            return None
        self._pass(session, "contract.result_type", operation="parse", path=path)
        return parsed

    # -- result.confidence (grammar drift categories, AC-7) -----------------

    def _result_confidence(
        self, session: _Session, case: ConformanceCase, result: DiscoveryResult
    ) -> None:
        if (
            case.category
            not in (
                ConformanceCategory.WRONG_HEADING,
                ConformanceCategory.MISSING_REQUIRED_FIELD,
            )
        ) or case.subject_path is None:
            return
        subject = case.subject_path.as_posix()
        skip_paths = {
            _rel_or_raw(session.workspace.root, skip.path) for skip in result.skipped
        }
        if subject in skip_paths:
            self._pass(session, "result.confidence", path=case.subject_path)
            return
        spec = next(
            (
                candidate
                for candidate in result.specs
                if _rel_or_raw(session.workspace.root, candidate.root) == subject
            ),
            None,
        )
        if spec is None:
            self._pass(session, "result.confidence", path=case.subject_path)
            return
        parsed = self._parse_for_check(session, spec, path=case.subject_path)
        if parsed is None:
            return
        if _is_confident(parsed):
            self._fail(
                session,
                "result.confidence",
                "malformed subject produced confident output",
                path=case.subject_path,
            )
        else:
            self._pass(session, "result.confidence", path=case.subject_path)

    # -- fingerprint coverage (AC-13) ----------------------------------------

    def _fingerprint_probes(
        self, case: ConformanceCase, session: _Session, result: DiscoveryResult
    ) -> None:
        for expected in case.expect.sources:
            spec = self._find_spec(result, expected.id)
            if spec is None:
                continue
            baseline = self._baseline.get(expected.id)
            if baseline is None:
                continue
            for contrib in expected.contributing_files:
                self._fingerprint_probe(
                    case, session, spec, expected, contrib, baseline
                )

    def _fingerprint_probe(
        self,
        case: ConformanceCase,
        session: _Session,
        spec: DiscoveredSpec,
        expected: SourceExpectation,
        contrib: Path,
        baseline: str,
    ) -> None:
        probe = self._prepare(
            case, Variant.FINGERPRINT_PROBE, contrib, MutationKind.FINGERPRINT_PROBE
        )
        if probe is None:
            return
        remapped = DiscoveredSpec(
            id=spec.id,
            root=probe.workspace.root / spec.root.relative_to(session.workspace.root),
            corpus_root=probe.workspace.root,
            contributing_files=[
                probe.workspace.root / path.relative_to(session.workspace.root)
                for path in spec.contributing_files
            ],
        )
        try:
            value = self.adapter.fingerprint(remapped)
        except Exception as exc:  # noqa: BLE001 - adapter execution failure (AC-9)
            self._adapter_exception(probe, "fingerprint", exc, path=contrib)
        else:
            if type(value) is not str:
                self._fail(
                    probe,
                    "contract.result_type",
                    f"fingerprint returned {type(value).__name__}, expected str",
                    operation="fingerprint",
                    path=contrib,
                )
            else:
                self._pass(
                    probe, "contract.result_type", operation="fingerprint", path=contrib
                )
                if value == baseline:
                    self._fail(
                        probe,
                        "fingerprint.coverage",
                        "changing a contributing file did not change the fingerprint",
                        path=contrib,
                    )
                else:
                    self._pass(probe, "fingerprint.coverage", path=contrib)
        self._finish(probe)

    # -- corruption variants (AC-8) ------------------------------------------

    def _corruption_variants(self, case: ConformanceCase) -> None:
        required = self._all_required_files(case)
        for req in required:
            self._corruption_run(case, req, Variant.EMPTY, MutationKind.EMPTY)
            self._corruption_run(
                case, req, Variant.INVALID_UTF8, MutationKind.INVALID_UTF8
            )

    @staticmethod
    def _all_required_files(case: ConformanceCase) -> tuple[Path, ...]:
        seen: list[Path] = []
        for source in case.expect.sources:
            for required in source.required_files:
                if required not in seen:
                    seen.append(required)
        return tuple(seen)

    def _corruption_run(
        self,
        case: ConformanceCase,
        req: Path,
        variant: Variant,
        mutation: MutationKind,
    ) -> None:
        session = self._prepare(case, variant, req, mutation)
        if session is None:
            return
        result = self._run_discovery(session, case, original=False)
        if result is None or result.corpus_error is not None:
            self._finish(session)
            return
        rule = (
            "corruption.empty"
            if variant == Variant.EMPTY
            else "corruption.invalid_utf8"
        )
        problems: list[str] = []
        omitted = False
        for expected in case.expect.sources:
            affected = req in expected.contributing_files
            spec = self._find_spec(result, expected.id)
            if affected:
                if spec is None:
                    continue
                parsed = self._parse_for_check(session, spec, path=req)
                if parsed is None:
                    omitted = True
                    break
                if _is_confident(parsed):
                    problems.append(
                        f"{expected.id} produced confident output "
                        "on the corrupted corpus"
                    )
            else:
                if spec is None:
                    problems.append(
                        f"{expected.id} disappeared from the corrupted corpus"
                    )
                    continue
                parsed = self._parse_for_check(session, spec, path=req)
                if parsed is None:
                    omitted = True
                    break
                difference = _result_difference(parsed, expected.result)
                if difference is not None:
                    problems.append(f"{expected.id} changed: {difference}")
        if omitted:
            pass
        elif problems:
            self._fail(session, rule, "; ".join(problems), path=req)
        else:
            self._pass(session, rule, path=req)
        self._finish(session)


def run_adapter_conformance(
    adapter: SourceAdapter,
    manifest: ConformanceManifest,
    fixtures: ConformanceFixturePort,
) -> ConformanceOutcome:
    """Run every reachable check against the adapter and manifest (AC-1, AC-18).

    The engine is the public typed application function used by the CLI and
    project tests. Failures are typed check results, never raised adapter
    exceptions; process control values such as ``KeyboardInterrupt`` escape.
    """
    return _Engine(adapter, manifest, fixtures).run()
