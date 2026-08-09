"""Application: runtime settings resolution (spec 0005 AC-12).

Each setting resolves from command input, then configuration, then its
default: ``adapter`` defaults to the built in ``jsmastery-specs``; a missing
corpus root after precedence is a usage error (exit 2); ``output`` defaults to
``<resolved corpus_root>/.decision-memory/records``. The output default is
derived only after corpus root resolution, so a configured corpus root anchors
the default output regardless of the current directory. This use case is pure:
configuration parsing lives in infrastructure and crosses inward as a plain
``ProjectConfig``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from decision_memory.application.adapter import (
    BUILTIN_ADAPTER_ID,
    DEFAULT_RECORDS_DIR,
)
from decision_memory.infrastructure.project_config import ProjectConfig


@dataclass(frozen=True)
class RuntimeSettings:
    """The resolved settings a command runs with."""

    adapter: str
    corpus_root: Path
    output: Path


@dataclass(frozen=True)
class SettingsError:
    """A required setting was absent after precedence resolution."""

    message: str


def resolve_runtime_settings(
    *,
    cli_corpus: Path | None,
    cli_adapter: str | None,
    cli_output: Path | None,
    config: ProjectConfig | None,
) -> RuntimeSettings | SettingsError:
    """Resolve adapter, corpus root, and output by precedence (AC-12)."""
    adapter = (
        cli_adapter
        or (config.adapter if config is not None else None)
        or BUILTIN_ADAPTER_ID
    )
    corpus_root = cli_corpus or (config.corpus_root if config is not None else None)
    if corpus_root is None:
        return SettingsError(
            "no corpus path given; pass one or set corpus_root in .decision-memory.yml"
        )
    output = (
        cli_output
        or (config.output if config is not None else None)
        or corpus_root / DEFAULT_RECORDS_DIR
    )
    return RuntimeSettings(adapter=adapter, corpus_root=corpus_root, output=output)
