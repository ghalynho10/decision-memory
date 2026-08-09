"""Application: the source adapter protocol and the adapt use case.

The protocol is declared here so infrastructure implements it inward: a source
format adapter exposes discover, parse, and fingerprint. The use case
orchestrates a full adapt run, discovery, parsing, validation, incremental
writing against a manifest, and the fixed exit codes from spec 0003. It uses
only the standard library; YAML record writing lives in infrastructure.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from decision_memory.application.canonical import (
    SourceReference,
    entry_digest,
    normalize_field_sources,
    record_digest,
)
from decision_memory.domain.records import (
    CanonicalDecisionRecord,
    Severity,
    Violation,
)

# The default output directory lives inside the corpus, a dot directory so it
# is unlikely to collide with real content (spec 0003).
DEFAULT_RECORDS_DIR = ".decision-memory/records"

# Exit codes fixed by spec 0003, matching the vocabulary spec 0002 set for
# validate. Code 2 is reserved by Click and not produced here.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CORPUS_INVALID = 3

# The built in adapter's selector name (spec 0005 AC-4): the default when no
# adapter option or config value is given. It contains a hyphen, so it cannot
# collide with a valid Python module name (AC-2).
BUILTIN_ADAPTER_ID = "jsmastery-specs"


class SourceAdapter(Protocol):
    """A source format adapter: identity, version, discover, parse, fingerprint.

    ``adapter_id`` and ``adapter_version`` are read only nonempty strings
    naming the implementation and its version; the version participates in the
    manifest and the adapter's fingerprints (spec 0005 AC-1, AC-15). Methods
    never raise for unadaptable sources; they return structured results that
    name what could not be adapted and why.
    """

    @property
    def adapter_id(self) -> str: ...

    @property
    def adapter_version(self) -> str: ...

    def discover(self, corpus_root: Path) -> DiscoveryResult: ...
    def parse(self, spec: DiscoveredSpec) -> AdaptationResult: ...
    def fingerprint(self, spec: DiscoveredSpec) -> str: ...


# The narrow writer port: a callable that writes one canonical record to a
# path. Infrastructure implements it; the use case takes it as a parameter so
# the application never imports infrastructure and a run can be tested without
# touching the filesystem (AGENTS.md: outer layers depend inward). cli.py, the
# composition root, wires the concrete YAML writer.
RecordWriter = Callable[[CanonicalDecisionRecord, Path], None]


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
    """Everything discovery found: adaptable specs, skips, and collisions.

    ``corpus_error`` is set when the corpus root itself does not match the
    adapter's required internal layout (for example ``docs/specs/`` is absent),
    naming the missing structure (spec 0005 AC-20). When it is set, ``specs``
    is empty and the run maps the error to exit code 3.
    """

    specs: list[DiscoveredSpec]
    skipped: list[SkippedSource]
    collisions: list[Collision]
    corpus_error: str | None = None


@dataclass(frozen=True)
class AdaptationResult:
    """The outcome of adapting one spec.

    ``record`` is None when the spec could not be adapted at all.
    ``violations`` holds every rule the adapter emitted plus what ``validate``
    returns for the built record. ``attempted_fields`` names fields with a
    defined source section that turned out absent or empty.
    ``field_sources`` maps each populated canonical value path to the exact
    original source locations that produced it, per the grammar and path list
    in spec 0007 (AC-2). Every populated chunkable leaf, the title, and a
    populated supersedes value must name at least one source.
    """

    record: CanonicalDecisionRecord | None
    violations: list[Violation]
    attempted_fields: frozenset[str]
    unresolved_mention_count: int
    fingerprint: str
    field_sources: dict[str, list[SourceReference]]


@dataclass(frozen=True)
class ManifestEntry:
    """One record's row in the manifest."""

    id: str
    fingerprint: str
    contributing_files: list[str]
    record_path: str
    record_digest: str
    entry_digest: str
    field_sources: dict[str, list[SourceReference]]


