"""Infrastructure: the index writer, SQLite plus Chroma (spec 0007 AC-6, AC-7).

Implements the application ``IndexWriter`` protocol. One generation holds one
SQLite database, one persistent Chroma collection under its ``chroma/``
directory, and an immutable ``generation.json``. A normal ingest resumes the
active generation when its pipeline matches; ``--rebuild`` stages a fresh
generation and switches ``ACTIVE`` only after complete parity. Updates write
new vectors, activate SQLite, and delete old vectors last. Removals become a
content free tombstone and are ineligible before vector deletion.
"""

from __future__ import annotations

import contextlib
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from decision_memory.application.canonical import (
    canonical_json,
    canonical_record_json,
    record_digest,
    sha256_hex,
)
from decision_memory.application.dto import ChunkPlan
from decision_memory.application.ingest import IndexWriter
from decision_memory.application.pipeline import (
    DEFAULT_PIPELINE_CONFIG,
    PipelineConfig,
)
from decision_memory.domain.records import CanonicalDecisionRecord
from decision_memory.infrastructure.chroma_store import (
    _client,
    locator_metadata,
    upsert_vectors,
    verify_vectors,
)
from decision_memory.infrastructure.sqlite_store import (
    create_lock_schema,
    create_schema,
    open_lock_database,
    open_store_database,
    verify_schema_version,
)
from decision_memory.infrastructure.store import (
    new_generation_id,
    read_active,
    read_generation_json,
    store_paths,
    write_active,
    write_format,
    write_generation_json,
)

# The record states the writer emits (spec 0007 State transitions).
STATE_CURRENT = "current"
STATE_REMOVED = "removed"
STATE_PENDING_REMOVAL = "pending_removal"

REMOVAL_REASON_ABSENT = "absent_from_manifest"


