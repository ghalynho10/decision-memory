"""Infrastructure: the read only doctor scanner.

Walks a resolved corpus root, classifies every observed path exactly once,
reads eligible Markdown files as strict UTF 8, and extracts their exact H2
heading sets with the narrow grammar fixed by spec 0004. Filesystem access,
text decoding, and the heading and fence grammar belong here; grouping rules
live in the domain. The scanner never opens or descends through a descendant
symbolic link, and it performs no writes (AC-11).
"""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path

from decision_memory.application.doctor_service import ScanResult
from decision_memory.domain.doctor import SkippedPath, SkipReason, SurveyedDocument

_MARKDOWN_SUFFIXES = (".md", ".markdown", ".mdown")

# H2 opener: zero through three ASCII spaces, exactly two hashes, then at
# least one ASCII space or tab and the heading text. A bare ``##`` at end of
# line never matches because the whitespace is required (AC-4).
_H2_RE = re.compile(r"^ {0,3}##[ \t]+(.*)$")

# Fence opener: zero through three ASCII spaces, then at least three
# backticks or at least three tildes. A backtick opener's remaining text
# cannot contain a backtick, checked separately (AC-4).
_FENCE_OPEN_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")

# Fence closer: zero through three ASCII spaces, the same marker character
# repeated at least as many times as the opener, then only ASCII spaces or
# tabs. One regex per marker character.
_BACKTICK_CLOSE_RE = re.compile(r"^ {0,3}(`+)[ \t]*$")
_TILDE_CLOSE_RE = re.compile(r"^ {0,3}(~+)[ \t]*$")


@dataclass
class _Accumulator:
    """Mutable scan state threaded through the recursive walk."""

    documents: list[SurveyedDocument] = field(default_factory=list)
    skipped: list[SkippedPath] = field(default_factory=list)
    ignored_non_markdown: int = 0


def scan_corpus(root: Path) -> ScanResult:
    """Survey a resolved corpus root and classify every observed path."""
    accumulator = _Accumulator()
    _inspect_directory(root, root, accumulator)
    return ScanResult(
        documents=accumulator.documents,
        ignored_non_markdown=accumulator.ignored_non_markdown,
        skipped=accumulator.skipped,
    )


def h2_headings(text: str) -> frozenset[str]:
    """The exact set of distinct H2 heading texts in decoded text (AC-5).

    Closed fence intervals are established before headings are classified, so
    an unmatched fence opener creates no excluded interval and later H2 lines
    stay eligible (AC-4).
    """
    lines = text.split("\n")
    fenced = _closed_fence_lines(lines)
    headings: set[str] = set()
    for index, line in enumerate(lines):
        if index in fenced:
            continue
        heading = _h2_text(line)
        if heading is not None:
            headings.add(heading)
    return frozenset(headings)


def _inspect_directory(root: Path, directory: Path, accumulator: _Accumulator) -> None:
    """Inspect a directory, classifying each entry in sorted name order."""
    try:
        iterator = os.scandir(directory)
    except FileNotFoundError:
        accumulator.skipped.append(
            SkippedPath(_relative(root, directory), SkipReason.DISAPPEARED)
        )
        return
    except OSError:
        # Access failure on the root is reported once as ``.`` with unknown
        # contents (AC-9); the survey never estimates what was below it.
        accumulator.skipped.append(
            SkippedPath(
                _relative(root, directory),
                SkipReason.UNREADABLE_DIRECTORY,
                unseen_contents=True,
            )
        )
        return
    with iterator:
        entries = sorted(iterator, key=lambda entry: entry.name)
    for entry in entries:
        _classify_entry(root, entry, accumulator)


def _classify_entry(
    root: Path, entry: os.DirEntry[str], accumulator: _Accumulator
) -> None:
    """Classify one entry by the fixed order in the spec's path table.

    The first applicable classification wins, and every observed path receives
    exactly one (AC-7). A metadata call that says the entry no longer exists
    is ``disappeared``; any other metadata failure is ``unsupported entry``.
    """
    try:
        metadata = entry.stat(follow_symlinks=False)
    except FileNotFoundError:
        accumulator.skipped.append(
            SkippedPath(_relative(root, Path(entry.path)), SkipReason.DISAPPEARED)
        )
        return
    except OSError:
        accumulator.skipped.append(
            SkippedPath(_relative(root, Path(entry.path)), SkipReason.UNSUPPORTED_ENTRY)
        )
        return

    mode = metadata.st_mode
    if stat.S_ISLNK(mode):
        accumulator.skipped.append(
            SkippedPath(
                _relative(root, Path(entry.path)),
                SkipReason.DESCENDANT_SYMBOLIC_LINK,
                unseen_contents=_link_target_is_directory(entry),
            )
        )
        return
    if stat.S_ISDIR(mode):
        if entry.name.startswith("."):
            accumulator.skipped.append(
                SkippedPath(
                    _relative(root, Path(entry.path)),
                    SkipReason.HIDDEN_DIRECTORY,
                    unseen_contents=True,
                )
            )
            return
        _inspect_directory(root, Path(entry.path), accumulator)
        return
    if stat.S_ISREG(mode):
        if _is_markdown(entry.name):
            _analyze_markdown(root, Path(entry.path), accumulator)
        else:
            accumulator.ignored_non_markdown += 1
        return
    accumulator.skipped.append(
        SkippedPath(_relative(root, Path(entry.path)), SkipReason.UNSUPPORTED_ENTRY)
    )