@dataclass(frozen=True)
class Manifest:
    """The manifest written to the output directory each non dry run.

    ``schema_version`` is the adapter output manifest grammar version, fixed
    at 2 by spec 0007 AC-2. ``source_root_hint`` is the absolute resolved
    corpus root at adapt time, informative and allowed not to resolve later
    (AC-19).
    """

    schema_version: int = 2
    adapter_version: str = ""
    generated_at: str = ""
    source_root_hint: str = ""
    entries: list[ManifestEntry] = field(default_factory=list)
    skipped: list[SkippedSource] = field(default_factory=list)
    collisions: list[Collision] = field(default_factory=list)


@dataclass(frozen=True)
class AdapterFailure:
    """An adapter operation raised while running, stopping that operation.

    Distinct from a source violation: a violation means the adapter completed
    and found bad source data, an exception means the adapter implementation
    itself failed (spec 0005 AC-7). ``operation`` is one of ``discover``,
    ``fingerprint``, or ``parse``.
    """

    operation: str
    exception_type: str
    message: str


@dataclass(frozen=True)
class RecordOutcome:
    """What one adapt run did with a spec's record.

    ``failure`` is set when the adapter raised instead of returning a result;
    a failed source carries either violations (adapter completed, record
    invalid) or a failure (adapter raised), never both.
    """

    id: str
    state: str
    fingerprint: str
    violations: list[Violation] = field(default_factory=list)
    failure: AdapterFailure | None = None


@dataclass(frozen=True)
class AdaptOutcome:
    """The full result of an adapt run, plus the exit code.

    ``adapter_id`` and ``adapter_version`` are the loaded adapter's identity
    for the report. ``corpus_error`` carries the adapter's message when the
    corpus root lacks its required layout (exit code 3). ``failure`` carries a
    fatal adapter failure such as a ``discover`` exception (exit code 1).
    ``manifest_warning`` carries a note when the previous manifest could not
    support incremental skip decisions, so every record was rewritten.
    """

    exit_code: int
    output_dir: Path
    dry_run: bool
    discovered: DiscoveryResult
    records: list[RecordOutcome]
    generated_at: str
    adapter_id: str = ""
    adapter_version: str = ""
    corpus_error: str | None = None
    failure: AdapterFailure | None = None
    manifest_warning: str | None = None


