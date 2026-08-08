"""The pure record validator.

`validate` checks a record against the rule table in spec 0002 and returns a
list of violations. It performs no filesystem or git access; all existence
checks use the sets supplied in `ValidationContext`. Rule ids are stable and
matched on by tests and later consumers.
"""

from __future__ import annotations

import re
from datetime import date as calendar_date
from typing import TypeVar

from decision_memory.domain.records import (
    CanonicalDecisionRecord,
    EvidenceKind,
    Severity,
    ValidationContext,
    Violation,
)

_T = TypeVar("_T")

_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SPECS_DIR_PREFIX = "docs/specs/"


def validate(
    record: CanonicalDecisionRecord, context: ValidationContext
) -> list[Violation]:
    """Validate a record against the schema rules and return violations."""
    violations: list[Violation] = []
    _check_required(record, violations)
    _check_id_format(record, violations)
    _check_date_format(record, violations)
    _check_rationale(record, violations)
    _check_alternatives(record, violations)
    _check_supersedes(record, violations)
    _check_evidence(record, context, violations)
    _check_attempted_fields(context, violations)
    _check_unknown_fields(context, violations)
    _check_mentions_unresolved(context, violations)
    _check_git_unavailable(record, context, violations)
    return violations


def _violation(field: str, severity: Severity, rule: str, reason: str) -> Violation:
    return Violation(field=field, severity=severity, rule=rule, reason=reason)


def _is_missing_str(value: str | None) -> bool:
    """A string is missing when absent, empty, or whitespace only."""
    return value is None or value.strip() == ""


def _is_missing_list(value: list[_T] | None) -> bool:
    """A list is missing when absent or empty."""
    return not value


def _check_required(
    record: CanonicalDecisionRecord, violations: list[Violation]
) -> None:
    if _is_missing_str(record.id):
        violations.append(
            _violation("id", Severity.ERROR, "required.missing", "id is required")
        )
    if _is_missing_str(record.title):
        violations.append(
            _violation("title", Severity.ERROR, "required.missing", "title is required")
        )
    status = record.status.value if record.status is not None else None
    if _is_missing_str(status):
        violations.append(
            _violation(
                "status", Severity.ERROR, "required.missing", "status is required"
            )
        )
    chosen = record.decision.chosen if record.decision is not None else None
    if _is_missing_str(chosen):
        violations.append(
            _violation(
                "decision.chosen",
                Severity.ERROR,
                "required.missing",
                "decision.chosen is required",
            )
        )
    if _is_missing_list(record.evidence):
        violations.append(
            _violation(
                "evidence", Severity.ERROR, "required.missing", "evidence is required"
            )
        )
    if record.evidence:
        for index, evidence in enumerate(record.evidence):
            if evidence.kind is None:
                violations.append(
                    _violation(
                        f"evidence[{index}].kind",
                        Severity.ERROR,
                        "required.missing",
                        "evidence kind is required",
                    )
                )
    if record.decision is not None:
        for index, alternative in enumerate(record.decision.alternatives):
            if _is_missing_str(alternative.title):
                violations.append(
                    _violation(
                        f"decision.alternatives[{index}].title",
                        Severity.ERROR,
                        "required.missing",
                        "alternative title is required",
                    )
                )


def _check_id_format(
    record: CanonicalDecisionRecord, violations: list[Violation]
) -> None:
    if record.id is None or _is_missing_str(record.id):
        return
    if _ID_PATTERN.match(record.id) is None:
        violations.append(
            _violation(
                "id",
                Severity.ERROR,
                "id.malformed",
                f"id {record.id!r} does not match the required format",
            )
        )


def _check_date_format(
    record: CanonicalDecisionRecord, violations: list[Violation]
) -> None:
    if record.date is None or _is_missing_str(record.date):
        return
    if _DATE_PATTERN.match(record.date) is None:
        violations.append(
            _violation(
                "date",
                Severity.ERROR,
                "date.malformed",
                f"date {record.date!r} is not a valid YYYY-MM-DD date",
            )
        )
        return
    try:
        calendar_date.fromisoformat(record.date)
    except ValueError:
        violations.append(
            _violation(
                "date",
                Severity.ERROR,
                "date.malformed",
                f"date {record.date!r} is not a real calendar date",
            )
        )


def _check_rationale(
    record: CanonicalDecisionRecord, violations: list[Violation]
) -> None:
    why_populated = any(item is not None and item.strip() != "" for item in record.why)
    summary_populated = (
        record.rationale_summary is not None and record.rationale_summary.strip() != ""
    )
    if not why_populated and not summary_populated:
        violations.append(
            _violation(
                "",
                Severity.ERROR,
                "rationale.missing",
                "at least one of why or rationale_summary must be populated",
            )
        )


def _check_alternatives(
    record: CanonicalDecisionRecord, violations: list[Violation]
) -> None:
    if record.decision is None:
        return
    for index, alternative in enumerate(record.decision.alternatives):
        if _is_missing_str(alternative.rejection_reason):
            violations.append(
                _violation(
                    f"decision.alternatives[{index}].rejection_reason",
                    Severity.WARNING,
                    "alternative.missing_rejection_reason",
                    "alternative has no rejection reason",
                )
            )


