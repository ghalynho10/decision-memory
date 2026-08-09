"""Application: write free corpus validation (spec 0005 AC-5 to AC-9).

Corpus validation answers a different question than record validation: can an
adapter turn a corpus into valid records at all, without writing anything. It
calls ``discover`` once, then ``fingerprint`` before ``parse`` for every
discovered source in deterministic order (AC-6), and distinguishes source
violations (the adapter completed and found bad source data) from adapter
exceptions (the adapter implementation failed, AC-7). Either kind makes the
command exit 1; an unusable corpus root exits 3. No record or manifest is
written, and the report carries no projected write state or output path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from decision_memory.application.adapter import (
    EXIT_CORPUS_INVALID,
    EXIT_ERROR,
    EXIT_OK,
    AdapterFailure,
    DiscoveryResult,
    SourceAdapter,
    exception_message,
)
from decision_memory.domain.records import Severity, Violation


@dataclass(frozen=True)
class SourceValidationResult:
    """One discovered source's corpus validation outcome.

    ``kind`` is ``ok`` (a valid record was produced), ``violation`` (the
    adapter completed but found bad source data, AC-7), or ``exception`` (the
    adapter raised, AC-8). A violation carries its violations with stable rule
    ids; an exception carries the failed operation plus exception type and
    message.
    """

    id: str
    kind: str
    violations: list[Violation] = field(default_factory=list)
    failure: AdapterFailure | None = None


@dataclass(frozen=True)
class CorpusValidationOutcome:
    """The full result of a write free corpus validation run.

    ``corpus_error`` is set (exit 3) when the root is not a directory or the
    adapter reports its required layout missing. ``discovery_failure`` is set
    (exit 1) when ``discover`` raises; no source operation runs after it.
    """

    exit_code: int
    adapter_id: str
    adapter_version: str
    discovered: DiscoveryResult
    results: list[SourceValidationResult]
    corpus_error: str | None = None
    discovery_failure: AdapterFailure | None = None


def validate_corpus(
    corpus_root: Path, adapter: SourceAdapter
) -> CorpusValidationOutcome:
    """Validate an adapter against a corpus without writing anything (AC-6)."""
    if not corpus_root.is_dir():
        return CorpusValidationOutcome(
            exit_code=EXIT_CORPUS_INVALID,
            adapter_id=adapter.adapter_id,
            adapter_version=adapter.adapter_version,
            discovered=DiscoveryResult([], [], []),
            results=[],
            corpus_error="corpus path does not exist or is not a directory",
        )
    try:
        discovery = adapter.discover(corpus_root)
    except Exception as exc:  # noqa: BLE001 - discover stops the run (AC-8)
        return CorpusValidationOutcome(
            exit_code=EXIT_ERROR,
            adapter_id=adapter.adapter_id,
            adapter_version=adapter.adapter_version,
            discovered=DiscoveryResult([], [], []),
            results=[],
            discovery_failure=AdapterFailure(
                "discover", type(exc).__name__, exception_message(exc)
            ),
        )
    if discovery.corpus_error is not None:
        return CorpusValidationOutcome(
            exit_code=EXIT_CORPUS_INVALID,
            adapter_id=adapter.adapter_id,
            adapter_version=adapter.adapter_version,
            discovered=discovery,
            results=[],
            corpus_error=discovery.corpus_error,
        )
    results: list[SourceValidationResult] = []
    for spec in discovery.specs:
        try:
            adapter.fingerprint(spec)
        except Exception as exc:  # noqa: BLE001 - parse is skipped (AC-8)
            results.append(
                SourceValidationResult(
                    id=spec.id,
                    kind="exception",
                    failure=AdapterFailure(
                        "fingerprint", type(exc).__name__, exception_message(exc)
                    ),
                )
            )
            continue
        try:
            result = adapter.parse(spec)
        except Exception as exc:  # noqa: BLE001 - the source stops here (AC-8)
            results.append(
                SourceValidationResult(
                    id=spec.id,
                    kind="exception",
                    failure=AdapterFailure(
                        "parse", type(exc).__name__, exception_message(exc)
                    ),
                )
            )
            continue
        violations = result.violations
        kind = (
            "violation"
            if any(v.severity == Severity.ERROR for v in violations)
            else "ok"
        )
        results.append(
            SourceValidationResult(id=spec.id, kind=kind, violations=violations)
        )
    exit_code = EXIT_ERROR if any(r.kind != "ok" for r in results) else EXIT_OK
    return CorpusValidationOutcome(
        exit_code=exit_code,
        adapter_id=adapter.adapter_id,
        adapter_version=adapter.adapter_version,
        discovered=discovery,
        results=results,
    )
