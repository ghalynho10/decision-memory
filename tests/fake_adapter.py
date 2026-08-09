"""A configurable fake adapter for runtime loading and validation tests.

The same class serves the adapt run, corpus validation, and runtime loader
tests. Every failure mode the spec names is injectable: a corpus format error
(AC-20), a discover exception, and per source fingerprint or parse exceptions
(AC-8). A corpus is a mapping of spec id to a small data dict with ``title``,
``chosen``, ``why``, and ``evidence`` keys, which parse into a valid canonical
record when the cited evidence exists on disk.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from decision_memory.application.adapter import (
    AdaptationResult,
    DiscoveredSpec,
    DiscoveryResult,
    SkippedSource,
)
from decision_memory.domain.records import (
    CanonicalDecisionRecord,
    Decision,
    Evidence,
    EvidenceKind,
    Status,
    ValidationContext,
)
from decision_memory.domain.validation import validate


class FakeAdapter:
    """An in memory adapter whose behavior and failures are fully injectable."""

    def __init__(
        self,
        *,
        adapter_id: str = "fake",
        adapter_version: str = "1",
        corpus: dict[str, dict[str, object]] | None = None,
        skipped: list[SkippedSource] | None = None,
        corpus_error: str | None = None,
        discover_error: Exception | None = None,
        fingerprint_errors: dict[str, Exception] | None = None,
        parse_errors: dict[str, Exception] | None = None,
    ) -> None:
        self._adapter_id = adapter_id
        self._adapter_version = adapter_version
        self._corpus = corpus or {}
        self._skipped = skipped or []
        self._corpus_error = corpus_error
        self._discover_error = discover_error
        self._fingerprint_errors = fingerprint_errors or {}
        self._parse_errors = parse_errors or {}

    @property
    def adapter_id(self) -> str:
        return self._adapter_id

    @property
    def adapter_version(self) -> str:
        return self._adapter_version

    def discover(self, corpus_root: Path) -> DiscoveryResult:
        if self._discover_error is not None:
            raise self._discover_error
        if self._corpus_error is not None:
            return DiscoveryResult([], [], [], corpus_error=self._corpus_error)
        specs = [
            DiscoveredSpec(
                id=spec_id,
                root=corpus_root / "fake" / spec_id,
                corpus_root=corpus_root,
                contributing_files=[corpus_root / "fake" / spec_id / "source.md"],
            )
            for spec_id in sorted(self._corpus)
        ]
        return DiscoveryResult(specs, self._skipped, [])

    def fingerprint(self, spec: DiscoveredSpec) -> str:
        if spec.id in self._fingerprint_errors:
            raise self._fingerprint_errors[spec.id]
        return hashlib.sha256(f"{self._adapter_version}:{spec.id}".encode()).hexdigest()

    def parse(self, spec: DiscoveredSpec) -> AdaptationResult:
        if spec.id in self._parse_errors:
            raise self._parse_errors[spec.id]
        data = self._corpus.get(spec.id, {})
        record = _record_from_data(spec.id, data)
        context = ValidationContext(existing_paths=_existing_paths(data))
        return AdaptationResult(
            record=record,
            violations=validate(record, context),
            attempted_fields=frozenset(),
            unresolved_mention_count=0,
            fingerprint=self.fingerprint(spec),
        )


def fake_source(tmp_path: Path, spec_id: str, target: str = "source.md") -> Path:
    """Write the file a fake discovered spec's evidence points at."""
    evidence = tmp_path / "fake" / spec_id / target
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text("source", encoding="utf-8")
    return evidence


def _record_from_data(spec_id: str, data: dict[str, object]) -> CanonicalDecisionRecord:
    return CanonicalDecisionRecord(
        id=spec_id,
        title=str(data.get("title") or ""),
        status=Status.ACCEPTED,
        decision=Decision(chosen=str(data.get("chosen") or "")),
        why=[str(item) for item in data.get("why", [])],
        evidence=[Evidence(kind=EvidenceKind.FILE, target=str(data["evidence"]))]
        if data.get("evidence")
        else [],
    )


def _existing_paths(data: dict[str, object]) -> frozenset[str]:
    if not data.get("evidence"):
        return frozenset()
    return frozenset({str(data["evidence"])})
