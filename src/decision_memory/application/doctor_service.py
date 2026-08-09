"""Application: the doctor survey use case.

Resolves the corpus root, delegates the read only scan to an injected scanner
port, applies the domain grouping rules, and returns the fixed exit code.
Only standard library imports; framework code stays in infrastructure and the
CLI, and the concrete scanner is injected from the composition root so this
module never imports infrastructure (AGENTS.md: outer layers depend inward).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from decision_memory.domain.doctor import (
    HeadingFrequency,
    HeadingSetGroup,
    SkippedPath,
    SkipSummary,
    SurveyedDocument,
    heading_frequencies,
    heading_set_groups,
    skip_summaries,
)

# Exit codes fixed by spec 0004, matching the vocabulary of specs 0002 and
# 0003. Code 2 is reserved by Click for command syntax errors.
EXIT_OK = 0
EXIT_ERROR = 1
EXIT_CORPUS_INVALID = 3


@dataclass(frozen=True)
class DoctorRequest:
    """One doctor run's inputs."""

    root: Path
    samples: int


@dataclass(frozen=True)
class ScanResult:
    """The scanner's raw output at the application boundary."""

    documents: list[SurveyedDocument] = field(default_factory=list)
    ignored_non_markdown: int = 0
    skipped: list[SkippedPath] = field(default_factory=list)


# The narrow scanner port: a callable that surveys a resolved corpus root.
# Infrastructure implements it; the use case takes it as a parameter so it
# never touches the filesystem itself. cli.py, the composition root, wires
# the concrete scanner.
DoctorScanner = Callable[[Path], ScanResult]


@dataclass(frozen=True)
class DoctorOutcome:
    """Everything the report needs, plus the exit code."""

    exit_code: int
    markdown_analyzed: int
    non_markdown_ignored: int
    headings: list[HeadingFrequency]
    heading_groups: list[HeadingSetGroup]
    skips: list[SkipSummary]


def run_doctor(request: DoctorRequest, scanner: DoctorScanner) -> DoctorOutcome:
    """Survey a corpus and return the fixed outcome.

    A missing root, a broken or cyclic root symbolic link chain, or a resolved
    root that is not a directory returns exit code 3 (AC-10). Otherwise the
    scan runs, the domain rules aggregate, and a completed survey always
    returns exit code 0, even when it reports skips (AC-9).
    """
    resolved = _resolve_root(request.root)
    if resolved is None:
        return DoctorOutcome(
            exit_code=EXIT_CORPUS_INVALID,
            markdown_analyzed=0,
            non_markdown_ignored=0,
            headings=[],
            heading_groups=[],
            skips=[],
        )
    scan = scanner(resolved)
    documents = scan.documents
    return DoctorOutcome(
        exit_code=EXIT_OK,
        markdown_analyzed=len(documents),
        non_markdown_ignored=scan.ignored_non_markdown,
        headings=heading_frequencies(documents),
        heading_groups=heading_set_groups(documents, request.samples),
        skips=skip_summaries(scan.skipped, request.samples),
    )


def _resolve_root(root: Path) -> Path | None:
    """The fully resolved corpus root, or None when the corpus is unusable.

    A symbolic link chain is followed only because this is the root path
    explicitly supplied by the user (AC-2). A broken or cyclic chain resolves
    to a path that is not a directory, which lands here as unusable, and an
    unreadable-but-real directory is not: the scanner reports it as a single
    ``unreadable directory`` skip for ``.`` (AC-9).
    """
    try:
        resolved = root.resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    if not resolved.is_dir():
        return None
    return resolved
