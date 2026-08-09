"""Infrastructure: strict loading of the adapter conformance manifest.

Spec 0006 AC-2 and AC-3: the manifest is a strict versioned YAML document.
Loading happens in three phases with three rule ids: ``manifest.load`` (read
and safe YAML), ``manifest.schema`` (version, fields, types, categories, and
required coverage), and ``manifest.paths`` (every declared path exists, is
contained, and is not a symlink). Every failure names the failing field or
path and is raised as ``ConformanceManifestError`` for the CLI to report as
the sole failed check and exit ``1``.

Expected records are parsed during loading (through the existing record
reader), so the application engine never reads those files and never depends
on this module.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from decision_memory.application.conformance import (
    CollisionExpectation,
    ConformanceCase,
    ConformanceCategory,
    ConformanceManifest,
    DiscoveryExpectation,
    ResultExpectation,
    SkipExpectation,
    SourceExpectation,
    ViolationExpectation,
)
from decision_memory.domain.records import (
    CanonicalDecisionRecord,
    Severity,
    ValidationContext,
)
from decision_memory.domain.validation import validate
from decision_memory.infrastructure.file_reader import parse_record_file

# The one supported schema version (AC-2).
SCHEMA_VERSION = 1


class ConformanceManifestError(Exception):
    """A manifest loading failure with the fixed rule id it maps to."""

    def __init__(self, rule: str, detail: str) -> None:
        super().__init__(detail)
        self.rule = rule
        self.detail = detail


@dataclass(frozen=True)
class _ResolvedSource:
    """A source expectation with its paths resolved and record loaded."""

    expectation: SourceExpectation
    existing_paths: frozenset[str]


# ---------------------------------------------------------------------------
# Pydantic models over the YAML mapping (framework code lives here only)
# ---------------------------------------------------------------------------


class ViolationExpectationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Severity
    rule: str
    field: str | None = None


class ResultExpectationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    record: str | None
    attempted_fields: list[str]
    unresolved_mention_count: int = Field(ge=0)
    violations: list[ViolationExpectationModel]


class SourceExpectationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    root: str
    contributing_files: list[str]
    required_files: list[str]
    result: ResultExpectationModel


class SkipExpectationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str


class CollisionExpectationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    paths: list[str]
    used: str


class DiscoveryExpectationModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[SourceExpectationModel]
    skips: list[SkipExpectationModel]
    collisions: list[CollisionExpectationModel]


class CaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    category: ConformanceCategory
    corpus: str
    subject_path: str | None = None
    target_fields: list[str] | None = None
    expect: DiscoveryExpectationModel


class ManifestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    cases: list[CaseModel]


# ---------------------------------------------------------------------------
# Canonical field path vocabulary (spec 0002 fields, dotted with [N] indexes)
# ---------------------------------------------------------------------------

_LEAF_FIELDS = frozenset(
    {
        "",
        "id",
        "title",
        "status",
        "date",
        "body",
        "context",
        "context.problem",
        "context.triggering_change",
        "decision",
        "decision.chosen",
        "decision.alternatives",
        "why",
        "rationale_summary",
        "consequences",
        "consequences.positive",
        "consequences.negative",
        "evidence",
        "evidence.kind",
        "evidence.target",
        "evidence.note",
        "tags",
        "supersedes",
    }
)

_INDEXED_FIELDS = frozenset(
    {
        "evidence[i]",
        "evidence[i].kind",
        "evidence[i].target",
        "evidence[i].note",
        "decision.alternatives[i]",
        "decision.alternatives[i].title",
        "decision.alternatives[i].rejection_reason",
    }
)

_INDEX_RE = re.compile(r"^\[(\d+)\]$")


def _normalize_indexed(field: str) -> str:
    """Replace list index brackets with [i] so indexed forms match the set."""
    return re.sub(r"\[\d+\]", "[i]", field)


def is_canonical_field_path(field: str) -> bool:
    """Whether a manifest declared field is a known canonical field path."""
    if field in _LEAF_FIELDS:
        return True
    return _normalize_indexed(field) in _INDEXED_FIELDS


# ---------------------------------------------------------------------------
# Semantic cross field validation (manifest.schema)
# ---------------------------------------------------------------------------


def _check_schema(model: ManifestModel) -> None:
    if not model.cases:
        raise ConformanceManifestError("manifest.schema", "cases must not be empty")
    case_ids: set[str] = set()
    total_required_files = 0
    for case in model.cases:
        if not case.id.strip():
            raise ConformanceManifestError(
                "manifest.schema", "a case id must not be empty"
            )
        if case.id in case_ids:
            raise ConformanceManifestError(
                "manifest.schema", f"duplicate case id {case.id!r}"
            )
        case_ids.add(case.id)
        _check_case(case)
        for source in case.expect.sources:
            total_required_files += len(source.required_files)
    if total_required_files == 0:
        raise ConformanceManifestError(
            "manifest.schema", "at least one required file must be declared (AC-8)"
        )


def _check_case(case: CaseModel) -> None:
    subject_required = case.category in (
        ConformanceCategory.SKIP,
        ConformanceCategory.WRONG_HEADING,
        ConformanceCategory.MISSING_REQUIRED_FIELD,
    )
    subject_forbidden = case.category in (
        ConformanceCategory.VALID,
        ConformanceCategory.COLLISION,
    )
    if subject_required and case.subject_path is None:
        raise ConformanceManifestError(
            "manifest.schema", f"case {case.id!r} requires subject_path"
        )
    if subject_forbidden and case.subject_path is not None:
        raise ConformanceManifestError(
            "manifest.schema", f"case {case.id!r} forbids subject_path"
        )
    target_required = case.category in (
        ConformanceCategory.WRONG_HEADING,
        ConformanceCategory.MISSING_REQUIRED_FIELD,
    )
    if target_required:
        if not case.target_fields:
            raise ConformanceManifestError(
                "manifest.schema", f"case {case.id!r} requires nonempty target_fields"
            )
        for target in case.target_fields:
            if not is_canonical_field_path(target):
                raise ConformanceManifestError(
                    "manifest.schema",
                    f"case {case.id!r} target field {target!r} "
                    "is not a canonical field path",
                )
    elif case.target_fields:
        raise ConformanceManifestError(
            "manifest.schema", f"case {case.id!r} forbids target_fields"
        )

    sources = case.expect.sources
    source_ids: set[str] = set()
    for source in sources:
        if not source.id.strip():
            raise ConformanceManifestError(
                "manifest.schema", f"case {case.id!r} has a source with an empty id"
            )
        if source.id in source_ids:
            raise ConformanceManifestError(
                "manifest.schema",
                f"case {case.id!r} duplicate source id {source.id!r}",
            )
        source_ids.add(source.id)
        if not source.contributing_files:
            raise ConformanceManifestError(
                "manifest.schema", f"source {source.id!r} needs contributing_files"
            )
        _check_nonempty_path(source.root, "source root", source.id)
        _reject_duplicate_paths(
            source.contributing_files, "contributing file", source.id
        )
        _reject_duplicate_paths(source.required_files, "required file", source.id)
        for required in source.required_files:
            if required not in source.contributing_files:
                raise ConformanceManifestError(
                    "manifest.schema",
                    f"source {source.id!r} required file {required!r} "
                    "is not a contributing file",
                )
        _check_result(source.result, source.id)

    skips = case.expect.skips
    if case.category == ConformanceCategory.SKIP and (
        case.subject_path is None
        or skips.count(SkipExpectationModel(path=case.subject_path)) != 1
    ):
        raise ConformanceManifestError(
            "manifest.schema",
            f"skip case {case.id!r} subject must appear exactly once in skips",
        )
    _reject_duplicate_paths([skip.path for skip in skips], "skip path", case.id)

    collisions = case.expect.collisions
    if case.category == ConformanceCategory.COLLISION and not collisions:
        raise ConformanceManifestError(
            "manifest.schema", f"collision case {case.id!r} needs a collision"
        )
    for collision in collisions:
        if not collision.id.strip():
            raise ConformanceManifestError(
                "manifest.schema", f"case {case.id!r} has a collision with an empty id"
            )
        if len(collision.paths) < 2:
            raise ConformanceManifestError(
                "manifest.schema",
                f"collision {collision.id!r} needs at least two paths",
            )
        if collision.used not in collision.paths:
            raise ConformanceManifestError(
                "manifest.schema",
                f"collision {collision.id!r} used path is not one of its paths",
            )
        _reject_duplicate_paths(collision.paths, "collision path", collision.id)

    if case.category == ConformanceCategory.VALID:
        valid_source = next(
            (source for source in sources if source.result.record is not None),
            None,
        )
        if valid_source is None:
            raise ConformanceManifestError(
                "manifest.schema",
                f"valid case {case.id!r} needs a source with a nonnull expected record",
            )


def _check_nonempty_path(path: str, what: str, owner: str) -> None:
    if not path.strip():
        raise ConformanceManifestError(
            "manifest.schema", f"{owner!r} {what} must not be empty"
        )


def _reject_duplicate_paths(paths: list[str], what: str, owner: str) -> None:
    seen: set[str] = set()
    for path in paths:
        if not path.strip():
            raise ConformanceManifestError(
                "manifest.schema", f"{owner!r} {what} must not be empty"
            )
        if path in seen:
            raise ConformanceManifestError(
                "manifest.schema", f"{owner!r} duplicate {what} {path!r}"
            )
        seen.add(path)


def _check_result(result: ResultExpectationModel, source_id: str) -> None:
    for field in result.attempted_fields:
        if not is_canonical_field_path(field):
            raise ConformanceManifestError(
                "manifest.schema",
                f"source {source_id!r} attempted field {field!r} is not canonical",
            )
    for violation in result.violations:
        if not violation.rule.strip():
            raise ConformanceManifestError(
                "manifest.schema",
                f"source {source_id!r} has a violation with an empty rule",
            )
        if violation.field is not None and not is_canonical_field_path(violation.field):
            raise ConformanceManifestError(
                "manifest.schema",
                f"source {source_id!r} violation field "
                f"{violation.field!r} is not canonical",
            )


# ---------------------------------------------------------------------------
# Path resolution and expected record loading (manifest.paths)
# ---------------------------------------------------------------------------


def load_conformance_manifest(path: Path) -> ConformanceManifest:
    """Load, validate, and resolve one conformance manifest (AC-2, AC-3)."""
    manifest_dir = path.resolve().parent
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:  # noqa: BLE001 - missing or unreadable manifest
        message = str(exc) if str(exc) else type(exc).__name__
        raise ConformanceManifestError(
            "manifest.load", f"cannot read manifest {path}: {message}"
        ) from None
    if path.is_symlink():
        raise ConformanceManifestError(
            "manifest.paths", "manifest must not be a symlink"
        )
    try:
        data = yaml.safe_load(text)
    except Exception as exc:  # noqa: BLE001 - YAML failure
        message = str(exc) if str(exc) else type(exc).__name__
        raise ConformanceManifestError("manifest.load", message) from None
    if not isinstance(data, dict):
        raise ConformanceManifestError(
            "manifest.schema", "manifest must be a YAML mapping"
        )
    try:
        model = ManifestModel.model_validate(data)
    except ValidationError as exc:
        raise ConformanceManifestError(
            "manifest.schema", _format_validation_error(exc)
        ) from None
    _check_schema(model)
    cases = _resolve_cases(model, manifest_dir)
    return ConformanceManifest(schema_version=SCHEMA_VERSION, cases=cases)


def _format_validation_error(exc: ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "invalid manifest"
    first = errors[0]
    location = ".".join(str(part) for part in first.get("loc", ()))
    message = str(first.get("msg", "invalid"))
    return f"{location}: {message}"


def _resolve_cases(
    model: ManifestModel, manifest_dir: Path
) -> tuple[ConformanceCase, ...]:
    resolved: list[ConformanceCase] = []
    for case_model in model.cases:
        corpus = _resolve_contained(manifest_dir, case_model.corpus, "case corpus")
        if not corpus.is_dir():
            raise ConformanceManifestError(
                "manifest.paths",
                f"case corpus {case_model.corpus!r} is not a directory",
            )
        _scan_symlinks(corpus, f"case corpus {case_model.corpus!r}")

        subject_path: Path | None = None
        if case_model.subject_path is not None:
            subject_path = Path(case_model.subject_path)
            _check_contained(
                corpus, subject_path, f"case {case_model.id!r} subject_path"
            )
            if not (corpus / subject_path).exists():
                raise ConformanceManifestError(
                    "manifest.paths",
                    f"case {case_model.id!r} subject "
                    f"{case_model.subject_path!r} does not exist",
                )

        sources: list[SourceExpectation] = []
        for source_model in case_model.expect.sources:
            sources.append(
                _resolve_source(
                    corpus,
                    source_model,
                    case_model.id,
                    case_model.category,
                    manifest_dir,
                )
            )
        skips = tuple(
            SkipExpectation(
                path=_resolve_contained_path(
                    corpus, skip.path, f"case {case_model.id!r} skip"
                )
            )
            for skip in case_model.expect.skips
        )
        collisions = tuple(
            CollisionExpectation(
                id=collision.id,
                paths=tuple(
                    _resolve_contained_path(corpus, p, f"collision {collision.id!r}")
                    for p in collision.paths
                ),
                used=_resolve_contained_path(
                    corpus, collision.used, f"collision {collision.id!r} used"
                ),
            )
            for collision in case_model.expect.collisions
        )
        resolved.append(
            ConformanceCase(
                id=case_model.id,
                category=case_model.category,
                corpus=corpus,
                subject_path=subject_path,
                target_fields=frozenset(case_model.target_fields or []),
                expect=DiscoveryExpectation(
                    sources=tuple(sources), skips=skips, collisions=collisions
                ),
            )
        )
    return tuple(resolved)


def _resolve_source(
    corpus: Path,
    source_model: SourceExpectationModel,
    case_id: str,
    category: ConformanceCategory,
    manifest_dir: Path,
) -> SourceExpectation:
    source_id = source_model.id
    root = _resolve_contained_path(
        corpus, source_model.root, f"source {source_id!r} root"
    )
    if not (corpus / root).exists():
        raise ConformanceManifestError(
            "manifest.paths",
            f"source {source_id!r} root {source_model.root!r} does not exist",
        )
    contributing = tuple(
        _resolve_contained_path(corpus, p, f"source {source_id!r} contributing file")
        for p in source_model.contributing_files
    )
    for contrib in contributing:
        if not (corpus / contrib).exists():
            raise ConformanceManifestError(
                "manifest.paths",
                f"source {source_id!r} contributing file {contrib!r} does not exist",
            )
    required = tuple(
        _resolve_contained_path(corpus, p, f"source {source_id!r} required file")
        for p in source_model.required_files
    )
    for required_path in required:
        full = corpus / required_path
        if not full.is_file() or full.is_symlink():
            raise ConformanceManifestError(
                "manifest.paths",
                f"source {source_id!r} required file "
                f"{required_path!r} is not a regular file",
            )
        try:
            full.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise ConformanceManifestError(
                "manifest.paths",
                f"source {source_id!r} required file "
                f"{required_path!r} is not valid UTF-8",
            ) from None
    existing_set = frozenset(_corpus_files(corpus))
    result = _resolve_result(
        source_model.result,
        source_id,
        case_id,
        category,
        manifest_dir,
        existing_set,
    )
    return SourceExpectation(
        id=source_id,
        root=root,
        contributing_files=contributing,
        required_files=required,
        result=result,
    )


def _corpus_files(corpus: Path) -> list[str]:
    """Every regular file in a case corpus, as a corpus relative POSIX path."""
    files: list[str] = []
    for current, _, names in os.walk(corpus):
        directory = Path(current)
        for name in names:
            entry = directory / name
            if entry.is_file() and not entry.is_symlink():
                files.append(entry.relative_to(corpus).as_posix())
    return files


def _resolve_result(
    result_model: ResultExpectationModel,
    source_id: str,
    case_id: str,
    category: ConformanceCategory,
    manifest_dir: Path,
    existing_paths: frozenset[str],
) -> ResultExpectation:
    record: CanonicalDecisionRecord | None = None
    if result_model.record is not None:
        record = _load_expected_record(
            manifest_dir, result_model.record, source_id, case_id
        )
    attempted = frozenset(result_model.attempted_fields)
    violations = tuple(
        ViolationExpectation(
            severity=violation.severity,
            rule=violation.rule,
            field=violation.field if violation.field is not None else "",
        )
        for violation in result_model.violations
    )
    context = ValidationContext(
        attempted_fields=attempted,
        existing_paths=existing_paths,
        git_available=False,
        unresolved_mention_count=result_model.unresolved_mention_count,
    )
    if record is not None and category == ConformanceCategory.VALID:
        errors = [
            violation
            for violation in validate(record, context)
            if violation.severity == Severity.ERROR
        ]
        if errors:
            raise ConformanceManifestError(
                "manifest.paths",
                f"expected record {result_model.record!r} for {source_id!r} has error "
                f"violations: {errors[0].rule} {errors[0].field}",
            )
    return ResultExpectation(
        record=record,
        attempted_fields=attempted,
        unresolved_mention_count=result_model.unresolved_mention_count,
        violations=violations,
    )


def _load_expected_record(
    manifest_dir: Path,
    record_path: str,
    source_id: str,
    case_id: str,
) -> CanonicalDecisionRecord:
    relative = _resolve_contained(manifest_dir, record_path, "expected record")
    if not relative.is_file() or relative.is_symlink():
        raise ConformanceManifestError(
            "manifest.paths",
            f"expected record {record_path!r} for {source_id!r} is not a regular file",
        )
    parsed = parse_record_file(relative)
    if parsed.record is None:
        raise ConformanceManifestError(
            "manifest.paths",
            f"expected record {record_path!r} for {source_id!r} "
            "is not a canonical record",
        )
    if parsed.unknown_fields:
        raise ConformanceManifestError(
            "manifest.paths",
            f"expected record {record_path!r} for {source_id!r} "
            f"has unknown canonical fields {sorted(parsed.unknown_fields)}",
        )
    return parsed.record


def _resolve_contained_path(base: Path, value: str, what: str) -> Path:
    """A corpus relative path checked for escape, returning the relative Path."""
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ConformanceManifestError(
            "manifest.paths", f"{what} {value!r} escapes the corpus"
        )
    return relative


def _resolve_contained(base: Path, value: str, what: str) -> Path:
    """Resolve a manifest relative path, rejecting escape and symlink components."""
    relative = _resolve_contained_path(base, value, what)
    resolved = (base / relative).resolve()
    if not _is_within(resolved, base):
        raise ConformanceManifestError(
            "manifest.paths", f"{what} {value!r} escapes the manifest directory"
        )
    _check_no_symlink_components(base, relative, what)
    return resolved


def _check_contained(base: Path, relative: Path, what: str) -> None:
    if relative.is_absolute() or ".." in relative.parts:
        raise ConformanceManifestError(
            "manifest.paths", f"{what} {relative!r} escapes the corpus"
        )


def _is_within(path: Path, base: Path) -> bool:
    try:
        path.relative_to(base)
    except ValueError:
        return False
    return True


def _check_no_symlink_components(base: Path, relative: Path, what: str) -> None:
    current = base
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ConformanceManifestError(
                "manifest.paths", f"{what} {relative!r} has a symlink path component"
            )


def _scan_symlinks(root: Path, what: str) -> None:
    """Reject any symlink entry anywhere in a case corpus (AC-2)."""
    for current, dirs, files in os.walk(root):
        directory = Path(current)
        for name in [*dirs, *files]:
            if (directory / name).is_symlink():
                raise ConformanceManifestError(
                    "manifest.paths",
                    f"{what} contains a symlink at "
                    f"{(directory / name).relative_to(root)}",
                )
        dirs[:] = [name for name in dirs if not (directory / name).is_symlink()]
