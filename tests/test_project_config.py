"""Project config discovery, parsing, and precedence (spec 0005 AC-10 to AC-13)."""

from __future__ import annotations

from pathlib import Path

import pytest
from spec_factory import make_corpus, write_spec
from typer.testing import CliRunner

from decision_memory.application.settings import (
    SettingsError,
    resolve_runtime_settings,
)
from decision_memory.cli import app
from decision_memory.infrastructure.project_config import (
    ProjectConfig,
    ProjectConfigError,
    load_project_config,
)

runner = CliRunner()

CONFIG = "adapter: vendor.runtime:adapter\ncorpus_root: ./corpus\noutput: ./out\n"


def _write_config(directory: Path, text: str) -> Path:
    path = directory / ".decision-memory.yml"
    path.write_text(text, encoding="utf-8")
    return path


class TestLoadProjectConfig:
    def test_missing_config_is_not_an_error(self, tmp_path: Path) -> None:
        assert load_project_config(tmp_path) is None

    def test_finds_the_nearest_file_from_a_nested_directory(
        self,
        tmp_path: Path,
    ) -> None:
        _write_config(tmp_path, "adapter: vendor.runtime:adapter\n")
        nested = tmp_path / "a" / "b"
        nested.mkdir(parents=True)
        found = load_project_config(nested)
        assert found is not None
        path, config = found
        assert path == tmp_path / ".decision-memory.yml"
        assert config.adapter == "vendor.runtime:adapter"

    def test_prefers_the_nearest_over_an_outer_file(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "adapter: outer\n")
        inner = tmp_path / "inner"
        inner.mkdir()
        _write_config(inner, "adapter: inner\n")
        found = load_project_config(inner)
        assert found is not None
        assert found[1].adapter == "inner"

    def test_stops_at_the_git_root(self, tmp_path: Path) -> None:
        # A config above the git root must not be found from inside the repo.
        (tmp_path / ".git").mkdir()
        _write_config(tmp_path.parent, "adapter: above-repo\n")
        assert load_project_config(tmp_path) is None

    def test_finds_a_config_at_the_git_root(self, tmp_path: Path) -> None:
        (tmp_path / ".git").mkdir()
        _write_config(tmp_path, "adapter: at-root\n")
        nested = tmp_path / "src"
        nested.mkdir()
        found = load_project_config(nested)
        assert found is not None
        assert found[1].adapter == "at-root"

    def test_empty_document_is_an_empty_config(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "")
        found = load_project_config(tmp_path)
        assert found is not None
        config = found[1]
        assert config.adapter is None
        assert config.corpus_root is None
        assert config.output is None

    def test_relative_paths_resolve_against_the_config_directory(
        self,
        tmp_path: Path,
    ) -> None:
        _write_config(tmp_path, "corpus_root: ./corpus\noutput: ./out\n")
        found = load_project_config(tmp_path)
        assert found is not None
        config = found[1]
        assert config.corpus_root == (tmp_path / "corpus").resolve()
        assert config.output == (tmp_path / "out").resolve()

    def test_absolute_paths_stay_absolute(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "corpus_root: /tmp/somewhere\n")
        found = load_project_config(tmp_path)
        assert found is not None
        assert found[1].corpus_root == Path("/tmp/somewhere").resolve()

    def test_unreadable_file_names_the_path(self, tmp_path: Path) -> None:
        path = _write_config(tmp_path, "adapter: x\n")
        path.chmod(0)
        try:
            with pytest.raises(ProjectConfigError) as excinfo:
                load_project_config(tmp_path)
            assert str(path) in excinfo.value.message
        finally:
            path.chmod(0o644)

    def test_invalid_yaml_names_the_path_and_error(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "adapter: [unclosed\n")
        with pytest.raises(ProjectConfigError) as excinfo:
            load_project_config(tmp_path)
        assert "invalid YAML" in excinfo.value.message
        assert str(tmp_path / ".decision-memory.yml") in str(excinfo.value)

    def test_nonmapping_root_is_rejected(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "- one\n- two\n")
        with pytest.raises(ProjectConfigError) as excinfo:
            load_project_config(tmp_path)
        assert "mapping" in excinfo.value.message

    def test_unknown_key_is_rejected(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "adapter: x\ncorpus: ./c\n")
        with pytest.raises(ProjectConfigError) as excinfo:
            load_project_config(tmp_path)
        assert "corpus" in excinfo.value.message

    def test_wrong_type_is_rejected(self, tmp_path: Path) -> None:
        _write_config(tmp_path, "corpus_root: [1, 2]\n")
        with pytest.raises(ProjectConfigError) as excinfo:
            load_project_config(tmp_path)
        assert "corpus_root" in excinfo.value.message


