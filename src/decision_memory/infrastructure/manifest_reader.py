"""Infrastructure: load the schema version 2 output manifest and its records.

Spec 0007 AC-2: the adapter output manifest is schema version 2. A reader that
meets an older or missing version fails clearly and points the user at
``adapt`` again. This module also computes the raw manifest digest over the
exact bytes and loads canonical record files, so ingest never needs the source
corpus or an adapter.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from decision_memory.application.adapter import Manifest, ManifestEntry
from decision_memory.application.canonical import (
    SourceReference,
    sha256_bytes,
)
from decision_memory.domain.records import CanonicalDecisionRecord
from decision_memory.infrastructure.file_reader import parse_record_file

MANIFEST_FILENAME = "manifest.json"


class ManifestError(Exception):
    """The manifest is missing, malformed, or not schema version 2."""


class RecordReadError(Exception):
    """A canonical record file cannot be read or parsed."""


def manifest_path(records_dir: Path) -> Path:
    """The manifest path inside a records directory."""
    return records_dir / MANIFEST_FILENAME


def load_manifest(path: Path) -> Manifest:
    """Load and validate a schema version 2 manifest."""
    if not path.is_file():
        raise ManifestError(f"manifest not found at {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raise ManifestError(f"manifest at {path} is not valid JSON") from None
    if not isinstance(data, dict):
        raise ManifestError("manifest must be a JSON object")
    if data.get("schema_version") != 2:
        version = data.get("schema_version")
        raise ManifestError(
            f"manifest schema version is {version!r}, expected 2; run adapt again"
        )
    entries: list[ManifestEntry] = []
    for entry in data.get("entries", []):
        if not isinstance(entry, dict):
            raise ManifestError("a manifest entry is not a JSON object")
        entries.append(
            ManifestEntry(
                id=str(entry["id"]),
                fingerprint=str(entry["fingerprint"]),
                contributing_files=[
                    str(item) for item in entry.get("contributing_files", [])
                ],
                record_path=str(entry.get("record_path", "")),
                record_digest=str(entry.get("record_digest", "")),
                entry_digest=str(entry.get("entry_digest", "")),
                field_sources=_field_sources(entry.get("field_sources")),
            )
        )
    return Manifest(
        schema_version=2,
        adapter_version=str(data.get("adapter_version", "")),
        generated_at=str(data.get("generated_at", "")),
        source_root_hint=str(data.get("source_root_hint", "")),
        entries=entries,
        skipped=[],
        collisions=[],
    )


def _field_sources(raw: object) -> dict[str, list[SourceReference]]:
    result: dict[str, list[SourceReference]] = {}
    if not isinstance(raw, dict):
        return result
    for value_path, refs in raw.items():
        if not isinstance(refs, list):
            continue
        resolved: list[SourceReference] = []
        for ref in refs:
            if not isinstance(ref, dict):
                continue
            ref_path = ref.get("path")
            section = ref.get("section")
            if isinstance(ref_path, str) and isinstance(section, str):
                resolved.append(SourceReference(path=ref_path, section=section))
        if resolved:
            result[str(value_path)] = resolved
    return result


def raw_manifest_digest(path: Path) -> str:
    """The raw manifest digest over the exact bytes (AC-9)."""
    return sha256_bytes(path.read_bytes())


def record_loader(records_dir: Path) -> Callable[[str], CanonicalDecisionRecord]:
    """A callable reading one canonical record file by record id."""

    def load(record_id: str) -> CanonicalDecisionRecord:
        path = records_dir / f"{record_id}.md"
        parsed = parse_record_file(path)
        if parsed.record is None:
            raise RecordReadError(f"cannot parse record {record_id} at {path}")
        return parsed.record

    return load
