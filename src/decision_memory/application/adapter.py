"""Application: the source adapter protocol and the adapt use case.

The protocol is declared here so infrastructure implements it inward: a source
format adapter exposes discover, parse, and fingerprint. The use case
orchestrates a full adapt run, discovery, parsing, validation, incremental
writing against a manifest, and the fixed exit codes from spec 0003. It uses
only the standard library; YAML record writing lives in infrastructure.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from decision_memory.domain.records import (
    CanonicalDecisionRecord,
    Severity,
    Violation,
)
from decision_memory.infrastructure.file_reader import write_record_file

# The default output directory lives inside the corpus, a dot directory so it
# is unlikely to collide with real content (spec 0003).
DEFAULT_RECORDS_DIR = ".decision-memory/records"

# Exit codes fixed by spec 0003, matching the vocabulary spec 0002 set for
# validate. Code 2 is reserved by Click and not produced here.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CORPUS_INVALID = 3


class SourceAdapter(Protocol):
    """A source format adapter: discover, parse, and fingerprint.

    Methods never raise for unadaptable sources; they return structured
    results that name what could not be adapted and why.
    """

    def discover(self, corpus_root: Path) -> DiscoveryResult: ...
    def parse(self, spec: DiscoveredSpec) -> AdaptationResult: ...
    def fingerprint(self, spec: DiscoveredSpec) -> str: ...


@dataclass(frozen=True)
class DiscoveredSpec:
    """One spec directory the adapter found and can adapt."""

    id: str
    root: Path
    corpus_root: Path
    contributing_files: list[Path]


@dataclass(frozen=True)
class SkippedSource:
    """A source that could not be adapted, with the reason."""

    path: Path
    reason: str


@dataclass(frozen=True)
class Collision:
    """Two or more sources deriving the same id, and the one used."""

    id: str
    paths: list[Path]
    used: Path


@dataclass(frozen=True)
class DiscoveryResult:
    """Everything discovery found: adaptable specs, skips, and collisions."""

    specs: list[DiscoveredSpec]
    skipped: list[SkippedSource]
    collisions: list[Collision]


@dataclass(frozen=True)
class AdaptationResult:
    """The outcome of adapting one spec.

    ``record`` is None when the spec could not be adapted at all.
    ``violations`` holds every rule the adapter emitted plus what ``validate``
    returns for the built record. ``attempted_fields`` names fields with a
    defined source section that turned out absent or empty.
    """

    record: CanonicalDecisionRecord | None
    violations: list[Violation]
    attempted_fields: frozenset[str]
    unresolved_mention_count: int
    fingerprint: str


@dataclass(frozen=True)
class ManifestEntry:
    """One record's row in the manifest."""

    id: str
    fingerprint: str
    contributing_files: list[str]
    record_path: str


@dataclass(frozen=True)
class Manifest:
    """The manifest written to the output directory each non dry run."""

    adapter_version: str
    generated_at: str
    entries: list[ManifestEntry]
    skipped: list[SkippedSource]
    collisions: list[Collision]


@dataclass(frozen=True)
class RecordOutcome:
    """What one adapt run did with a spec's record."""

    id: str
    state: str
    fingerprint: str
    violations: list[Violation] = field(default_factory=list)


@dataclass(frozen=True)
class AdaptOutcome:
    """The full result of an adapt run, plus the exit code."""

    exit_code: int
    output_dir: Path
    dry_run: bool
    discovered: DiscoveryResult
    records: list[RecordOutcome]
    generated_at: str


