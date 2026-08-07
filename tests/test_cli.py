"""Smoke tests for the CLI shell and package metadata.

These are plain unit tests: they stub nothing and call no external services.
"""

from typer.testing import CliRunner

from decision_memory import __version__
from decision_memory.cli import app

runner = CliRunner()


def test_version_command_prints_version() -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_args_shows_command_shell() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "decision-memory" in result.stdout


def test_version_is_a_string() -> None:
    assert isinstance(__version__, str)
    assert len(__version__) > 0
