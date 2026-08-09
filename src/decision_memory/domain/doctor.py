"""Domain: the doctor diagnostic's pure survey rules.

Holds the closed skip reason set, the surveyed document and skipped path
shapes, and the exact grouping, frequency, and percentage rules fixed by
spec 0004. Standard library only, no framework imports, by project rule.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum


class SkipReason(StrEnum):
    """Every reason a path can be excluded, in the fixed display order.

    The order here is the order skip rows render in (AC-3), so it is part of
    the report contract and must not be rearranged casually.
    """

    DISAPPEARED = "disappeared"
    DESCENDANT_SYMBOLIC_LINK = "descendant symbolic link"
    HIDDEN_DIRECTORY = "hidden directory"
    UNREADABLE_DIRECTORY = "unreadable directory"
    UNREADABLE_MARKDOWN = "unreadable Markdown file"
    UNSUPPORTED_ENTRY = "unsupported entry"


@dataclass(frozen=True)
class SurveyedDocument:
    """One analyzed Markdown file and its exact set of H2 heading texts.

    ``h2_headings`` is a set because each distinct H2 counts at most once per
    file (AC-5), and it is the identity for heading set grouping (AC-6).
    """

    relative_path: str
    h2_headings: frozenset[str]


@dataclass(frozen=True)
class SkippedPath:
    """One path the survey did not analyze, with its reason."""

    relative_path: str
    reason: SkipReason
    unseen_contents: bool = False


@dataclass(frozen=True)
class HeadingFrequency:
    """How many analyzed files carry one exact heading, with its percentage."""

    heading: str
    file_count: int
    percentage: Decimal


@dataclass(frozen=True)
class HeadingSetGroup:
    """Files whose H2 sets are exactly equal, with limited sample paths."""

    headings: tuple[str, ...]
    file_count: int
    sample_paths: tuple[str, ...]


@dataclass(frozen=True)
class SkipSummary:
    """One skip reason's totals and limited sample paths."""

    reason: SkipReason
    count: int
    unseen_subtrees: int
    sample_paths: tuple[str, ...]


def heading_frequencies(
    documents: Sequence[SurveyedDocument],
) -> list[HeadingFrequency]:
    """Distinct headings with file counts and percentages, sorted.

    Rows sort by file count descending, then exact heading text (AC-5). The
    percentage is 100 times the file count divided by the analyzed Markdown
    count, rounded to one decimal place with decimal round half up (AC-5).
    """
    analyzed = len(documents)
    counts: dict[str, int] = {}
    for document in documents:
        for heading in document.h2_headings:
            counts[heading] = counts.get(heading, 0) + 1
    frequencies = [
        HeadingFrequency(
            heading=heading,
            file_count=count,
            percentage=_percentage(count, analyzed),
        )
        for heading, count in counts.items()
    ]
    frequencies.sort(key=lambda item: (-item.file_count, item.heading))
    return frequencies


def heading_set_groups(
    documents: Sequence[SurveyedDocument],
    samples: int,
) -> list[HeadingSetGroup]:
    """Documents grouped by their exact H2 set, including the empty set.

    Heading order and duplicates do not change group identity (AC-6). Groups
    sort by file count descending, then the sorted heading tuple (AC-3).
    Sample paths are sorted and limited to ``samples``; the limit changes
    examples only, never totals or grouping.
    """
    by_set: dict[frozenset[str], list[str]] = {}
    for document in documents:
        by_set.setdefault(document.h2_headings, []).append(document.relative_path)
    groups = [
        HeadingSetGroup(
            headings=tuple(sorted(headings)),
            file_count=len(paths),
            sample_paths=tuple(sorted(paths)[:samples]),
        )
        for headings, paths in by_set.items()
    ]
    groups.sort(key=lambda group: (-group.file_count, group.headings))
    return groups


def skip_summaries(
    skipped: Sequence[SkippedPath],
    samples: int,
) -> list[SkipSummary]:
    """Skipped paths grouped by reason, in the fixed reason order.

    Zero count reasons are omitted. Unseen subtree counts sum the true
    ``unseen_contents`` values, and sample paths are sorted and limited to
    ``samples``.
    """
    by_reason: dict[SkipReason, list[SkippedPath]] = {}
    for item in skipped:
        by_reason.setdefault(item.reason, []).append(item)
    summaries: list[SkipSummary] = []
    for reason in SkipReason:
        items = by_reason.get(reason, [])
        if not items:
            continue
        summaries.append(
            SkipSummary(
                reason=reason,
                count=len(items),
                unseen_subtrees=sum(1 for item in items if item.unseen_contents),
                sample_paths=tuple(
                    sorted(item.relative_path for item in items)[:samples]
                ),
            )
        )
    return summaries


def _percentage(file_count: int, analyzed: int) -> Decimal:
    """One decimal place with decimal round half up; zero when no files."""
    if analyzed == 0:
        return Decimal("0")
    value = Decimal(100) * Decimal(file_count) / Decimal(analyzed)
    return value.quantize(Decimal("0.0"), rounding=ROUND_HALF_UP)
