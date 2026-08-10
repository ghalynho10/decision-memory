"""Source resolution state tests (spec 0007 AC-19).

``resolve_source_path`` classifies a stored relative POSIX path against the
absolute ``source_root_hint``. Resolution is informative only and never
changes query state.
"""

from __future__ import annotations

from decision_memory.application.dto import ResolutionState
from decision_memory.infrastructure.source_resolver import resolve_source_path


def test_resolves_an_existing_file(tmp_path) -> None:
    target = tmp_path / "corpus" / "docs" / "specs" / "0012-portfolio" / "index.md"
    target.parent.mkdir(parents=True)
    target.write_text("# x", encoding="utf-8")
    result = resolve_source_path(
        "docs/specs/0012-portfolio/index.md", str(tmp_path / "corpus")
    )
    assert result == ResolutionState.RESOLVED


def test_absent_file_is_missing(tmp_path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    assert resolve_source_path("docs/nope.md", str(root)) == ResolutionState.MISSING


def test_directory_is_missing(tmp_path) -> None:
    (tmp_path / "docs").mkdir()
    assert resolve_source_path("docs", str(tmp_path)) == ResolutionState.MISSING


def test_wrong_case_is_missing(tmp_path) -> None:
    target = tmp_path / "index.md"
    target.write_text("# x", encoding="utf-8")
    assert resolve_source_path("Index.md", str(tmp_path)) == ResolutionState.MISSING


def test_symlink_escape_is_missing(tmp_path) -> None:
    outside = tmp_path / "outside.md"
    outside.write_text("# x", encoding="utf-8")
    root = tmp_path / "root"
    root.mkdir()
    (root / "link.md").symlink_to(outside)
    assert resolve_source_path("link.md", str(root)) == ResolutionState.MISSING


def test_invalid_relative_paths(tmp_path) -> None:
    for bad in ["/abs/path.md", "../escape.md", "a//b.md", "a/b/"]:
        assert (
            resolve_source_path(bad, str(tmp_path))
            == ResolutionState.INVALID_RELATIVE_PATH
        ), bad


def test_missing_hint_is_hint_unavailable(tmp_path) -> None:
    assert resolve_source_path("a/b.md", None) == ResolutionState.HINT_UNAVAILABLE
