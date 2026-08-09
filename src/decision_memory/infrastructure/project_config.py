"""Infrastructure: strict project config discovery and parsing.

Spec 0005 AC-10 to AC-13. ``.decision-memory.yml`` is an optional one mapping
with ``adapter``, ``corpus_root``, and ``output`` string fields. Discovery
searches from the starting directory upward, uses the nearest file, and stops
at the nearest Git repository root when inside one, or the filesystem root
otherwise. PyYAML ``safe_load`` reads it, then a Pydantic model with
``extra="forbid"`` rejects unknown keys and wrong types. Relative path strings
resolve against the config file directory before precedence is applied.

A missing config file is not an error. An unreadable file, invalid YAML,
nonmapping root, unknown key, or invalid field raises ``ProjectConfigError``,
naming the config path and the precise parse or schema error.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, ValidationError

CONFIG_FILENAME = ".decision-memory.yml"


@dataclass(frozen=True)
class ProjectConfig:
    """The parsed project settings, paths resolved against the config file.

    There is one object per discovered file and no persistence beyond that
    file. Every field is optional; an empty YAML document is an empty config.
    """

    adapter: str | None = None
    corpus_root: Path | None = None
    output: Path | None = None


class ProjectConfigModel(BaseModel):
    """The strict schema over the config mapping (AC-11).

    ``extra="forbid"`` rejects an unknown key, and field types are enforced,
    so a misspelled setting never silently selects a default.
    """

    model_config = ConfigDict(extra="forbid")

    adapter: str | None = None
    corpus_root: str | None = None
    output: str | None = None


class ProjectConfigError(Exception):
    """A config file was found but could not be used (AC-13)."""

    def __init__(self, path: Path, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


def load_project_config(start: Path) -> tuple[Path, ProjectConfig] | None:
    """Find and parse the nearest ``.decision-memory.yml``, or None when absent.

    ``start`` is the directory the search begins from (the current directory
    in the CLI). Raises ``ProjectConfigError`` when a found file cannot be
    read or parsed.
    """
    config_path = _find_config(start)
    if config_path is None:
        return None
    return config_path, _read_config(config_path)


def _find_config(start: Path) -> Path | None:
    """The nearest config file from ``start`` upward within the search boundary."""
    current = start.resolve()
    while True:
        candidate = current / CONFIG_FILENAME
        if candidate.is_file():
            return candidate
        if (current / ".git").exists():
            # The nearest Git repository root is the search boundary; the root
            # itself was already checked for the file above (AC-10).
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _read_config(path: Path) -> ProjectConfig:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ProjectConfigError(path, f"cannot read config: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ProjectConfigError(path, f"invalid YAML: {exc}") from exc
    if data is None:
        # An empty YAML document is an empty configuration (AC-11).
        data = {}
    if not isinstance(data, dict):
        raise ProjectConfigError(path, "config root must be a mapping")
    try:
        model = ProjectConfigModel.model_validate(data)
    except ValidationError as exc:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ProjectConfigError(path, f"invalid config: {details}") from exc
    base = path.parent
    return ProjectConfig(
        adapter=model.adapter,
        corpus_root=(
            _resolve_path(model.corpus_root, base) if model.corpus_root else None
        ),
        output=_resolve_path(model.output, base) if model.output else None,
    )


def _resolve_path(value: str, base: Path) -> Path:
    """Resolve a configured path string against the config file directory."""
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (base / path).resolve()
