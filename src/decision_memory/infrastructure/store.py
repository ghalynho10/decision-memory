"""Infrastructure: the versioned store layout and generations (spec 0007).

The store format version is 2 (spec 0008 AC-12) with a fixed layout:

.. code-block:: text

    query-index/
      FORMAT
      ACTIVE
      lock.sqlite3
      generations/
        <generation-id>/
          records.sqlite3
          generation.json
          chroma/

``FORMAT`` holds ``1`` plus LF. ``ACTIVE`` holds one generation id plus LF
and is replaced by an atomic same directory rename. A generation id is a
lowercase UUID hex value. ``generation.json`` holds the immutable format
version, generation id, initial pipeline signature, and creation time. The
lock database is never placed inside or replaced with a generation.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from decision_memory.application.pipeline import (
    DEFAULT_PIPELINE_CONFIG,
    PipelineConfig,
    pipeline_signature,
)
from decision_memory.application.store_format import STORE_FORMAT_VERSION

FORMAT_FILENAME = "FORMAT"
ACTIVE_FILENAME = "ACTIVE"
LOCK_DATABASE = "lock.sqlite3"
GENERATIONS_DIR = "generations"
RECORDS_DATABASE = "records.sqlite3"
GENERATION_JSON = "generation.json"
CHROMA_DIR = "chroma"


@dataclass(frozen=True)
class StorePaths:
    """The resolved paths of one store."""

    root: Path
    format_file: Path
    active_file: Path
    lock_database: Path
    generations_dir: Path


def store_paths(store_dir: Path) -> StorePaths:
    """The fixed layout paths beneath ``store_dir``."""
    return StorePaths(
        root=store_dir,
        format_file=store_dir / FORMAT_FILENAME,
        active_file=store_dir / ACTIVE_FILENAME,
        lock_database=store_dir / LOCK_DATABASE,
        generations_dir=store_dir / GENERATIONS_DIR,
    )


def new_generation_id() -> str:
    """A fresh lowercase UUID hex generation id."""
    return uuid.uuid4().hex


def generation_dir(store_dir: Path, generation_id: str) -> Path:
    """The directory of one generation."""
    return store_dir / GENERATIONS_DIR / generation_id


def generation_paths(store_dir: Path, generation_id: str) -> tuple[Path, Path, Path]:
    """(records database, generation json, chroma dir) for one generation."""
    root = generation_dir(store_dir, generation_id)
    return root / RECORDS_DATABASE, root / GENERATION_JSON, root / CHROMA_DIR


@dataclass(frozen=True)
class GenerationMetadata:
    """The immutable generation.json contents."""

    format_version: int
    generation_id: str
    pipeline_signature: str
    created_at: str


def write_format(store_dir: Path) -> None:
    """Write FORMAT with the store format version, creating the directory."""
    store_dir.mkdir(parents=True, exist_ok=True)
    paths = store_paths(store_dir)
    _atomic_write_text(paths.format_file, f"{STORE_FORMAT_VERSION}\n")


def read_format(store_dir: Path) -> int | None:
    """The store format version, or None when FORMAT is absent or invalid."""
    path = store_paths(store_dir).format_file
    if not path.is_file():
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def write_active(store_dir: Path, generation_id: str) -> None:
    """Atomically replace ACTIVE with the new generation id."""
    paths = store_paths(store_dir)
    paths.root.mkdir(parents=True, exist_ok=True)
    _atomic_write_text(paths.active_file, f"{generation_id}\n")


def read_active(store_dir: Path) -> str | None:
    """The active generation id, or None when absent or invalid."""
    path = store_paths(store_dir).active_file
    if not path.is_file():
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value if value else None


def write_generation_json(
    store_dir: Path,
    generation_id: str,
    config: PipelineConfig = DEFAULT_PIPELINE_CONFIG,
) -> GenerationMetadata:
    """Write generation.json and return its contents."""
    metadata = GenerationMetadata(
        format_version=STORE_FORMAT_VERSION,
        generation_id=generation_id,
        pipeline_signature=pipeline_signature(config),
        created_at=datetime.now(UTC).isoformat(),
    )
    directory = generation_dir(store_dir, generation_id)
    directory.mkdir(parents=True, exist_ok=True)
    payload = {
        "format_version": metadata.format_version,
        "generation_id": metadata.generation_id,
        "pipeline_signature": metadata.pipeline_signature,
        "created_at": metadata.created_at,
    }
    _atomic_write_text(
        directory / GENERATION_JSON,
        json.dumps(payload, indent=2) + "\n",
    )
    return metadata


def read_generation_json(
    store_dir: Path, generation_id: str
) -> GenerationMetadata | None:
    """The generation metadata, or None when unreadable or invalid."""
    path = generation_dir(store_dir, generation_id) / GENERATION_JSON
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    try:
        return GenerationMetadata(
            format_version=int(data["format_version"]),
            generation_id=str(data["generation_id"]),
            pipeline_signature=str(data["pipeline_signature"]),
            created_at=str(data["created_at"]),
        )
    except (KeyError, TypeError, ValueError):
        return None


def _atomic_write_text(path: Path, text: str) -> None:
    """Write via a same directory temp file and atomic rename."""
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)