def adapt_corpus(
    corpus_root: Path,
    adapter: SourceAdapter,
    writer: RecordWriter,
    output: Path | None = None,
    dry_run: bool = False,
) -> AdaptOutcome:
    """Run the full adapt pipeline for a corpus and return the outcome.

    Exits 0 when every discovered spec produced a valid record or was
    unchanged, 1 when at least one failed to produce a valid record or an
    adapter operation raised, and 3 when the corpus path is not a directory or
    the adapter reports its required layout is missing via a discovery corpus
    error. The adapter identity and version come from the adapter itself; the
    manifest version is ``adapter.adapter_version`` (AC-1, AC-15). In a dry
    run the whole run and its report happen but nothing is written. The
    concrete writer is injected from the composition root, so this use case
    never touches infrastructure or the filesystem itself.
    """
    output_dir = (output or corpus_root / DEFAULT_RECORDS_DIR).resolve()
    if not corpus_root.is_dir():
        return AdaptOutcome(
            exit_code=EXIT_CORPUS_INVALID,
            output_dir=output_dir,
            dry_run=dry_run,
            discovered=DiscoveryResult([], [], []),
            records=[],
            generated_at="",
            adapter_id=adapter.adapter_id,
            adapter_version=adapter.adapter_version,
            corpus_error="corpus path does not exist or is not a directory",
        )
    try:
        discovery = adapter.discover(corpus_root)
    except Exception as exc:  # noqa: BLE001 - adapter execution failure, AC-9
        return AdaptOutcome(
            exit_code=EXIT_ERROR,
            output_dir=output_dir,
            dry_run=dry_run,
            discovered=DiscoveryResult([], [], []),
            records=[],
            generated_at="",
            adapter_id=adapter.adapter_id,
            adapter_version=adapter.adapter_version,
            failure=AdapterFailure(
                "discover", type(exc).__name__, exception_message(exc)
            ),
        )
    if discovery.corpus_error is not None:
        return AdaptOutcome(
            exit_code=EXIT_CORPUS_INVALID,
            output_dir=output_dir,
            dry_run=dry_run,
            discovered=discovery,
            records=[],
            generated_at="",
            adapter_id=adapter.adapter_id,
            adapter_version=adapter.adapter_version,
            corpus_error=discovery.corpus_error,
        )
    generated_at = datetime.now(UTC).isoformat()
    manifest_path = output_dir / "manifest.json"
    previous, manifest_warning = _load_previous_manifest(manifest_path)

    records: list[RecordOutcome] = []
    entries: list[ManifestEntry] = []
    writes: list[tuple[DiscoveredSpec, AdaptationResult]] = []
    for spec in discovery.specs:
        try:
            fingerprint = adapter.fingerprint(spec)
        except Exception as exc:  # noqa: BLE001 - parse is skipped (AC-8)
            records.append(
                RecordOutcome(
                    id=spec.id,
                    state="failed",
                    fingerprint="",
                    failure=AdapterFailure(
                        "fingerprint", type(exc).__name__, exception_message(exc)
                    ),
                )
            )
            continue
        try:
            result = adapter.parse(spec)
        except Exception as exc:  # noqa: BLE001 - the source stops here (AC-8)
            records.append(
                RecordOutcome(
                    id=spec.id,
                    state="failed",
                    fingerprint=fingerprint,
                    failure=AdapterFailure(
                        "parse", type(exc).__name__, exception_message(exc)
                    ),
                )
            )
            continue
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
        assert result.record is not None
        contributing_files = [
            path.relative_to(spec.corpus_root).as_posix()
            for path in spec.contributing_files
        ]
        record_path = f"{spec.id}.md"
        digest = record_digest(result.record)
        entries.append(
            ManifestEntry(
                id=spec.id,
                fingerprint=fingerprint,
                contributing_files=contributing_files,
                record_path=record_path,
                record_digest=digest,
                entry_digest=entry_digest(
                    record_id=spec.id,
                    fingerprint=fingerprint,
                    contributing_files=contributing_files,
                    record_path=record_path,
                    record_digest_value=digest,
                    field_sources=result.field_sources,
                ),
                field_sources=result.field_sources,
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
                writer(result.record, output_dir / f"{spec.id}.md")
        manifest = Manifest(
            adapter_version=adapter.adapter_version,
            generated_at=generated_at,
            source_root_hint=corpus_root.resolve().as_posix(),
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
        adapter_id=adapter.adapter_id,
        adapter_version=adapter.adapter_version,
        manifest_warning=manifest_warning,
    )


def exception_message(exc: Exception) -> str:
    """A short message for reporting; empty when the exception carries none."""
    message = str(exc)
    return message if message else type(exc).__name__


def _has_errors(violations: list[Violation]) -> bool:
    return any(v.severity == Severity.ERROR for v in violations)


def _load_previous_manifest(manifest_path: Path) -> tuple[dict[str, str], str | None]:
    """Map of record id to fingerprint from a prior manifest, plus a warning.

    The output manifest schema version must be exactly 2. An older version 1
    manifest (or one with no version) cannot support incremental skip
    decisions, so the run treats it as having no previous fingerprints, every
    record is rewritten into the new schema, and a warning explains why
    (spec 0007 AC-2, the one breaking change).
    """
    if not manifest_path.is_file():
        return {}, None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, None
    if not isinstance(data, dict) or data.get("schema_version") != 2:
        return {}, (
            "previous manifest is not schema version 2; "
            "every record is being rewritten (run adapt again to rebuild it)"
        )
    entries = data.get("entries", [])
    return (
        {
            str(entry.get("id", "")): str(entry.get("fingerprint", ""))
            for entry in entries
            if isinstance(entry, dict)
        },
        None,
    )


def _write_manifest(path: Path, manifest: Manifest) -> None:
    """Write the manifest as JSON with two space indent, entries by id."""
    data = {
        "schema_version": manifest.schema_version,
        "adapter_version": manifest.adapter_version,
        "generated_at": manifest.generated_at,
        "source_root_hint": manifest.source_root_hint,
        "entries": [
            {
                "id": entry.id,
                "fingerprint": entry.fingerprint,
                "contributing_files": entry.contributing_files,
                "record_path": entry.record_path,
                "record_digest": entry.record_digest,
                "entry_digest": entry.entry_digest,
                "field_sources": {
                    path: [{"path": ref.path, "section": ref.section} for ref in refs]
                    for path, refs in normalize_field_sources(
                        entry.field_sources
                    ).items()
                },
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
