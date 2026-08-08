"""Discovery tests for the jsmastery adapter (spec 0003).

Covers AC-1, AC-2, AC-7 (unmapped status skip), AC-19, and AC-20.
"""

from __future__ import annotations

from spec_factory import INDEX, make_corpus, write_spec

from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter


def _adapter() -> JsmasteryAdapter:
    return JsmasteryAdapter()


def test_discovers_immediate_child_directories_with_index_md(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    write_spec(corpus, "0002-second")
    result = _adapter().discover(corpus)
    assert [spec.id for spec in result.specs] == ["DM-0001", "DM-0002"]
    assert result.skipped == []
    assert result.collisions == []


def test_directory_without_index_md_is_reported_as_not_a_spec(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    (corpus / "docs" / "specs" / "0002-assets").mkdir()
    result = _adapter().discover(corpus)
    assert [spec.id for spec in result.specs] == ["DM-0001"]
    assert [skip.path.name for skip in result.skipped] == ["0002-assets"]
    assert result.skipped[0].reason == "no index.md"


def test_directory_without_leading_digits_is_skipped(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "no-leading-digits")
    result = _adapter().discover(corpus)
    assert result.specs == []
    assert result.skipped[0].reason == "no leading digits in directory name"


def test_id_derives_from_leading_digits(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0012-portfolio-private-access-gate")
    result = _adapter().discover(corpus)
    assert result.specs[0].id == "DM-0012"


def test_directory_without_decision_section_is_skipped(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    index = (
        "# 0001. No decision\n\n"
        "**Date**: 2026-08-07\n"
        "**Status**: Accepted\n\n"
        "## Context\n\nNo decision section here.\n"
    )
    write_spec(corpus, "0001-no-decision", index=index, rationale=None)
    result = _adapter().discover(corpus)
    assert result.specs == []
    assert result.skipped[0].reason == "no ## Decision section"


def test_unmapped_status_is_skipped(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    index = INDEX.replace("**Status**: Accepted", "**Status**: Draft")
    write_spec(corpus, "0001-draft", index=index)
    result = _adapter().discover(corpus)
    assert result.specs == []
    assert "not a known status" in result.skipped[0].reason


def test_contributing_files_are_index_then_rationale(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    spec_dir = write_spec(corpus, "0001-first")
    result = _adapter().discover(corpus)
    spec = result.specs[0]
    assert spec.root == spec_dir
    assert spec.corpus_root == corpus
    assert spec.contributing_files == [
        spec_dir / "index.md",
        spec_dir / "rationale.md",
    ]


def test_contributing_files_without_rationale_is_index_only(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    spec_dir = write_spec(corpus, "0001-first", rationale=None)
    result = _adapter().discover(corpus)
    assert result.specs[0].contributing_files == [spec_dir / "index.md"]


def test_collision_reports_every_path_and_uses_first(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-alpha")
    write_spec(corpus, "0001-beta")
    result = _adapter().discover(corpus)
    assert [spec.id for spec in result.specs] == ["DM-0001"]
    assert result.specs[0].root.name == "0001-alpha"
    assert len(result.collisions) == 1
    collision = result.collisions[0]
    assert collision.id == "DM-0001"
    assert [path.name for path in collision.paths] == ["0001-alpha", "0001-beta"]
    assert collision.used.name == "0001-alpha"