class TestResolveRuntimeSettings:
    def _config(
        self,
        *,
        adapter: str | None = None,
        corpus: Path | None = None,
        output: Path | None = None,
    ) -> ProjectConfig:
        return ProjectConfig(adapter=adapter, corpus_root=corpus, output=output)

    def test_adapter_resolves_command_then_config_then_default(self) -> None:
        config = self._config(adapter="config.runtime:adapter")
        assert (
            resolve_runtime_settings(
                cli_corpus=Path("c"),
                cli_adapter="cli.runtime:adapter",
                cli_output=None,
                config=config,
            ).adapter
            == "cli.runtime:adapter"
        )
        assert (
            resolve_runtime_settings(
                cli_corpus=Path("c"), cli_adapter=None, cli_output=None, config=config
            ).adapter
            == "config.runtime:adapter"
        )
        resolved = resolve_runtime_settings(
            cli_corpus=Path("c"), cli_adapter=None, cli_output=None, config=None
        )
        assert resolved.adapter == "jsmastery-specs"

    def test_missing_corpus_root_is_a_settings_error(self) -> None:
        result = resolve_runtime_settings(
            cli_corpus=None, cli_adapter=None, cli_output=None, config=None
        )
        assert isinstance(result, SettingsError)
        assert "corpus" in result.message

    def test_corpus_root_resolves_command_then_config(self) -> None:
        config = self._config(corpus=Path("/cfg/corpus"))
        assert resolve_runtime_settings(
            cli_corpus=Path("/cli"), cli_adapter=None, cli_output=None, config=config
        ).corpus_root == Path("/cli")
        assert resolve_runtime_settings(
            cli_corpus=None, cli_adapter=None, cli_output=None, config=config
        ).corpus_root == Path("/cfg/corpus")

    def test_output_resolves_command_then_config_then_corpus_default(self) -> None:
        config = self._config(corpus=Path("/cfg/corpus"), output=Path("/cfg/out"))
        resolved = resolve_runtime_settings(
            cli_corpus=None,
            cli_adapter=None,
            cli_output=Path("/cli/out"),
            config=config,
        )
        assert resolved.output == Path("/cli/out")
        resolved = resolve_runtime_settings(
            cli_corpus=None, cli_adapter=None, cli_output=None, config=config
        )
        assert resolved.output == Path("/cfg/out")
        config = self._config(corpus=Path("/cfg/corpus"))
        resolved = resolve_runtime_settings(
            cli_corpus=None, cli_adapter=None, cli_output=None, config=config
        )
        assert resolved.output == Path("/cfg/corpus") / ".decision-memory" / "records"

    def test_configured_corpus_root_anchors_the_default_output(self) -> None:
        # AC-12: the output default derives from the resolved corpus root, so
        # a configured absolute root anchors it regardless of the cwd.
        config = self._config(corpus=Path("/abs/corpus"))
        resolved = resolve_runtime_settings(
            cli_corpus=None, cli_adapter=None, cli_output=None, config=config
        )
        assert resolved.output == Path("/abs/corpus") / ".decision-memory" / "records"


class TestCliConfig:
    def test_adapt_uses_configured_corpus_root(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        corpus = make_corpus(tmp_path)
        write_spec(corpus, "0001-first")
        _write_config(tmp_path, f"corpus_root: {corpus}\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["adapt"])
        assert result.exit_code == 0
        assert "written DM-0001" in result.stdout

    def test_adapt_command_argument_overrides_config(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        corpus = make_corpus(tmp_path)
        write_spec(corpus, "0001-first")
        other = make_corpus(tmp_path / "other")
        write_spec(other, "0002-second")
        _write_config(tmp_path, f"corpus_root: {corpus}\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["adapt", str(other)])
        assert result.exit_code == 0
        assert "written DM-0002" in result.stdout

    def test_adapt_missing_corpus_and_no_config_exits_two(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["adapt"])
        assert result.exit_code == 2
        assert "corpus" in result.stdout

    def test_adapt_config_output_anchors_writes(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        corpus = make_corpus(tmp_path)
        write_spec(corpus, "0001-first")
        _write_config(tmp_path, f"corpus_root: {corpus}\noutput: ./out\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["adapt"])
        assert result.exit_code == 0
        assert (tmp_path / "out" / "DM-0001.md").is_file()

    def test_validate_uses_configured_corpus_root(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        corpus = make_corpus(tmp_path)
        write_spec(corpus, "0001-first")
        _write_config(tmp_path, f"corpus_root: {corpus}\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 0
        assert "ok DM-0001" in result.stdout

    def test_validate_no_config_exits_two(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["validate"])
        assert result.exit_code == 2

    def test_malformed_config_exits_one_and_names_the_path(
        self,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        corpus = make_corpus(tmp_path)
        write_spec(corpus, "0001-first")
        _write_config(tmp_path, "corpus_root: [bad\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["adapt", str(corpus)])
        assert result.exit_code == 1
        assert ".decision-memory.yml" in result.stdout
        assert "invalid YAML" in result.stdout

    def test_unknown_key_exits_one(self, tmp_path: Path, monkeypatch) -> None:
        corpus = make_corpus(tmp_path)
        write_spec(corpus, "0001-first")
        _write_config(tmp_path, "corpus_root: ./c\ncorpus: ./other\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["adapt", str(corpus)])
        assert result.exit_code == 1
        assert "corpus" in result.stdout
