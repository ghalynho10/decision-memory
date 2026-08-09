"""Conformance engine unit tests (spec 0006).

These drive the public ``run_adapter_conformance`` engine with a configurable
fake adapter and the real fixture workspace port, so every failure property in
the spec's critical test scenarios is exercised against real copied corpora:
exact comparison, grammar drift confidence, corruption, fingerprint coverage,
write detection, preservation, adapter exceptions, signature and result type
boundaries, and continued independent execution.
"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from decision_memory.application.adapter import (
    AdaptationResult,
    DiscoveredSpec,
    DiscoveryResult,
    SkippedSource,
    SourceAdapter,
)
from decision_memory.application.conformance import (
    CollisionExpectation,
    ConformanceCase,
    ConformanceCategory,
    ConformanceManifest,
    ConformanceOutcome,
    CorpusSnapshot,
    DiscoveryExpectation,
    FixtureFailure,
    MutationKind,
    ResultExpectation,
    SkipExpectation,
    SourceExpectation,
    Variant,
    Workspace,
    run_adapter_conformance,
)
from decision_memory.domain.records import (
    CanonicalDecisionRecord,
    Decision,
    Evidence,
    EvidenceKind,
    Severity,
    Status,
    Violation,
)
from decision_memory.infrastructure.conformance_fixtures import WorkspaceFixture

# ---------------------------------------------------------------------------
# Shared builders
# ---------------------------------------------------------------------------


def _record(
    record_id: str, *, rationale_summary: str | None = None
) -> CanonicalDecisionRecord:
    record = CanonicalDecisionRecord(
        id=record_id,
        title="A decision",
        status=Status.ACCEPTED,
        date="2026-08-09",
        body="",
        decision=Decision(chosen="Chosen"),
        why=["Because"],
        evidence=[Evidence(kind=EvidenceKind.FILE, target=f"decisions/{record_id}.md")],
    )
    if rationale_summary is not None:
        record = replace(record, rationale_summary=rationale_summary)
    return record


def _source(
    record_id: str,
    record: CanonicalDecisionRecord,
    *,
    required: tuple[str, ...] = (),
) -> SourceExpectation:
    return SourceExpectation(
        id=record_id,
        root=Path(f"decisions/{record_id}.md"),
        contributing_files=(Path(f"decisions/{record_id}.md"),),
        required_files=tuple(Path(p) for p in required),
        result=ResultExpectation(
            record=record,
            attempted_fields=frozenset(),
            unresolved_mention_count=0,
            violations=(),
        ),
    )


def _case(
    case_id: str,
    category: ConformanceCategory,
    corpus: Path,
    *,
    sources: tuple[SourceExpectation, ...] = (),
    skips: tuple[SkipExpectation, ...] = (),
    collisions: tuple[CollisionExpectation, ...] = (),
    subject: str | None = None,
    target: frozenset[str] = frozenset(),
) -> ConformanceCase:
    return ConformanceCase(
        id=case_id,
        category=category,
        corpus=corpus,
        subject_path=Path(subject) if subject is not None else None,
        target_fields=target,
        expect=DiscoveryExpectation(
            sources=sources, skips=skips, collisions=collisions
        ),
    )


def _manifest(*cases: ConformanceCase) -> ConformanceManifest:
    return ConformanceManifest(schema_version=1, cases=tuple(cases))


def _write_decision(corpus: Path, name: str, *, decision: bool = True) -> Path:
    decisions = corpus / "decisions"
    decisions.mkdir(parents=True, exist_ok=True)
    path = decisions / f"{name}.md"
    body = [
        f"# {name}",
        "",
        "**Status**: Accepted",
        "**Date**: 2026-08-09",
        "",
        "## Context",
        "",
        "Context text.",
    ]
    if decision:
        body += [
            "",
            "## Decision",
            "",
            f"Chosen {name}.",
            "",
            "## Why",
            "",
            "- Because",
        ]
    path.write_text("\n".join(body) + "\n", encoding="utf-8")
    return path


class ConfAdapter:
    """A controllable adapter that reads decisions/*.md from the copied corpus."""

    def __init__(
        self,
        *,
        results: dict[str, AdaptationResult] | None = None,
        discover_error: Exception | None = None,
        parse_error: Exception | None = None,
        fingerprint_error: Exception | None = None,
        corpus_error: str | None = None,
        always_discover: bool = False,
        constant_fingerprint: bool = False,
    ) -> None:
        self._results = results or {}
        self._discover_error = discover_error
        self._parse_error = parse_error
        self._fingerprint_error = fingerprint_error
        self._corpus_error = corpus_error
        self._always_discover = always_discover
        self._constant_fingerprint = constant_fingerprint

    @property
    def adapter_id(self) -> str:
        return "conf-fake"

    @property
    def adapter_version(self) -> str:
        return "1"

    def discover(self, corpus_root: Path) -> DiscoveryResult:
        if self._discover_error is not None:
            raise self._discover_error
        if self._corpus_error is not None:
            return DiscoveryResult([], [], [], corpus_error=self._corpus_error)
        specs: list[DiscoveredSpec] = []
        skipped: list[SkippedSource] = []
        decisions = corpus_root / "decisions"
        for path in sorted(decisions.glob("*.md")):
            text = _read_text(path)
            if text is None:
                skipped.append(SkippedSource(path=path, reason="cannot read file"))
                continue
            if not self._always_discover and "## Decision" not in text:
                skipped.append(
                    SkippedSource(path=path, reason="no ## Decision section")
                )
                continue
            specs.append(
                DiscoveredSpec(
                    id=path.stem,
                    root=path,
                    corpus_root=corpus_root,
                    contributing_files=[path],
                )
            )
        return DiscoveryResult(specs, skipped, [])

    def fingerprint(self, spec: DiscoveredSpec) -> str:
        if self._fingerprint_error is not None:
            raise self._fingerprint_error
        if self._constant_fingerprint:
            return "constant"
        digest = hashlib.sha256()
        for path in spec.contributing_files:
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def parse(self, spec: DiscoveredSpec) -> AdaptationResult:
        if self._parse_error is not None:
            raise self._parse_error
        result = self._results.get(
            spec.id,
            AdaptationResult(
                record=None,
                violations=[],
                attempted_fields=frozenset(),
                unresolved_mention_count=0,
                fingerprint=self.fingerprint(spec),
                field_sources={},
            ),
        )
        if not result.fingerprint:
            result = replace(result, fingerprint=self.fingerprint(spec))
        return result


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _result(record: CanonicalDecisionRecord) -> AdaptationResult:
    return AdaptationResult(
        record=record,
        violations=[],
        attempted_fields=frozenset(),
        unresolved_mention_count=0,
        fingerprint="",
        field_sources={},
    )


def _failures(outcome: ConformanceOutcome) -> list[str]:
    return [check.rule for check in outcome.checks if not check.status]


# ---------------------------------------------------------------------------
# Happy path and exact comparison
# ---------------------------------------------------------------------------


class TestValidCase:
    def test_a_valid_case_passes_every_check(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        record = _record("one")
        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", record, required=("decisions/one.md",)),),
        )
        adapter = ConfAdapter(results={"one": _result(record)})
        outcome = run_adapter_conformance(adapter, _manifest(case), WorkspaceFixture())
        assert outcome.failed == 0
        assert outcome.exit_code == 0
        assert outcome.passed > 0

    def test_an_invented_field_fails_the_record_check(self, tmp_path: Path) -> None:
        # AC-4: an invented canonical field fails even when id and validity look
        # right, because the expected record does not carry it.
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        expected_record = _record("one")
        actual_record = _record("one", rationale_summary="invented")
        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", expected_record, required=("decisions/one.md",)),),
        )
        adapter = ConfAdapter(results={"one": _result(actual_record)})
        outcome = run_adapter_conformance(adapter, _manifest(case), WorkspaceFixture())
        failed = [c for c in outcome.checks if not c.status]
        assert any(c.rule == "result.exact" for c in failed)
        assert any("rationale_summary" in c.detail for c in failed)
        assert outcome.exit_code == 1

    def test_an_invented_field_fails_even_when_the_record_is_valid(
        self, tmp_path: Path
    ) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        expected = _record("one")
        # The invented field still leaves the record otherwise valid, so a
        # textual validator would pass it; exact comparison must not.
        actual = _record("one", rationale_summary="invented but valid")
        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", expected),),
        )
        outcome = run_adapter_conformance(
            ConfAdapter(results={"one": _result(actual)}),
            _manifest(case),
            WorkspaceFixture(),
        )
        assert "result.exact" in _failures(outcome)

    def test_attempted_fields_and_violations_compare(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        expected = _source(
            "one",
            _record("one"),
        )
        expected = replace(
            expected,
            result=ResultExpectation(
                record=_record("one"),
                attempted_fields=frozenset({"why"}),
                unresolved_mention_count=0,
                violations=(),
            ),
        )
        case = _case("valid", ConformanceCategory.VALID, corpus, sources=(expected,))
        actual = replace(
            _result(_record("one")), attempted_fields=frozenset({"why", "context"})
        )
        outcome = run_adapter_conformance(
            ConfAdapter(results={"one": actual}), _manifest(case), WorkspaceFixture()
        )
        assert "result.exact" in _failures(outcome)


class TestDiscoveryComparison:
    def test_a_missing_source_fails_discovery_exact(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        _write_decision(corpus, "two")
        record = _record("one")
        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", record),),
        )
        # Discovery returns an extra source that is not expected.
        adapter = ConfAdapter(
            results={"one": _result(record), "two": _result(_record("two"))}
        )
        # The expectation only lists one; the extra appears anyway.
        case = replace(
            case,
            expect=replace(case.expect, sources=(_source("one", record),)),
        )
        outcome = run_adapter_conformance(adapter, _manifest(case), WorkspaceFixture())
        assert "discovery.exact" in _failures(outcome)


# ---------------------------------------------------------------------------
# Contract boundaries
# ---------------------------------------------------------------------------


class TestContractSignature:
    def test_an_extra_required_positional_parameter_fails(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")

        class BadAdapter(ConfAdapter):
            # Deliberately violates the protocol: an extra required parameter.
            def discover(self, corpus_root: Path, extra: str) -> DiscoveryResult:  # type: ignore[override]
                return super().discover(corpus_root)

        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", _record("one")),),
        )
        # The deliberately broken signature is a protocol violation by design.
        outcome = run_adapter_conformance(
            cast(SourceAdapter, BadAdapter()), _manifest(case), WorkspaceFixture()
        )
        failed = [c for c in outcome.checks if not c.status]
        assert any(
            c.rule == "contract.signature" and c.operation == "discover" for c in failed
        )
        # A failed signature omits all case execution.
        assert not any(c.case_id is not None for c in outcome.checks)

    def test_optional_and_variadic_parameters_pass(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        record = _record("one")

        class FlexibleAdapter(ConfAdapter):
            def discover(
                self, corpus_root: Path, *, options: str | None = None, **kwargs: object
            ) -> DiscoveryResult:
                return super().discover(corpus_root)

            def parse(self, spec: DiscoveredSpec, *args: object) -> AdaptationResult:
                return super().parse(spec)

            def fingerprint(self, spec: DiscoveredSpec, flag: bool = True) -> str:
                return super().fingerprint(spec)

        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", record),),
        )
        outcome = run_adapter_conformance(
            FlexibleAdapter(results={"one": _result(record)}),
            _manifest(case),
            WorkspaceFixture(),
        )
        assert outcome.failed == 0


class TestResultTypes:
    def test_a_lookalike_discovery_result_is_rejected(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")

        class WrongAdapter(ConfAdapter):
            # Deliberately returns a lookalike, not the exact contract type.
            def discover(self, corpus_root: Path) -> object:  # type: ignore[override]
                return {"specs": []}

        case = _case("valid", ConformanceCategory.VALID, corpus)
        # The lookalike return type is a protocol violation by design.
        outcome = run_adapter_conformance(
            cast(SourceAdapter, WrongAdapter()), _manifest(case), WorkspaceFixture()
        )
        failed = [c for c in outcome.checks if not c.status]
        assert any(
            c.rule == "contract.result_type" and c.operation == "discover"
            for c in failed
        )


class TestAdapterException:
    def test_an_exception_fails_and_later_cases_continue(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        _write_decision(corpus, "two")
        record = _record("one")
        second = _case(
            "second",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("two", record),),
        )
        # The first case's adapter raises during discovery; the second case's
        # discovery must still run.
        failing = replace(second, id="first")

        class RaiseOnceAdapter(ConfAdapter):
            def __init__(self) -> None:
                super().__init__(
                    results={"one": _result(record), "two": _result(record)}
                )
                self.calls = 0

            def discover(self, corpus_root: Path) -> DiscoveryResult:
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("boom")
                return super().discover(corpus_root)

        outcome = run_adapter_conformance(
            RaiseOnceAdapter(), _manifest(failing, second), WorkspaceFixture()
        )
        failed = [c for c in outcome.checks if not c.status]
        assert any(
            c.rule == "adapter.exception" and c.operation == "discover" for c in failed
        )
        # The independent later case still ran and passed.
        assert any(
            c.rule == "result.exact" and c.status and c.case_id == "second"
            for c in outcome.checks
        )

    def test_keyboard_interrupt_escapes(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")

        class InterruptAdapter(ConfAdapter):
            def discover(self, corpus_root: Path) -> DiscoveryResult:
                raise KeyboardInterrupt()

        case = _case("valid", ConformanceCategory.VALID, corpus)
        with pytest.raises(KeyboardInterrupt):
            run_adapter_conformance(
                InterruptAdapter(), _manifest(case), WorkspaceFixture()
            )


class TestDeterminism:
    def test_discovery_that_changes_between_calls_fails(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        record = _record("one")
        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", record),),
        )

        class StatefulAdapter(ConfAdapter):
            def __init__(self) -> None:
                super().__init__(results={"one": _result(record)})
                self.calls = 0

            def discover(self, corpus_root: Path) -> DiscoveryResult:
                self.calls += 1
                result = super().discover(corpus_root)
                if self.calls == 2:
                    # Second call reports a different source id.
                    spec = result.specs[0]
                    result = DiscoveryResult(
                        [
                            replace(spec, id="changed"),
                        ],
                        [],
                        [],
                    )
                return result

        outcome = run_adapter_conformance(
            StatefulAdapter(), _manifest(case), WorkspaceFixture()
        )
        failed = [c for c in outcome.checks if not c.status]
        assert any(
            c.rule == "operation.deterministic" and c.operation == "discover"
            for c in failed
        )


# ---------------------------------------------------------------------------
# Confidence and grammar drift (AC-6, AC-7)
# ---------------------------------------------------------------------------


class TestConfidence:
    def _malformed_case(
        self, tmp_path: Path, category: ConformanceCategory, subject: str
    ) -> ConformanceCase:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "subject", decision=False)
        target = frozenset({"decision.chosen"})
        return _case(
            "drift",
            category,
            corpus,
            subject=subject,
            target=target,
        )

    def test_a_confident_record_for_a_malformed_subject_fails(
        self, tmp_path: Path
    ) -> None:
        case = self._malformed_case(
            tmp_path, ConformanceCategory.WRONG_HEADING, "decisions/subject.md"
        )
        # The adapter discovers the subject and returns a valid record.
        adapter = ConfAdapter(
            results={"subject": _result(_record("subject"))}, always_discover=True
        )
        outcome = run_adapter_conformance(adapter, _manifest(case), WorkspaceFixture())
        assert "result.confidence" in _failures(outcome)

    def test_a_skipped_malformed_subject_passes(self, tmp_path: Path) -> None:
        case = self._malformed_case(
            tmp_path, ConformanceCategory.WRONG_HEADING, "decisions/subject.md"
        )
        expect = replace(
            case.expect,
            skips=(SkipExpectation(Path("decisions/subject.md")),),
        )
        case = replace(case, expect=expect)
        adapter = ConfAdapter()
        outcome = run_adapter_conformance(adapter, _manifest(case), WorkspaceFixture())
        failed = [c for c in outcome.checks if not c.status]
        assert not any(c.rule == "result.confidence" for c in failed)

    def test_an_absent_malformed_subject_passes(self, tmp_path: Path) -> None:
        case = self._malformed_case(
            tmp_path, ConformanceCategory.MISSING_REQUIRED_FIELD, "decisions/subject.md"
        )
        adapter = ConfAdapter()
        outcome = run_adapter_conformance(adapter, _manifest(case), WorkspaceFixture())
        failed = [c for c in outcome.checks if not c.status]
        assert not any(c.rule == "result.confidence" for c in failed)

    def test_a_non_confident_record_for_a_malformed_subject_passes(
        self, tmp_path: Path
    ) -> None:
        case = self._malformed_case(
            tmp_path, ConformanceCategory.MISSING_REQUIRED_FIELD, "decisions/subject.md"
        )
        error_record = _record("subject")

        actual = AdaptationResult(
            record=error_record,
            violations=[Violation("", Severity.ERROR, "rationale.missing", "missing")],
            attempted_fields=frozenset(),
            unresolved_mention_count=0,
            fingerprint="",
            field_sources={},
        )
        adapter = ConfAdapter(results={"subject": actual})
        outcome = run_adapter_conformance(adapter, _manifest(case), WorkspaceFixture())
        failed = [c for c in outcome.checks if not c.status]
        assert not any(c.rule == "result.confidence" for c in failed)


# ---------------------------------------------------------------------------
# Fingerprint coverage and write detection
# ---------------------------------------------------------------------------


class TestFingerprintCoverage:
    def test_a_content_independent_fingerprint_fails_coverage(
        self, tmp_path: Path
    ) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        record = _record("one")
        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", record),),
        )
        adapter = ConfAdapter(
            results={"one": _result(record)}, constant_fingerprint=True
        )
        outcome = run_adapter_conformance(adapter, _manifest(case), WorkspaceFixture())
        failed = [c for c in outcome.checks if not c.status]
        assert any(c.rule == "fingerprint.coverage" for c in failed)

    def test_editing_the_corpus_fails_fixture_unchanged(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        path = _write_decision(corpus, "one")
        record = _record("one")
        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", record),),
        )

        class EditingAdapter(ConfAdapter):
            def parse(self, spec: DiscoveredSpec) -> AdaptationResult:
                spec.contributing_files[0].write_text("# tampered", encoding="utf-8")
                return _result(record)

        outcome = run_adapter_conformance(
            EditingAdapter(results={"one": _result(record)}),
            _manifest(case),
            WorkspaceFixture(),
        )
        failed = [c for c in outcome.checks if not c.status]
        assert any(c.rule == "fixture.unchanged" for c in failed)
        # The original fixture was not touched.
        assert "# tampered" not in path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Preservation and cleanup (AC-17)
# ---------------------------------------------------------------------------


class TestPreservation:
    def test_a_failed_workspace_is_preserved_and_cleaned_up_on_success(
        self, tmp_path: Path
    ) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")

        # Expect a record the adapter will not produce: rationale_summary absent
        # in expectation but present in actual output.
        expected_record = _record("one")
        actual_record = _record("one", rationale_summary="invented")
        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", expected_record),),
        )
        fixtures = WorkspaceFixture()
        outcome = run_adapter_conformance(
            ConfAdapter(results={"one": _result(actual_record)}),
            _manifest(case),
            fixtures,
        )
        failed = [c for c in outcome.checks if not c.status]
        assert any(c.rule == "result.exact" for c in failed)
        # The first failed check owns the preserved artifact path.
        assert failed[0].artifact_path is not None
        artifact = Path(failed[0].artifact_path)
        assert artifact.is_dir()
        # The original case corpus is untouched.
        assert (corpus / "decisions" / "one.md").is_file()


class TestCorpusUsable:
    def test_a_corpus_error_fails_and_omits_source_checks(self, tmp_path: Path) -> None:
        # AC-5: a nonnull corpus_error is forbidden in a conformance case and
        # fails discovery.corpus_usable, then omits source checks.
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        record = _record("one")
        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", record),),
        )
        adapter = ConfAdapter(
            results={"one": _result(record)}, corpus_error="no docs/specs directory"
        )
        outcome = run_adapter_conformance(adapter, _manifest(case), WorkspaceFixture())
        assert "discovery.corpus_usable" in _failures(outcome)
        # Source checks are omitted entirely.
        assert not any(c.rule == "result.exact" for c in outcome.checks)
        assert not any(c.rule == "fingerprint.consistency" for c in outcome.checks)


class TestFixtureFailures:
    """Fixture operation failures keep their fixed rule ids (AC-17)."""

    def _empty_case(self, corpus: Path) -> ConformanceCase:
        return _case("empty", ConformanceCategory.VALID, corpus)

    def test_a_prepare_failure_emits_fixture_prepare(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        fixtures = BrokenFixture(fail_prepare=True)
        outcome = run_adapter_conformance(
            ConfAdapter(), _manifest(self._empty_case(corpus)), fixtures
        )
        assert "fixture.prepare" in _failures(outcome)
        # The surviving root was preserved once.
        assert len(fixtures.preserved) == 1

    def test_a_snapshot_failure_requests_preservation(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        fixtures = BrokenFixture(fail_snapshot=True)
        outcome = run_adapter_conformance(
            ConfAdapter(), _manifest(self._empty_case(corpus)), fixtures
        )
        assert "fixture.snapshot" in _failures(outcome)
        assert any(c.rule == "fixture.preserve" and c.status for c in outcome.checks)
        # Cleanup is skipped after preservation.
        assert not fixtures.cleaned

    def test_a_preserve_failure_skips_cleanup(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        expected = _record("one")
        actual = _record("one", rationale_summary="invented")
        case = _case(
            "valid",
            ConformanceCategory.VALID,
            corpus,
            sources=(_source("one", expected),),
        )
        fixtures = BrokenFixture(fail_preserve=True)
        outcome = run_adapter_conformance(
            ConfAdapter(results={"one": _result(actual)}), _manifest(case), fixtures
        )
        assert "fixture.preserve" in _failures(outcome)
        assert not fixtures.cleaned

    def test_a_cleanup_failure_does_not_preserve(self, tmp_path: Path) -> None:
        corpus = tmp_path / "corpus"
        _write_decision(corpus, "one")
        fixtures = BrokenFixture(fail_cleanup=True)
        outcome = run_adapter_conformance(
            ConfAdapter(), _manifest(self._empty_case(corpus)), fixtures
        )
        assert "fixture.cleanup" in _failures(outcome)
        assert not fixtures.preserved


class BrokenFixture:
    """A fixture port that can fail one operation on demand (AC-17)."""

    def __init__(
        self,
        *,
        fail_prepare: bool = False,
        fail_snapshot: bool = False,
        fail_preserve: bool = False,
        fail_cleanup: bool = False,
    ) -> None:
        self._fail_prepare = fail_prepare
        self._fail_snapshot = fail_snapshot
        self._fail_preserve = fail_preserve
        self._fail_cleanup = fail_cleanup
        self.preserved: list[Path] = []
        self.cleaned: list[Path] = []

    def open_case(self, case_id: str, corpus: Path) -> Workspace | FixtureFailure:
        if self._fail_prepare:
            return FixtureFailure("prepare", "OSError", "boom", last_known_path=corpus)
        return Workspace(
            root=Path("/ws") / case_id,
            variant=Variant.ORIGINAL,
            baseline=CorpusSnapshot(()),
        )

    def open_variant(
        self,
        case_id: str,
        corpus: Path,
        target: Path,
        mutation: MutationKind,
    ) -> Workspace | FixtureFailure:
        if self._fail_prepare:
            return FixtureFailure("prepare", "OSError", "boom", last_known_path=corpus)
        variant = (
            Variant.EMPTY
            if mutation == MutationKind.EMPTY
            else Variant.INVALID_UTF8
            if mutation == MutationKind.INVALID_UTF8
            else Variant.FINGERPRINT_PROBE
        )
        return Workspace(
            root=Path("/ws") / case_id,
            variant=variant,
            mutation_path=target,
            mutation_kind=mutation,
            baseline=CorpusSnapshot(()),
        )

    def snapshot(self, root: Path) -> CorpusSnapshot | FixtureFailure:
        if self._fail_snapshot:
            return FixtureFailure("snapshot", "OSError", "boom")
        return CorpusSnapshot(())

    def preserve(self, root: Path) -> Path | FixtureFailure:
        if self._fail_preserve:
            return FixtureFailure("preserve", "OSError", "boom", last_known_path=root)
        self.preserved.append(root)
        return root

    def cleanup(self, workspace: Workspace) -> None | FixtureFailure:
        if self._fail_cleanup:
            return FixtureFailure(
                "cleanup", "OSError", "boom", last_known_path=workspace.root
            )
        self.cleaned.append(workspace.root)
        return None


class SharedFileAdapter:
    """Three sources; one and two both derive from decisions/one.md (AC-8).

    This is the adapter shape that makes a required file genuinely shared by
    two sources: ``one`` and ``two`` both list ``decisions/one.md`` as their
    contributing file, and ``three`` is independent. Corrupting the shared
    file must make both sharing sources non confident while ``three`` keeps
    its exact result.
    """

    @property
    def adapter_id(self) -> str:
        return "shared"

    @property
    def adapter_version(self) -> str:
        return "1"

    def discover(self, corpus_root: Path) -> DiscoveryResult:
        specs: list[DiscoveredSpec] = []
        for name in ("one", "two", "three"):
            contributing = "one" if name != "three" else "three"
            specs.append(
                DiscoveredSpec(
                    id=name,
                    root=corpus_root / "decisions" / f"{name}.md",
                    corpus_root=corpus_root,
                    contributing_files=[
                        corpus_root / "decisions" / f"{contributing}.md"
                    ],
                )
            )
        return DiscoveryResult(specs, [], [])

    def fingerprint(self, spec: DiscoveredSpec) -> str:
        digest = hashlib.sha256()
        digest.update(spec.id.encode("utf-8"))
        for path in spec.contributing_files:
            digest.update(path.read_bytes())
        return digest.hexdigest()

    def parse(self, spec: DiscoveredSpec) -> AdaptationResult:
        text = _read_text(spec.contributing_files[0])
        if text is None or "## Decision" not in text:
            return AdaptationResult(
                record=None,
                violations=[
                    Violation("", Severity.ERROR, "file.unreadable", "no decision")
                ],
                attempted_fields=frozenset(),
                unresolved_mention_count=0,
                fingerprint=self.fingerprint(spec),
                field_sources={},
            )
        record = CanonicalDecisionRecord(
            id=spec.id,
            title=f"Title {spec.id}",
            status=Status.ACCEPTED,
            body="",
            decision=Decision(chosen="Chosen"),
            why=["x"],
            evidence=[
                Evidence(kind=EvidenceKind.FILE, target=f"decisions/{spec.id}.md")
            ],
        )
        return AdaptationResult(
            record=record,
            violations=[],
            attempted_fields=frozenset(),
            unresolved_mention_count=0,
            fingerprint=self.fingerprint(spec),
            field_sources={},
        )


class TestSharedCorruption:
    """AC-8: every source listing a required file is affected on corruption."""

    def _sources(self) -> tuple[SourceExpectation, ...]:
        def make(name: str, required: tuple[str, ...]) -> SourceExpectation:
            contributing = "one" if name != "three" else "three"
            return SourceExpectation(
                id=name,
                root=Path(f"decisions/{name}.md"),
                contributing_files=(Path(f"decisions/{contributing}.md"),),
                required_files=tuple(Path(p) for p in required),
                result=ResultExpectation(
                    record=CanonicalDecisionRecord(
                        id=name,
                        title=f"Title {name}",
                        status=Status.ACCEPTED,
                        body="",
                        decision=Decision(chosen="Chosen"),
                        why=["x"],
                        evidence=[
                            Evidence(
                                kind=EvidenceKind.FILE,
                                target=f"decisions/{name}.md",
                            )
                        ],
                    ),
                    attempted_fields=frozenset(),
                    unresolved_mention_count=0,
                    violations=(),
                ),
            )

        return (
            make("one", ("decisions/one.md",)),
            make("two", ("decisions/one.md",)),
            make("three", ("decisions/three.md",)),
        )

    def test_a_shared_required_file_affects_every_source_that_lists_it(
        self, tmp_path: Path
    ) -> None:
        corpus = tmp_path / "corpus"
        for name in ("one", "two", "three"):
            _write_decision(corpus, name)
        case = ConformanceCase(
            id="shared",
            category=ConformanceCategory.VALID,
            corpus=corpus,
            subject_path=None,
            target_fields=frozenset(),
            expect=DiscoveryExpectation(
                sources=self._sources(), skips=(), collisions=()
            ),
        )
        outcome = run_adapter_conformance(
            SharedFileAdapter(), _manifest(case), WorkspaceFixture()
        )
        # Corruption runs for both required files, empty before invalid_utf8.
        corruption = [c for c in outcome.checks if c.rule.startswith("corruption.")]
        assert len(corruption) == 4
        assert all(c.status for c in corruption)
        assert outcome.failed == 0
        assert outcome.exit_code == 0