def adapt_corpus(
    corpus_root: Path,
    adapter: SourceAdapter,
    adapter_version: str,
    output: Path | None = None,
    dry_run: bool = False,
) -> AdaptOutcome:
    """Run the full adapt pipeline for a corpus and return the outcome.

    Exits 0 when every discovered spec produced a valid record or was
    unchanged, 1 when at least one failed to produce a valid record, and 3
    when the corpus path does not exist or holds no ``docs/specs/`` directory.
    In a dry run the whole run and its report happen but nothing is written.
    """
    specs_dir = corpus_root / "docs" / "specs"
    if not corpus_root.is_dir() or not specs_dir.is_dir():
        return AdaptOutcome(
            exit_code=EXIT_CORPUS_INVALID,
            output_dir=(output or corpus_root / DEFAULT_RECORDS_DIR).resolve(),
            dry_run=dry_run,
            discovered=DiscoveryResult([], [], []),
            records=[],
            generated_at="",
        )
    output_dir = (output or corpus_root / DEFAULT_RECORDS_DIR).resolve()
    generated_at = datetime.now(UTC).isoformat()
    discovery = adapter.discover(corpus_root)
    manifest_path = output_dir / "manifest.json"
    previous = _load_previous_fingerprints(manifest_path)

    records: list[RecordOutcome] = []
    entries: list[ManifestEntry] = []
    writes: list[tuple[DiscoveredSpec, AdaptationResult]] = []
    for spec in discovery.specs:
        fingerprint = adapter.fingerprint(spec)
        result = adapter.parse(spec)
        if result.record is None or _has_errors(result.violations):
            records.append(
                RecordOutcome(
                    id=spec.id,
                    state="failed",
                    fingerprint=fingerprint,
                    violations=result.violations,
                )
            )
            continue
        previous_fingerprint = previous.get(spec.id)
        record_exists = (output_dir / f"{spec.id}.md").is_file()
        if previous_fingerprint == fingerprint and record_exists:
            state = "unchanged"
        elif spec.id in previous:
            # A matching fingerprint with no file on disk lands here too: the
            # manifest alone cannot say a record is current, or a deleted
            # record would never be restored.
            state = "rewritten"
        else:
            state = "written"
        entries.append(
            ManifestEntry(
                id=spec.id,
                fingerprint=fingerprint,
                contributing_files=[
                    path.relative_to(spec.corpus_root).as_posix()
                    for path in spec.contributing_files
                ],
                record_path=f"{spec.id}.md",
            )
        )
        records.append(
            RecordOutcome(
                id=spec.id,
                state=state,
                fingerprint=fingerprint,
                violations=result.violations,
            )
        )
        if state != "unchanged":
            writes.append((spec, result))

    if not dry_run:
        for spec, result in writes:
            if result.record is not None:
                write_record_file(result.record, output_dir / f"{spec.id}.md")
        manifest = Manifest(
            adapter_version=adapter_version,
            generated_at=generated_at,
            entries=entries,
            skipped=discovery.skipped,
            collisions=discovery.collisions,
        )
        _write_manifest(manifest_path, manifest)

    exit_code = EXIT_ERROR if any(r.state == "failed" for r in records) else EXIT_OK
    return AdaptOutcome(
        exit_code=exit_code,
        output_dir=output_dir,
        dry_run=dry_run,
        discovered=discovery,
        records=records,
        generated_at=generated_at,
    )


def _has_errors(violations: list[Violation]) -> bool:
    return any(v.severity == Severity.ERROR for v in violations)


def _load_previous_fingerprints(manifest_path: Path) -> dict[str, str]:
    """Map of record id to fingerprint from a prior manifest, if any."""
    if not manifest_path.is_file():
        return {}
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    entries = data.get("entries", []) if isinstance(data, dict) else []
    return {
        str(entry.get("id", "")): str(entry.get("fingerprint", ""))
        for entry in entries
        if isinstance(entry, dict)
    }


def _write_manifest(path: Path, manifest: Manifest) -> None:
    """Write the manifest as JSON with two space indent, entries by id."""
    data = {
        "adapter_version": manifest.adapter_version,
        "generated_at": manifest.generated_at,
        "entries": [
            {
                "id": entry.id,
                "fingerprint": entry.fingerprint,
                "contributing_files": entry.contributing_files,
                "record_path": entry.record_path,
            }
            for entry in sorted(manifest.entries, key=lambda entry: entry.id)
        ],
        "skipped": [
            {"path": str(skipped.path), "reason": skipped.reason}
            for skipped in manifest.skipped
        ],
        "collisions": [
            {
                "id": collision.id,
                "paths": [str(path) for path in collision.paths],
                "used": str(collision.used),
            }
            for collision in manifest.collisions
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
