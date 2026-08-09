"""Scanner tests for the doctor diagnostic (spec 0004).

Covers the narrow H2 and fence grammar, decoding, and the deterministic path
classification: hidden paths, suffix casing, symbolic links, unreadable and
unsupported entries, and transient disappearance. Includes the shared
unmatched fence fixture asserted through both the doctor scanner and the
shipped adapter scanner so their agreed behavior cannot drift (AC-4).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from decision_memory.domain.doctor import SkipReason
from decision_memory.infrastructure.doctor_scanner import (
    _Accumulator,
    _classify_entry,
    h2_headings,
    scan_corpus,
)
from decision_memory.infrastructure.jsmastery_adapter import _h2_sections

# The shared unmatched fence fixture: an opener that never closes, followed by
# an H2 that must still count through both scanners.
UNMATCHED_FENCE_TEXT = (
    "## Notes\n\n"
    "```bash\n"
    'echo "this fence is never closed"\n\n'
    "## Consequences\n\n"
    "**Positive**:\n"
    "- Still found.\n"
)


class _DisappearingEntry:
    """A fake directory entry whose stat says it no longer exists."""

    def __init__(self, path: str) -> None:
        self.name = Path(path).name
        self.path = path

    def stat(self, follow_symlinks: bool = True) -> object:
        raise FileNotFoundError(2, "No such file or directory")


def test_unmatched_fence_agrees_with_the_adapter() -> None:
    # both scanners recognize the H2 after the unmatched fence opener, so the
    # shared fixture cannot drift (AC-4).
    assert "Consequences" in h2_headings(UNMATCHED_FENCE_TEXT)
    assert "Consequences" in _h2_sections(UNMATCHED_FENCE_TEXT)


def test_bom_and_line_endings_are_normalized(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.md").write_bytes(b"\xef\xbb\xbf## Context\r\n\r\n## Decision\r")
    result = scan_corpus(root)
    assert len(result.documents) == 1
    assert result.documents[0].h2_headings == frozenset({"Context", "Decision"})


def test_h2_opener_requires_two_hashes_then_whitespace() -> None:
    assert h2_headings("## Context") == frozenset({"Context"})
    assert h2_headings("##\tContext") == frozenset({"Context"})
    assert h2_headings("   ## Context") == frozenset({"Context"})
    assert h2_headings("##") == frozenset()  # a bare ## is not a heading
    assert h2_headings("### Context") == frozenset()  # H3 is not H2
    assert h2_headings("# Context") == frozenset()  # H1 is not H2
    assert h2_headings("    ## Context") == frozenset()  # four spaces is not H2


def test_h2_text_stripping_and_empty_heading() -> None:
    assert h2_headings("##   Context  ") == frozenset({"Context"})
    assert h2_headings("## ") == frozenset({""})  # an empty heading


def test_closing_hash_run_is_stripped() -> None:
    assert h2_headings("## Context ###") == frozenset({"Context"})
    assert h2_headings("## Context#") == frozenset({"Context#"})
    assert h2_headings("## ###") == frozenset({""})
    assert h2_headings("## Context \\#") == frozenset({"Context \\#"})


def test_closed_backtick_fence_excludes_headings() -> None:
    text = "## Real\n\n```\n## Fake\n```\n\n## After\n"
    assert h2_headings(text) == frozenset({"Real", "After"})


def test_closed_tilde_fence_excludes_headings() -> None:
    text = "## Real\n\n~~~\n## Fake\n~~~\n\n## After\n"
    assert h2_headings(text) == frozenset({"Real", "After"})


def test_tilde_does_not_close_a_backtick_fence() -> None:
    text = "## Real\n\n```\n~~~\n## Fake\n```\n## After\n"
    assert h2_headings(text) == frozenset({"Real", "After"})


def test_short_closer_leaves_the_fence_unclosed() -> None:
    # a three backtick closer cannot close a four backtick opener, and an
    # opener that never closes excludes nothing (AC-4).
    text = "## Real\n\n````\n## Fake\n```\n## After\n"
    assert h2_headings(text) == frozenset({"Real", "Fake", "After"})


def test_backtick_opener_with_backtick_in_info_is_not_a_fence() -> None:
    text = "## Real\n\n```foo`bar\n## Still\n"
    assert h2_headings(text) == frozenset({"Real", "Still"})


def test_mixed_nested_corpus_classifies_every_path_once(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    (root / "adr").mkdir(parents=True)
    (root / "adr" / "0001.md").write_text("## Context\n## Decision\n", encoding="utf-8")
    (root / "adr" / "0002.md").write_text("## Context\n## Decision\n", encoding="utf-8")
    (root / "notes.md").write_text("no headings\n", encoding="utf-8")
    (root / "readme.txt").write_text("x\n", encoding="utf-8")
    (root / "data.json").write_text("{}\n", encoding="utf-8")
    (root / "linked.md").symlink_to(root / "adr", target_is_directory=True)

    result = scan_corpus(root)
    assert len(result.documents) == 3
    assert result.ignored_non_markdown == 2
    assert len(result.skipped) == 1
    assert result.skipped[0].reason == SkipReason.DESCENDANT_SYMBOLIC_LINK
    assert result.skipped[0].relative_path == "linked.md"
    assert result.skipped[0].unseen_contents is True


def test_hidden_directory_is_excluded_with_unseen_subtree(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    (root / ".git").mkdir(parents=True)
    (root / ".git" / "a.md").write_text("## X\n", encoding="utf-8")
    (root / "ok.md").write_text("## Y\n", encoding="utf-8")
    result = scan_corpus(root)
    assert [document.relative_path for document in result.documents] == ["ok.md"]
    hidden = [
        item for item in result.skipped if item.reason == SkipReason.HIDDEN_DIRECTORY
    ]
    assert len(hidden) == 1
    assert hidden[0].relative_path == ".git"
    assert hidden[0].unseen_contents is True


def test_hidden_markdown_file_is_analyzed(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / ".hidden.md").write_text("## X\n", encoding="utf-8")
    result = scan_corpus(root)
    assert [document.relative_path for document in result.documents] == [".hidden.md"]


def test_markdown_suffixes_match_without_regard_to_case(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.MD").write_text("## X\n", encoding="utf-8")
    (root / "b.Markdown").write_text("## Y\n", encoding="utf-8")
    (root / "c.mdown").write_text("## Z\n", encoding="utf-8")
    (root / "d.txt").write_text("x\n", encoding="utf-8")
    result = scan_corpus(root)
    assert len(result.documents) == 3
    assert result.ignored_non_markdown == 1


def test_descendant_symlink_to_file_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "target.md").write_text("## X\n", encoding="utf-8")
    (root / "link.md").symlink_to(root / "target.md")
    result = scan_corpus(root)
    assert len(result.documents) == 1  # only the real file
    assert result.skipped[0].reason == SkipReason.DESCENDANT_SYMBOLIC_LINK
    assert result.skipped[0].unseen_contents is False


def test_broken_symlink_is_skipped_without_unseen_subtree(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "broken.md").symlink_to(root / "missing.md")
    result = scan_corpus(root)
    assert len(result.documents) == 0
    assert result.skipped[0].reason == SkipReason.DESCENDANT_SYMBOLIC_LINK
    assert result.skipped[0].unseen_contents is False


def test_cyclic_symlinks_are_skipped_without_unseen_subtree(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a").symlink_to(root / "b")
    (root / "b").symlink_to(root / "a")
    result = scan_corpus(root)
    assert [item.reason for item in result.skipped] == [
        SkipReason.DESCENDANT_SYMBOLIC_LINK,
        SkipReason.DESCENDANT_SYMBOLIC_LINK,
    ]
    assert all(not item.unseen_contents for item in result.skipped)


def test_strict_utf8_failure_reports_unreadable_markdown(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "bad.md").write_bytes(b"\xff\xfe\x00bad")
    result = scan_corpus(root)
    assert len(result.documents) == 0
    assert result.skipped[0].reason == SkipReason.UNREADABLE_MARKDOWN


def test_unreadable_directory_reports_one_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import decision_memory.infrastructure.doctor_scanner as scanner_module

    root = tmp_path / "corpus"
    root.mkdir()
    (root / "ok.md").write_text("## X\n", encoding="utf-8")
    (root / "locked").mkdir()
    real_scandir = scanner_module.os.scandir

    def fake_scandir(path: str) -> object:
        if os.path.basename(str(path)) == "locked":
            raise PermissionError(13, "Permission denied")
        return real_scandir(path)

    monkeypatch.setattr(scanner_module.os, "scandir", fake_scandir)
    result = scan_corpus(root)
    locked = [
        item
        for item in result.skipped
        if item.reason == SkipReason.UNREADABLE_DIRECTORY
    ]
    assert len(locked) == 1
    assert locked[0].relative_path == "locked"
    assert locked[0].unseen_contents is True
    assert len(result.documents) == 1


def test_unreadable_root_reports_dot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import decision_memory.infrastructure.doctor_scanner as scanner_module

    root = tmp_path / "corpus"
    root.mkdir()

    def fake_scandir(path: str) -> object:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(scanner_module.os, "scandir", fake_scandir)
    result = scan_corpus(root)
    assert len(result.documents) == 0
    assert len(result.skipped) == 1
    assert result.skipped[0].relative_path == "."
    assert result.skipped[0].reason == SkipReason.UNREADABLE_DIRECTORY
    assert result.skipped[0].unseen_contents is True


def test_disappeared_entry_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    accumulator = _Accumulator()
    entry = _DisappearingEntry(str(root / "ghost.md"))
    _classify_entry(root, entry, accumulator)
    assert len(accumulator.skipped) == 1
    assert accumulator.skipped[0].reason == SkipReason.DISAPPEARED
    assert accumulator.skipped[0].relative_path == "ghost.md"


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="POSIX named pipes only")
def test_unsupported_entry_is_reported(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    os.mkfifo(root / "pipe")
    result = scan_corpus(root)
    assert [item.reason for item in result.skipped] == [SkipReason.UNSUPPORTED_ENTRY]
    assert result.skipped[0].relative_path == "pipe"


def test_directory_entries_are_sorted_deterministically(tmp_path: Path) -> None:
    # the same corpus in different creation orders yields the same report,
    # because entries are sorted by name (AC-3).
    names = ["b.md", "a.md", "c.md"]
    results: list[tuple[str, ...]] = []
    for order in ((0, 1, 2), (2, 0, 1)):
        root = tmp_path / f"corpus{order[0]}"
        root.mkdir()
        for index in order:
            (root / names[index]).write_text("## X\n", encoding="utf-8")
        result = scan_corpus(root)
        results.append(tuple(doc.relative_path for doc in result.documents))
    assert results[0] == results[1] == ("a.md", "b.md", "c.md")
