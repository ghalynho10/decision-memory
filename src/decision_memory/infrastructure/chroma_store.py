"""Infrastructure: Chroma vector parity for one generation (spec 0007 AC-6).

Chroma stores one cosine vector per chunk id with locator metadata only:
generation id, record id, active fingerprint, value path, and ordinal. Upsert
by the deterministic chunk id is idempotent. Before activation ingest fetches
every requested id and confirms count and metadata; query verifies every
active SQLite chunk has a matching Chroma id, fingerprint, and generation.
A valid cosine distance is finite and between 0.0 and 2.0; any other value is
store failure.

chromadb is imported lazily so importing this module stays cheap for the fast
unit suite; only the integration marked tests construct a live client.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

CHROMA_COLLECTION = "decision_chunks_v1"
CHROMA_DISTANCE = "cosine"

# The exact metadata keys Chroma carries for one vector (spec 0008 AC-6 adds
# chunk_id so semantic search can constrain by exact accepted chunk ids).
GENERATION_KEY = "generation_id"
RECORD_KEY = "record_id"
FINGERPRINT_KEY = "fingerprint"
VALUE_PATH_KEY = "value_path"
ORDINAL_KEY = "ordinal"
CHUNK_ID_KEY = "chunk_id"

_CHROMA_METADATA_KEYS = (
    GENERATION_KEY,
    RECORD_KEY,
    FINGERPRINT_KEY,
    VALUE_PATH_KEY,
    ORDINAL_KEY,
    CHUNK_ID_KEY,
)


class ChromaError(Exception):
    """A Chroma operation failed or a parity check found corruption."""


def locator_metadata(
    generation_id: str,
    record_id: str,
    fingerprint: str,
    value_path: str,
    ordinal: int,
    chunk_id: str,
) -> dict[str, str | int]:
    """The exact locator metadata map for one vector (AC-6)."""
    return {
        GENERATION_KEY: generation_id,
        RECORD_KEY: record_id,
        FINGERPRINT_KEY: fingerprint,
        VALUE_PATH_KEY: value_path,
        ORDINAL_KEY: ordinal,
        CHUNK_ID_KEY: chunk_id,
    }


def _client(persist_dir: Path | None = None) -> Any:
    """An ephemeral in memory or persistent Chroma client."""
    import chromadb
    from chromadb.config import Settings

    settings = Settings(anonymized_telemetry=False)
    if persist_dir is not None:
        persist_dir.mkdir(parents=True, exist_ok=True)
        return chromadb.PersistentClient(path=str(persist_dir), settings=settings)
    return chromadb.Client(settings=settings)


def _collection(client: Any, *, create: bool = True) -> Any:
    """The fixed cosine collection, created on demand."""
    if create:
        return client.get_or_create_collection(
            CHROMA_COLLECTION,
            metadata={"hnsw:space": CHROMA_DISTANCE},
        )
    return client.get_collection(CHROMA_COLLECTION)


def upsert_vectors(
    client: Any,
    ids: Sequence[str],
    embeddings: Sequence[Sequence[float]],
    metadatas: Sequence[Mapping[str, str | int]],
) -> None:
    """Upsert vectors by chunk id, idempotent per the deterministic id."""
    try:
        collection = _collection(client)
        collection.upsert(
            ids=list(ids),
            embeddings=[list(vector) for vector in embeddings],
            metadatas=[dict(metadata) for metadata in metadatas],
        )
    except Exception as exc:  # noqa: BLE001 - surface as ChromaError
        raise ChromaError(f"upsert failed: {type(exc).__name__}") from None


def verify_vectors(
    client: Any,
    ids: Sequence[str],
    expected_metadata: Mapping[str, Mapping[str, str | int]],
) -> list[str]:
    """Problems confirming every requested id exists with exact metadata.

    Returns a list of problem messages; an empty list means parity holds. This
    is the pre activation check: every new vector must exist with its locator
    metadata before SQLite activation (AC-6).
    """
    if not ids:
        return []
    try:
        collection = _collection(client, create=False)
        fetched = collection.get(ids=list(ids), include=["metadatas"])
    except Exception as exc:  # noqa: BLE001 - surface as ChromaError
        return [f"fetch failed: {type(exc).__name__}"]
    fetched_ids = fetched.get("ids", []) if isinstance(fetched, dict) else []
    fetched_metas = fetched.get("metadatas", []) if isinstance(fetched, dict) else []
    problems: list[str] = []
    fetched_by_id = dict(zip(fetched_ids, fetched_metas, strict=False))
    for chunk_id in ids:
        meta = fetched_by_id.get(chunk_id)
        if meta is None:
            problems.append(f"missing vector {chunk_id}")
            continue
        expected = expected_metadata.get(chunk_id)
        if expected is None:
            continue
        actual = {key: meta.get(key) for key in _CHROMA_METADATA_KEYS}
        if actual != expected:
            problems.append(f"metadata mismatch for {chunk_id}")
    if len(fetched_ids) != len(ids):
        problems.append(
            f"count mismatch: fetched {len(fetched_ids)}, expected {len(ids)}"
        )
    return problems


def is_valid_distance(distance: float) -> bool:
    """A valid cosine distance is finite and within 0.0 to 2.0 (AC-6)."""
    return distance == distance and 0.0 <= distance <= 2.0


def delete_vectors(client: Any, ids: Sequence[str]) -> None:
    """Delete vectors by id, used for old vector cleanup after activation."""
    if not ids:
        return
    try:
        collection = _collection(client, create=False)
        collection.delete(ids=list(ids))
    except Exception as exc:  # noqa: BLE001 - surface as ChromaError
        raise ChromaError(f"delete failed: {type(exc).__name__}") from None
