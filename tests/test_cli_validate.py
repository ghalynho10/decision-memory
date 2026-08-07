"""End to end tests for the CLI validate command.

These write temp files and run the command through Typer's CliRunner. The
project root is passed explicitly so the path scan and git checks are
deterministic regardless of where the test runs from.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from decision_memory.cli import app

runner = CliRunner()


def _record_text(*, target: str = "source.md", commit: bool = False) -> str:
    evidence = (
        f"  - kind: commit\n    target: {target}\n"
        if commit
        else f"  - kind: file\n    target: {target}\n"
    )
    return (
        "---\n"
        'id: "0001"\n'
        "title: A decision\n"
        "status: accepted\n"
        "decision:\n"
        "  chosen: Chosen option\n"
        "why:\n"
        "  - Because it is better\n"
        "evidence:\n"
        f"{evidence}"
        "---\n"
    )


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


class TestValidateCommand:
    def test_valid_record_exits_zero(self, tmp_path: Path) -> None:
        _write(tmp_path / "source.md", "source")
        record = _write(tmp_path / "record.md", _record_text())
        result = runner.invoke(
            app, ["validate", str(record), "--project-root", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "valid record, no violations" in result.stdout

    def test_violations_print_severity_rule_field_reason(self, tmp_path: Path) -> None:
        record = _write(
            tmp_path / "record.md",
            _record_text().replace("title: A decision\n", "title: \n"),
        )
        result = runner.invoke(
            app, ["validate", str(record), "--project-root", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "error" in result.stdout
        assert "required.missing" in result.stdout
        assert "title" in result.stdout

    def test_unparseable_file_exits_three_with_no_rule_violations(
        self, tmp_path: Path
    ) -> None:
        record = _write(tmp_path / "record.md", "no frontmatter here\n")
        result = runner.invoke(
            app, ["validate", str(record), "--project-root", str(tmp_path)]
        )
        assert result.exit_code == 3
        assert "file.no_frontmatter" in result.stdout
        assert "required.missing" not in result.stdout

    def test_unresolved_evidence_exits_one(self, tmp_path: Path) -> None:
        _write(tmp_path / "source.md", "source")
        record = _write(tmp_path / "record.md", _record_text(target="missing.md"))
        result = runner.invoke(
            app, ["validate", str(record), "--project-root", str(tmp_path)]
        )
        assert result.exit_code == 1
        assert "evidence.path_unresolved" in result.stdout
        assert "evidence[0].target" in result.stdout

    def test_git_unavailable_warns_but_exits_zero(self, tmp_path: Path) -> None:
        record = _write(
            tmp_path / "record.md", _record_text(target="abcdef0", commit=True)
        )
        result = runner.invoke(
            app, ["validate", str(record), "--project-root", str(tmp_path)]
        )
        assert result.exit_code == 0
        assert "context.git_unavailable" in result.stdout
        assert "evidence.commit_unresolved" not in result.stdout
