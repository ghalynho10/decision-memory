"""End to end tests for the CLI doctor command (spec 0004).

Covers the normative report contract, sample suppression, and the fixed exit
codes: 0 for a completed survey, 2 for a negative samples value, and 3 for an
unusable corpus root.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from decision_memory.cli import app

runner = CliRunner()


def _build_fixture_corpus(root: Path) -> None:
    """The corpus behind the spec's first normative report fixture."""
    (root / "adr").mkdir(parents=True)
    (root / "adr" / "0001.md").write_text(
        "## Context\n\n## Decision\n", encoding="utf-8"
    )
    (root / "adr" / "0002.md").write_text(
        "## Context\n\n## Decision\n", encoding="utf-8"
    )
    (root / "notes.md").write_text("plain notes without headings\n", encoding="utf-8")
    (root / "readme.txt").write_text("hi\n", encoding="utf-8")
    (root / "data.json").write_text("{}\n", encoding="utf-8")
    (root / "linked.md").symlink_to(root / "adr", target_is_directory=True)


def test_doctor_report_matches_the_normative_fixture(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    _build_fixture_corpus(root)
    result = runner.invoke(app, ["doctor", str(root)])
    expected = (
        "coverage\n"
        "  markdown analyzed: 3\n"
        "  non markdown ignored: 2\n"
        "  skipped: 1\n"
        "common H2 headings\n"
        '  "Context" | files: 2 | percent: 66.7%\n'
        '  "Decision" | files: 2 | percent: 66.7%\n'
        "exact H2 heading sets\n"
        '  ["Context", "Decision"] | files: 2\n'
        '    samples: ["adr/0001.md", "adr/0002.md"]\n'
        "  [] | files: 1\n"
        '    samples: ["notes.md"]\n'
        "skipped\n"
        "  descendant symbolic link | count: 1 | unseen subtrees: 1\n"
        '    samples: ["linked.md"]\n'
    )
    assert result.exit_code == 0
    assert result.stdout == expected


def test_empty_corpus_matches_the_zero_fixture(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    result = runner.invoke(app, ["doctor", str(root)])
    expected = (
        "coverage\n"
        "  markdown analyzed: 0\n"
        "  non markdown ignored: 0\n"
        "  skipped: 0\n"
        "common H2 headings\n"
        "  no heading evidence found\n"
        "exact H2 heading sets\n"
        "  no heading sets found\n"
        "skipped\n"
        "  none\n"
    )
    assert result.exit_code == 0
    assert result.stdout == expected


def test_zero_samples_suppresses_sample_lines(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "a.md").write_text("## Context\n## Decision\n", encoding="utf-8")
    result = runner.invoke(app, ["doctor", str(root), "--samples", "0"])
    assert result.exit_code == 0
    assert "samples:" not in result.stdout
    assert '["Context", "Decision"] | files: 1' in result.stdout


def test_samples_limits_sample_lines(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    for index in range(4):
        (root / f"{index}.md").write_text("## Context\n", encoding="utf-8")
    result = runner.invoke(app, ["doctor", str(root), "--samples", "2"])
    assert result.exit_code == 0
    assert '    samples: ["0.md", "1.md"]' in result.stdout
    assert '"2.md"' not in result.stdout


def test_negative_samples_is_a_usage_error(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    result = runner.invoke(app, ["doctor", str(root), "--samples", "-1"])
    assert result.exit_code == 2
    assert "coverage" not in result.stdout


def test_missing_root_exits_three(tmp_path: Path) -> None:
    result = runner.invoke(app, ["doctor", str(tmp_path / "nope")])
    assert result.exit_code == 3
    assert "coverage" not in result.stdout


def test_root_that_is_a_file_exits_three(tmp_path: Path) -> None:
    file_path = tmp_path / "x.md"
    file_path.write_text("hi\n", encoding="utf-8")
    result = runner.invoke(app, ["doctor", str(file_path)])
    assert result.exit_code == 3


def test_symlink_root_is_resolved_and_surveyed(tmp_path: Path) -> None:
    target = tmp_path / "real"
    target.mkdir()
    (target / "a.md").write_text("## Context\n", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(target, target_is_directory=True)
    result = runner.invoke(app, ["doctor", str(link)])
    assert result.exit_code == 0
    assert "markdown analyzed: 1" in result.stdout
    assert '    samples: ["a.md"]' in result.stdout


def test_hidden_root_is_surveyed(tmp_path: Path) -> None:
    root = tmp_path / ".hidden"
    root.mkdir()
    (root / "a.md").write_text("## Context\n", encoding="utf-8")
    result = runner.invoke(app, ["doctor", str(root)])
    assert result.exit_code == 0
    assert "markdown analyzed: 1" in result.stdout


def test_hidden_markdown_file_is_analyzed(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / ".hidden.md").write_text("## Context\n", encoding="utf-8")
    result = runner.invoke(app, ["doctor", str(root)])
    assert result.exit_code == 0
    assert '    samples: [".hidden.md"]' in result.stdout


def test_unreadable_markdown_is_reported_without_stopping(tmp_path: Path) -> None:
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "good.md").write_text("## Context\n", encoding="utf-8")
    (root / "bad.md").write_bytes(b"\xff\xfe\x00bad")
    result = runner.invoke(app, ["doctor", str(root)])
    assert result.exit_code == 0
    assert "markdown analyzed: 1" in result.stdout
    assert "unreadable Markdown file | count: 1 | unseen subtrees: 0" in result.stdout


def test_unreadable_root_is_surveyed_as_a_dot_skip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # an unreadable root is not an argument error: the survey reports one
    # 'unreadable directory' skip for '.' and completes with exit 0 (AC-9).
    import decision_memory.infrastructure.doctor_scanner as scanner_module

    root = tmp_path / "corpus"
    root.mkdir()

    def fake_scandir(path: str) -> object:
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(scanner_module.os, "scandir", fake_scandir)
    result = runner.invoke(app, ["doctor", str(root)])
    assert result.exit_code == 0
    assert "unreadable directory | count: 1 | unseen subtrees: 1" in result.stdout
    assert '    samples: ["."]' in result.stdout


def test_doctor_help_lists_the_command() -> None:
    result = runner.invoke(app, ["doctor", "--help"])
    assert result.exit_code == 0
    assert "--samples" in result.stdout