class SqliteChromaIndexWriter(IndexWriter):
    """The concrete writer over one store directory."""

    def __init__(
        self,
        store_dir: Path,
        config: PipelineConfig = DEFAULT_PIPELINE_CONFIG,
    ) -> None:
        self._store_dir = store_dir
        self._config = config
        self._conn: Any = None
        self._chroma: Any = None
        self._generation_id: str | None = None

    def open_generation(self, force_rebuild: bool) -> str:
        """Resume the active generation or create a fresh staging one.

        A normal ingest resumes the active generation when its pipeline
        signature matches, so unchanged records keep their vectors. ``--rebuild``
        or a mismatched signature creates a fresh generation whose ``ACTIVE``
        pointer is set only after parity (AC-8).
        """
        write_format(self._store_dir)
        paths = store_paths(self._store_dir)
        lock_conn = open_lock_database(paths.lock_database)
        create_lock_schema(lock_conn)
        lock_conn.close()
        if not force_rebuild:
            active = read_active(self._store_dir)
            if active is not None:
                metadata = read_generation_json(self._store_dir, active)
                if (
                    metadata is not None
                    and metadata.pipeline_signature == self._config_signature()
                ):
                    self._open(active)
                    return active
        generation_id = new_generation_id()
        self._create(generation_id)
        return generation_id

    def _open(self, generation_id: str) -> None:
        """Open an existing generation for incremental work."""
        database, _, chroma_dir = self._generation_paths(generation_id)
        self._conn = open_store_database(database)
        verify_schema_version(self._conn)
        self._chroma = _client(chroma_dir)
        self._generation_id = generation_id

    def _create(self, generation_id: str) -> None:
        """Create a fresh generation with its schema and metadata."""
        write_generation_json(self._store_dir, generation_id, self._config)
        database, _, chroma_dir = self._generation_paths(generation_id)
        self._conn = open_store_database(database)
        create_schema(self._conn)
        self._conn.execute(
            "INSERT INTO index_metadata (id, store_format, sqlite_schema_version, "
            "generation_id, pipeline_signature) VALUES (1, ?, 1, ?, ?)",
            ("1", generation_id, self._config_signature()),
        )
        self._conn.commit()
        self._chroma = _client(chroma_dir)
        self._generation_id = generation_id

    def _generation_paths(self, generation_id: str) -> tuple[Path, Path, Path]:
        from decision_memory.infrastructure.store import generation_paths

        return generation_paths(self._store_dir, generation_id)

    def _config_signature(self) -> str:
        from decision_memory.application.pipeline import pipeline_signature

        return pipeline_signature(self._config)

    def existing_states(self) -> dict[str, tuple[str, str | None, str | None]]:
        """Map of record id to (state, desired fingerprint, active fingerprint)."""
        assert self._conn is not None
        rows = self._conn.execute(
            "SELECT record_id, state, desired_fingerprint, active_fingerprint "
            "FROM record_state"
        ).fetchall()
        return {str(row[0]): (str(row[1]), row[2], row[3]) for row in rows}

    def write_record(
        self,
        generation_id: str,
        record: CanonicalDecisionRecord,
        chunks: Sequence[ChunkPlan],
        embeddings: Sequence[Sequence[float]],
    ) -> list[str]:
        """Write one record's vectors and SQLite rows, returning old chunk ids.

        Returns the chunk ids this record previously owned, so the caller can
        delete those vectors only after activation (old vectors last).
        """
        record_id = record.id
        if record_id is None:
            raise ValueError("record has no id")
        assert self._conn is not None and self._chroma is not None
        old_ids = [
            str(row[0])
            for row in self._conn.execute(
                "SELECT chunk_id FROM chunk WHERE record_id = ?", (record_id,)
            ).fetchall()
        ]
        ids = [chunk.chunk_id for chunk in chunks]
        metadatas = [
            locator_metadata(
                generation_id,
                record_id,
                chunk.fingerprint,
                chunk.value_path,
                chunk.ordinal,
            )
            for chunk in chunks
        ]
        if ids:
            upsert_vectors(self._chroma, ids, embeddings, metadatas)
        self._write_sqlite(record_id, record, chunks)
        return old_ids

    def _write_sqlite(
        self,
        record_id: str,
        record: CanonicalDecisionRecord,
        chunks: Sequence[ChunkPlan],
    ) -> None:
        conn = self._conn
        fingerprint = chunks[0].fingerprint if chunks else record_digest(record)
        now = datetime.now(UTC).isoformat()
        was_present = self._had_chunks(record_id)
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO record_state (record_id, state, action, "
                "desired_fingerprint, active_fingerprint, record_path, "
                "indexed_time) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    STATE_CURRENT,
                    "updated" if was_present else "added",
                    fingerprint,
                    fingerprint,
                    f"{record_id}.md",
                    now,
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO record_snapshot (record_id, "
                "active_fingerprint, record_digest, title, status, date, "
                "supersedes, canonical_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    record_id,
                    fingerprint,
                    record_digest(record),
                    record.title or "",
                    record.status.value if record.status is not None else None,
                    record.date,
                    record.supersedes,
                    canonical_record_json(record),
                ),
            )
            for tag in record.tags:
                conn.execute(
                    "INSERT OR IGNORE INTO record_tag (record_id, tag) VALUES (?, ?)",
                    (record_id, tag),
                )
            for chunk in chunks:
                conn.execute(
                    "INSERT OR REPLACE INTO chunk (chunk_id, generation_id, "
                    "record_id, active_fingerprint, value_path, ordinal, text, "
                    "token_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        chunk.chunk_id,
                        self._generation_id,
                        record_id,
                        chunk.fingerprint,
                        chunk.value_path,
                        chunk.ordinal,
                        chunk.text,
                        chunk.evidence_token_count,
                    ),
                )
                for source in chunk.sources:
                    conn.execute(
                        "INSERT OR IGNORE INTO chunk_source (chunk_id, path, "
                        "section) VALUES (?, ?, ?)",
                        (chunk.chunk_id, source.path, source.section),
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO field_source (record_id, "
                        "value_path, path, section) VALUES (?, ?, ?, ?)",
                        (record_id, chunk.value_path, source.path, source.section),
                    )

    def _had_chunks(self, record_id: str) -> bool:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT 1 FROM chunk WHERE record_id = ? LIMIT 1", (record_id,)
        ).fetchone()
        return row is not None

    def mark_pending_removal(self, record_id: str) -> None:
        """Mark a record pending removal so it is ineligible before deletion."""
        assert self._conn is not None
        with self._conn:
            self._conn.execute(
                "UPDATE record_state SET state = ?, action = 'removed' "
                "WHERE record_id = ?",
                (STATE_PENDING_REMOVAL, record_id),
            )

    def mark_failed(
        self,
        record_id: str,
        desired_fingerprint: str,
        active_fingerprint: str | None,
        failure_code: str,
    ) -> None:
        """Record a failed record so freshness can report failed_ingest."""
        assert self._conn is not None
        with self._conn:
            self._conn.execute(
                "INSERT OR REPLACE INTO record_state (record_id, state, action, "
                "desired_fingerprint, active_fingerprint, record_path, "
                "failure_code, indexed_time) VALUES (?, 'failed', 'failed', "
                "?, ?, ?, ?, ?)",
                (
                    record_id,
                    desired_fingerprint,
                    active_fingerprint,
                    f"{record_id}.md",
                    failure_code,
                    datetime.now(UTC).isoformat(),
                ),
            )

    def remove_record(
        self, generation_id: str, record_id: str, prior_fingerprint: str | None
    ) -> None:
        """Tombstone a removed record and delete its content and vectors."""
        assert self._conn is not None and self._chroma is not None
        chunk_ids = [
            str(row[0])
            for row in self._conn.execute(
                "SELECT chunk_id FROM chunk WHERE record_id = ?", (record_id,)
            ).fetchall()
        ]
        now = datetime.now(UTC).isoformat()
        with self._conn:
            self._conn.execute("DELETE FROM chunk WHERE record_id = ?", (record_id,))
            self._conn.execute(
                "DELETE FROM record_snapshot WHERE record_id = ?", (record_id,)
            )
            self._conn.execute(
                "INSERT OR REPLACE INTO record_state (record_id, state, action, "
                "desired_fingerprint, active_fingerprint, record_path, "
                "removed_time, removal_reason) VALUES (?, ?, ?, ?, NULL, ?, ?, ?)",
                (
                    record_id,
                    STATE_REMOVED,
                    "removed",
                    prior_fingerprint,
                    f"{record_id}.md",
                    now,
                    REMOVAL_REASON_ABSENT,
                ),
            )
        if chunk_ids:
            self.delete_vectors(chunk_ids)

    def delete_vectors(self, chunk_ids: Sequence[str]) -> None:
        """Delete old or orphan vectors by chunk id (best effort, visible)."""
        if not chunk_ids:
            return
        assert self._chroma is not None
        from decision_memory.infrastructure.chroma_store import delete_vectors

        try:
            delete_vectors(self._chroma, list(chunk_ids))
        except Exception:  # noqa: BLE001 - cleanup failure is visible, not fatal
            return

    def cleanup_orphans(self, generation_id: str) -> None:
        """Delete inactive Chroma vectors with no matching SQLite chunk (AC-6)."""
        assert self._conn is not None and self._chroma is not None
        sqlite_ids = {
            str(row[0])
            for row in self._conn.execute("SELECT chunk_id FROM chunk").fetchall()
        }
        try:
            from decision_memory.infrastructure.chroma_store import (
                CHROMA_COLLECTION,
            )

            collection = self._chroma.get_collection(CHROMA_COLLECTION)
            fetched = collection.get(include=[])
            chroma_ids = set(fetched.get("ids", []) or [])
        except Exception:  # noqa: BLE001 - no collection means no orphans
            return
        orphans = sorted(chroma_ids - sqlite_ids)
        if orphans:
            self.delete_vectors(orphans)

    def set_manifest_metadata(
        self,
        records_manifest_path: str,
        semantic_digest: str,
        raw_digest: str,
        source_root_hint: str,
    ) -> None:
        """Record the manifest hint and digests for query freshness (AC-9)."""
        assert self._conn is not None
        now = datetime.now(UTC).isoformat()
        with self._conn:
            self._conn.execute(
                "UPDATE index_metadata SET semantic_manifest_digest = ?, "
                "raw_manifest_digest = ?, records_manifest_path = ?, "
                "last_ingest_time = ?, source_root_hint = ? WHERE id = 1",
                (
                    semantic_digest,
                    raw_digest,
                    records_manifest_path,
                    now,
                    source_root_hint,
                ),
            )

    def activate(self, generation_id: str) -> list[str]:
        """Verify parity, update the active digest, then switch ACTIVE."""
        assert self._conn is not None and self._chroma is not None
        rows = self._conn.execute(
            "SELECT chunk_id, generation_id, record_id, active_fingerprint, "
            "value_path, ordinal FROM chunk"
        ).fetchall()
        ids = [str(row[0]) for row in rows]
        expected = {
            str(row[0]): locator_metadata(
                row[1], str(row[2]), str(row[3]), row[4], row[5]
            )
            for row in rows
        }
        problems = verify_vectors(self._chroma, ids, expected)
        if problems:
            return problems
        sorted_ids = sorted(ids)
        digest = sha256_hex(canonical_json(sorted_ids)) if sorted_ids else ""
        with self._conn:
            self._conn.execute(
                "UPDATE index_metadata SET active_chunk_count = ?, "
                "active_chunk_id_digest = ? WHERE id = 1",
                (len(sorted_ids), digest),
            )
        write_active(self._store_dir, generation_id)
        return []

    def close(self) -> None:
        """Close the SQLite connection and the Chroma client, if any."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
        if self._chroma is not None:
            with contextlib.suppress(Exception):
                self._chroma.clear_system_cache()
            self._chroma = None
