"""Domain rule tests for the doctor diagnostic (spec 0004).

Covers heading frequency counts and rounding, exact heading set grouping, and
skip summaries, the pure rules that live in the domain layer.
"""

from __future__ import annotations

from decimal import Decimal

from decision_memory.domain.doctor import (
    SkippedPath,
    SkipReason,
    SurveyedDocument,
    heading_frequencies,
    heading_set_groups,
    skip_summaries,
)


def _doc(path: str, headings: list[str]) -> SurveyedDocument:
    return SurveyedDocument(relative_path=path, h2_headings=frozenset(headings))


def test_heading_frequencies_count_distinct_headings_per_file() -> None:
    # a duplicated heading inside one file counts once (AC-5).
    docs = [
        _doc("a.md", ["Context", "Decision", "Context"]),
        _doc("b.md", ["Context"]),
        _doc("c.md", []),
    ]
    frequencies = heading_frequencies(docs)
    assert [(item.heading, item.file_count) for item in frequencies] == [
        ("Context", 2),
        ("Decision", 1),
    ]
    by_heading = {item.heading: item for item in frequencies}
    assert by_heading["Context"].percentage == Decimal("66.7")
    assert by_heading["Decision"].percentage == Decimal("33.3")


def test_heading_frequencies_sort_by_count_then_exact_text() -> None:
    docs = [
        _doc("a.md", ["Zebra"]),
        _doc("b.md", ["Alpha", "Beta"]),
        _doc("c.md", ["Alpha"]),
    ]
    frequencies = heading_frequencies(docs)
    assert [(item.heading, item.file_count) for item in frequencies] == [
        ("Alpha", 2),
        ("Beta", 1),
        ("Zebra", 1),
    ]


def test_heading_frequency_rounds_half_up() -> None:
    # 1 of 16 is 6.25 percent; decimal round half up lands on 6.3, where
    # round half even would land on 6.2.
    docs = [_doc("a.md", ["X"])] + [_doc(f"{index}.md", []) for index in range(1, 16)]
    frequencies = heading_frequencies(docs)
    assert frequencies[0].percentage == Decimal("6.3")


def test_heading_frequency_zero_denominator_is_never_a_row() -> None:
    assert heading_frequencies([]) == []


def test_heading_set_groups_group_by_exact_set() -> None:
    docs = [
        _doc("a.md", ["Context", "Decision"]),
        _doc("b.md", ["Decision", "Context"]),
        _doc("c.md", ["Context"]),
        _doc("d.md", []),
        _doc("e.md", []),
    ]
    groups = heading_set_groups(docs, samples=5)
    # two count 2 groups sort by heading tuple, empty tuple first (AC-3).
    assert [(group.headings, group.file_count) for group in groups] == [
        ((), 2),
        (("Context", "Decision"), 2),
        (("Context",), 1),
    ]


def test_heading_set_groups_limit_samples_only() -> None:
    docs = [_doc(f"{index}.md", ["X"]) for index in range(5)]
    groups = heading_set_groups(docs, samples=2)
    assert groups[0].file_count == 5
    assert groups[0].sample_paths == ("0.md", "1.md")


def test_skip_summaries_fixed_order_and_unseen_counts() -> None:
    skipped = [
        SkippedPath("a", SkipReason.HIDDEN_DIRECTORY, unseen_contents=True),
        SkippedPath("b", SkipReason.HIDDEN_DIRECTORY, unseen_contents=True),
        SkippedPath("c", SkipReason.UNREADABLE_MARKDOWN),
        SkippedPath("d", SkipReason.DESCENDANT_SYMBOLIC_LINK, unseen_contents=True),
    ]
    summaries = skip_summaries(skipped, samples=5)
    assert [
        (summary.reason, summary.count, summary.unseen_subtrees)
        for summary in summaries
    ] == [
        (SkipReason.DESCENDANT_SYMBOLIC_LINK, 1, 1),
        (SkipReason.HIDDEN_DIRECTORY, 2, 2),
        (SkipReason.UNREADABLE_MARKDOWN, 1, 0),
    ]


def test_skip_summaries_limit_samples() -> None:
    skipped = [
        SkippedPath(f"p{index}.md", SkipReason.UNREADABLE_MARKDOWN)
        for index in range(5)
    ]
    summaries = skip_summaries(skipped, samples=2)
    assert summaries[0].count == 5
    assert summaries[0].sample_paths == ("p0.md", "p1.md")


def test_skip_summaries_with_no_skips_is_empty() -> None:
    assert skip_summaries([], samples=3) == []
