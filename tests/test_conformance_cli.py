"""test-adapter CLI tests (spec 0006 AC-1, AC-16).

Exit 0 means every executed check passed; exit 1 covers manifest, adapter
loading, fixture, and conformance failures; exit 2 is reserved for a malformed
selector. The report is deterministic and shows the normative header and
summary lines.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from decision_memory.cli import app

runner = CliRunner()

_BUILTIN_MANIFEST = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "adapter_conformance"
    / "jsmastery_specs"
    / "adapter-conformance.yml"
)


class TestExitCodes:
    def test_builtin_manifest_passes_through_the_cli(self) -> None:
        result = runner.invoke(
            app,
            ["test-adapter", "jsmastery-specs", "--cases", str(_BUILTIN_MANIFEST)],
        )
        assert result.exit_code == 0
        assert "adapter: jsmastery-specs" in result.stdout
        assert "manifest: adapter-conformance.yml" in result.stdout
        assert "final: passed" in result.stdout
        assert "0 failed" in result.stdout

    def test_a_manifest_schema_failure_exits_one(self, tmp_path: Path) -> None:
        manifest = tmp_path / "bad.yml"
        manifest.write_text("schema_version: 9\ncases: []\n", encoding="utf-8")
        result = runner.invoke(
            app,
            ["test-adapter", "jsmastery-specs", "--cases", str(manifest)],
        )
        assert result.exit_code == 1
        assert "FAIL manifest.schema" in result.stdout
        assert "final: failed" in result.stdout

    def test_a_missing_manifest_path_exits_one(self, tmp_path: Path) -> None:
        missing = tmp_path / "absent.yml"
        result = runner.invoke(
            app,
            ["test-adapter", "jsmastery-specs", "--cases", str(missing)],
        )
        assert result.exit_code == 1
        assert "FAIL manifest.load" in result.stdout

    def test_a_malformed_selector_exits_two(self) -> None:
        result = runner.invoke(
            app,
            ["test-adapter", "not a selector", "--cases", str(_BUILTIN_MANIFEST)],
        )
        assert result.exit_code == 2
        assert "FAIL adapter.load" in result.stdout

    def test_a_missing_module_selector_exits_one(self) -> None:
        result = runner.invoke(
            app,
            [
                "test-adapter",
                "definitely.not_a_module:adapter",
                "--cases",
                str(_BUILTIN_MANIFEST),
            ],
        )
        assert result.exit_code == 1
        assert "FAIL adapter.load" in result.stdout

    def test_missing_cases_option_is_a_usage_error(self) -> None:
        result = runner.invoke(app, ["test-adapter", "jsmastery-specs"])
        assert result.exit_code == 2

    def test_the_report_is_deterministic(self) -> None:
        first = runner.invoke(
            app,
            ["test-adapter", "jsmastery-specs", "--cases", str(_BUILTIN_MANIFEST)],
        )
        second = runner.invoke(
            app,
            ["test-adapter", "jsmastery-specs", "--cases", str(_BUILTIN_MANIFEST)],
        )
        assert first.stdout == second.stdout
        assert first.exit_code == second.exit_code