def _link_target_is_directory(entry: os.DirEntry[str]) -> bool:
    """Whether a descendant link's target is a directory, never opening it.

    Only the target type is queried; the target is never opened or descended
    through (AC-2, AC-11). A broken, cyclic, or unreadable target leaves the
    value false.
    """
    try:
        target = entry.stat(follow_symlinks=True)
    except OSError:
        return False
    return stat.S_ISDIR(target.st_mode)


def _analyze_markdown(root: Path, path: Path, accumulator: _Accumulator) -> None:
    """Read one Markdown file, or record it as unreadable (AC-9)."""
    text = _read_text(path)
    if text is None:
        accumulator.skipped.append(
            SkippedPath(_relative(root, path), SkipReason.UNREADABLE_MARKDOWN)
        )
        return
    accumulator.documents.append(
        SurveyedDocument(
            relative_path=_relative(root, path),
            h2_headings=h2_headings(text),
        )
    )


def _is_markdown(name: str) -> bool:
    """An eligible Markdown suffix, compared without regard to case (AC-2)."""
    lowered = name.lower()
    return lowered.endswith(_MARKDOWN_SUFFIXES)


def _relative(root: Path, path: Path) -> str:
    """A corpus relative POSIX path; ``.`` for the root itself (AC-2)."""
    return path.relative_to(root).as_posix()


def _read_text(path: Path) -> str | None:
    """Strict UTF 8 with one leading BOM removed, line endings normalized.

    The ``utf-8-sig`` codec decodes strict UTF 8 and strips one leading BOM;
    a decoding failure returns None so the caller can report an unreadable
    Markdown file without stopping the survey (AC-4, AC-9).
    """
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError):
        return None
    return raw.replace("\r\n", "\n").replace("\r", "\n")


def _h2_text(line: str) -> str | None:
    """The cleaned H2 heading text for a line, or None when it is not an H2.

    The text strips leading and trailing ASCII spaces and tabs, then removes
    an unescaped closing hash run when whitespace precedes it, then strips
    again (AC-4). ``## `` is an empty heading; a bare ``##`` is not a heading.
    """
    match = _H2_RE.match(line)
    if match is None:
        return None
    raw = match.group(1)
    end = len(raw)
    while end > 0 and raw[end - 1] == "#":
        end -= 1
    if end == len(raw):
        return raw.strip(" \t")
    before = raw[:end]
    preceded_by_space = before == "" or before[-1] in " \t"
    unescaped = not before.endswith("\\")
    if preceded_by_space and unescaped:
        return before.rstrip(" \t").strip(" \t")
    return raw.strip(" \t")


def _closed_fence_lines(lines: list[str]) -> frozenset[int]:
    """Line indices covered by a fence that actually closes (AC-4).

    A fence closes only on the same marker character repeated at least as many
    times as the opener, followed by only ASCII spaces or tabs. An opener with
    no valid closer creates no excluded interval, so a later H2 line remains
    eligible rather than being swallowed to end of file.
    """
    fenced: set[int] = set()
    opener_index: int | None = None
    marker_char = ""
    marker_len = 0
    for index, line in enumerate(lines):
        if opener_index is None:
            match = _FENCE_OPEN_RE.match(line)
            if match is None:
                continue
            marker = match.group(1)
            info = match.group(2)
            if marker[0] == "`" and "`" in info:
                continue
            opener_index = index
            marker_char = marker[0]
            marker_len = len(marker)
        else:
            closer = (
                _BACKTICK_CLOSE_RE.match(line)
                if marker_char == "`"
                else _TILDE_CLOSE_RE.match(line)
            )
            if closer is not None and len(closer.group(1)) >= marker_len:
                fenced.update(range(opener_index, index + 1))
                opener_index = None
    return frozenset(fenced)
