"""Application: turn a record file path into a validation outcome.

This is the glue that makes the CLI work end to end. It resolves the project
root, scans existing paths, queries git history, builds the validation context,
and maps the result to the fixed exit codes. It uses only the standard library;
framework code stays in infrastructure.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

from decision_memory.domain.records import Severity, ValidationContext, Violation
from decision_memory.domain.validation import validate
from decision_memory.infrastructure.file_reader import parse_record_file
from decision_memory.infrastructure.path_resolution import resolve_cited_paths

# Exit codes fixed by spec 0002.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_UNPARSEABLE = 3


@dataclass(frozen=True)
class ValidationOutcome:
    """Violations plus the exit code the CLI should return."""

    violations: list[Violation]
    exit_code: int


def validate_file(
    file_path: Path, project_root: Path | None = None
) -> ValidationOutcome:
    """Parse and validate a record file, gathering context from the project root."""
    parse_result = parse_record_file(file_path)
    if parse_result.record is None:
        return ValidationOutcome(
            violations=parse_result.violations, exit_code=EXIT_UNPARSEABLE
        )
    root = _resolve_project_root(file_path, project_root)
    known_commits, git_available = _query_known_commits(root)
    context = ValidationContext(
        attempted_fields=frozenset(),
        unknown_fields=parse_result.unknown_fields,
        existing_paths=resolve_cited_paths(parse_result.record, root),
        known_commits=known_commits,
        git_available=git_available,
    )
    violations = [*parse_result.violations, *validate(parse_result.record, context)]
    exit_code = (
        EXIT_ERROR if any(v.severity == Severity.ERROR for v in violations) else EXIT_OK
    )
    return ValidationOutcome(violations=violations, exit_code=exit_code)


def _resolve_project_root(file_path: Path, override: Path | None) -> Path:
    """The root that anchors path and git checks.

    `--project-root` when given, else the nearest ancestor of the record file
    that contains a `.git` directory, else the record file's parent. Resolving
    from the record file rather than the working directory keeps the result the
    same wherever the command is run from.
    """
    if override is not None:
        return override.resolve()
    candidate = file_path
    for parent in (file_path, *file_path.parents):
        if (parent / ".git").exists():
            return parent
    return candidate.parent


def _query_known_commits(root: Path) -> tuple[frozenset[str], bool]:
    """Full commit hashes in git history, plus whether git is available.

    A root with no `.git` directory, or a git invocation that fails, yields an
    empty set and git_available False, which the validator reports as a single
    `context.git_unavailable` warning.
    """
    if not (root / ".git").exists():
        return frozenset(), False
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-list", "--all"],
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset(), False
    if result.returncode != 0:
        return frozenset(), False
    commits = {line.strip() for line in result.stdout.splitlines() if line.strip()}
    return frozenset(commits), True