def _check_supersedes(
    record: CanonicalDecisionRecord, violations: list[Violation]
) -> None:
    if (
        record.supersedes is not None
        and record.id is not None
        and record.supersedes == record.id
    ):
        violations.append(
            _violation(
                "supersedes",
                Severity.ERROR,
                "supersedes.self_reference",
                "supersedes must not equal this record's own id",
            )
        )


def _target_is_not_normalized(target: str) -> bool:
    """True when a path target is absolute, has a .. segment, or ends in a slash."""
    return (
        target.startswith("/")
        or any(part == ".." for part in target.split("/"))
        or target.endswith("/")
    )


def normalize_target(target: str) -> str:
    """Strip a leading ./ and collapse repeated slashes to match scanned paths.

    Public because both the jsmastery adapter and the application validation
    path need one shared normalization (spec 0003): the adapter builds
    evidence targets from code path tokens, and validation checks each cited
    target directly against that same normalized form.
    """
    stripped = target.strip()
    if stripped.startswith("./"):
        stripped = stripped[2:]
    parts = [part for part in stripped.split("/") if part != ""]
    return "/".join(parts)


def _under_specs_dir(normalized: str) -> bool:
    return normalized.startswith(_SPECS_DIR_PREFIX)


def _check_evidence(
    record: CanonicalDecisionRecord,
    context: ValidationContext,
    violations: list[Violation],
) -> None:
    if not record.evidence:
        return
    for index, evidence in enumerate(record.evidence):
        field = f"evidence[{index}].target"
        if evidence.target is None or evidence.target.strip() == "":
            violations.append(
                _violation(
                    field,
                    Severity.ERROR,
                    "evidence.empty_target",
                    "evidence target is empty",
                )
            )
            continue
        if evidence.kind is None:
            # already reported as required.missing; nothing kind specific to check
            continue
        target = evidence.target.strip()
        if evidence.kind == EvidenceKind.COMMIT:
            if not context.git_available:
                # resolution is skipped entirely; git_unavailable warns instead
                continue
            matches = [
                commit for commit in context.known_commits if commit.startswith(target)
            ]
            if not matches:
                violations.append(
                    _violation(
                        field,
                        Severity.ERROR,
                        "evidence.commit_unresolved",
                        f"commit prefix {target!r} matches no known commit",
                    )
                )
            elif len(matches) > 1:
                violations.append(
                    _violation(
                        field,
                        Severity.ERROR,
                        "evidence.commit_ambiguous",
                        f"commit prefix {target!r} matches more than one known commit",
                    )
                )
            continue
        if _target_is_not_normalized(target):
            violations.append(
                _violation(
                    field,
                    Severity.ERROR,
                    "evidence.target_not_normalized",
                    "evidence target must be a relative normalized path",
                )
            )
            continue
        normalized = normalize_target(target)
        if evidence.kind == EvidenceKind.SPEC and not _under_specs_dir(normalized):
            violations.append(
                _violation(
                    field,
                    Severity.ERROR,
                    "evidence.spec_outside_specs_dir",
                    "spec evidence must resolve under docs/specs/",
                )
            )
            continue
        if normalized not in context.existing_paths:
            violations.append(
                _violation(
                    field,
                    Severity.ERROR,
                    "evidence.path_unresolved",
                    f"evidence target {normalized!r} is not an existing path",
                )
            )


def _check_attempted_fields(
    context: ValidationContext, violations: list[Violation]
) -> None:
    for field in sorted(context.attempted_fields):
        violations.append(
            _violation(
                field,
                Severity.WARNING,
                "field.attempted_unfilled",
                f"field {field} was attempted but not populated",
            )
        )


def _check_unknown_fields(
    context: ValidationContext, violations: list[Violation]
) -> None:
    for field in sorted(context.unknown_fields):
        violations.append(
            _violation(
                field,
                Severity.WARNING,
                "field.unknown",
                f"unknown field {field}",
            )
        )


def _check_mentions_unresolved(
    context: ValidationContext, violations: list[Violation]
) -> None:
    """Warn when the adapter dropped code path mentions that did not resolve."""
    if context.unresolved_mention_count > 0:
        violations.append(
            _violation(
                "evidence",
                Severity.WARNING,
                "evidence.mentions_unresolved",
                f"{context.unresolved_mention_count} code path mentions "
                "did not resolve",
            )
        )


def _check_git_unavailable(
    record: CanonicalDecisionRecord,
    context: ValidationContext,
    violations: list[Violation],
) -> None:
    if context.git_available:
        return
    has_commit = record.evidence is not None and any(
        evidence.kind == EvidenceKind.COMMIT for evidence in record.evidence
    )
    if has_commit:
        violations.append(
            _violation(
                "",
                Severity.WARNING,
                "context.git_unavailable",
                "git history is unavailable, commit evidence resolution was skipped",
            )
        )
