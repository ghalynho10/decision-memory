"""Application: canonical JSON serialization and content digests.

Spec 0007 AC-2 fixes a canonical JSON form for hashing: UTF8 without BOM or
trailing LF, NFC Unicode, LF line endings, keys sorted by code point, compact
separators, JSON strings for dates, explicit null for absent scalar or object
fields, and [] for empty lists. ``record_digest`` hashes canonical record
JSON. ``entry_digest`` hashes a canonical mapping of the retrieval relevant
entry fields, including the normalized field source map. A later ingest
milestone computes the semantic manifest digest over schema version, adapter
version, source root hint, and entries sorted by id, plus a raw digest over
the exact manifest bytes.

This module is pure standard library code, so both adapt (application) and
later ingest (application) can use it. ``SourceReference`` lives here rather
than in ``adapter.py`` so the adapter contract can import the digest helpers
without a module cycle; ``adapter.py`` re exports it as part of the contract.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass

from decision_memory.domain.records import CanonicalDecisionRecord


@dataclass(frozen=True)
class SourceReference:
    """One original source location for a canonical value.

    ``path`` is a normalized POSIX relative path (no absolute form, no ``..``,
    no empty segment, no trailing slash). ``section`` is the exact heading the
    value came from, without Markdown markers; the reserved value ``preamble``
    names source metadata before the first H2 (spec 0007 AC-19).
    """

    path: str
    section: str


def sha256_hex(text: str) -> str:
    """Lowercase 64 character SHA256 over the UTF8 encoding of ``text``."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_field_sources(
    field_sources: dict[str, list[SourceReference]],
) -> dict[str, tuple[SourceReference, ...]]:
    """References deduplicated and sorted by path then section, keys by path.

    The exact normalization rule from spec 0007: within each value path the
    references lose duplicates and sort by (path, section), and the value
    paths themselves sort by code point. The result is stable for hashing and
    for the manifest.
    """
    normalized: dict[str, tuple[SourceReference, ...]] = {}
    for path in sorted(field_sources):
        seen: set[tuple[str, str]] = set()
        refs: list[SourceReference] = []
        for ref in field_sources[path]:
            key = (ref.path, ref.section)
            if key not in seen:
                seen.add(key)
                refs.append(ref)
        refs.sort(key=lambda ref: (ref.path, ref.section))
        normalized[path] = tuple(refs)
    return normalized


def _normalize(value: object) -> object:
    """NFC Unicode, LF line endings, and recursed dict/list normalization."""
    if isinstance(value, str):
        return (
            unicodedata.normalize("NFC", value)
            .replace("\r\n", "\n")
            .replace("\r", "\n")
        )
    if isinstance(value, dict):
        return {str(key): _normalize(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(item) for item in value]
    return value


def canonical_json(value: object) -> str:
    """Compact canonical JSON: sorted keys, no spaces, no trailing LF."""
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def canonical_record_mapping(record: CanonicalDecisionRecord) -> dict[str, object]:
    """The full fixed canonical shape: every spec 0002 field, nulls explicit.

    Keys are sorted by code point when serialized. Absent scalar or object
    fields are null; empty lists are []; dates are JSON strings; status and
    evidence kind use their enum values.
    """
    return {
        "id": record.id,
        "title": record.title,
        "status": record.status.value if record.status is not None else None,
        "date": record.date,
        "body": record.body,
        "context": (
            {
                "problem": record.context.problem,
                "triggering_change": record.context.triggering_change,
            }
            if record.context is not None
            else None
        ),
        "decision": (
            {
                "chosen": record.decision.chosen,
                "alternatives": [
                    {
                        "title": alternative.title,
                        "rejection_reason": alternative.rejection_reason,
                    }
                    for alternative in record.decision.alternatives
                ],
            }
            if record.decision is not None
            else None
        ),
        "why": list(record.why),
        "rationale_summary": record.rationale_summary,
        "consequences": (
            {
                "positive": list(record.consequences.positive),
                "negative": list(record.consequences.negative),
            }
            if record.consequences is not None
            else None
        ),
        "evidence": (
            [
                {
                    "kind": entry.kind.value if entry.kind is not None else None,
                    "target": entry.target,
                    "note": entry.note,
                }
                for entry in record.evidence
            ]
            if record.evidence is not None
            else None
        ),
        "tags": list(record.tags),
        "supersedes": record.supersedes,
    }


def canonical_record_json(record: CanonicalDecisionRecord) -> str:
    """Canonical JSON of one canonical record, for record_digest."""
    return canonical_json(canonical_record_mapping(record))


def record_digest(record: CanonicalDecisionRecord) -> str:
    """SHA256 over canonical record JSON (spec 0007 AC-2)."""
    return sha256_hex(canonical_record_json(record))


def entry_digest(
    *,
    record_id: str,
    fingerprint: str,
    contributing_files: Iterable[str],
    record_path: str,
    record_digest_value: str,
    field_sources: dict[str, list[SourceReference]],
) -> str:
    """SHA256 over canonical JSON of the retrieval relevant entry fields."""
    mapping: dict[str, object] = {
        "id": record_id,
        "fingerprint": fingerprint,
        "contributing_files": list(contributing_files),
        "record_path": record_path,
        "record_digest": record_digest_value,
        "field_sources": {
            path: [{"path": ref.path, "section": ref.section} for ref in refs]
            for path, refs in normalize_field_sources(field_sources).items()
        },
    }
    return sha256_hex(canonical_json(mapping))
