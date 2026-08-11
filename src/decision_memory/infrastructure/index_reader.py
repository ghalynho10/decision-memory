"""Infrastructure: the index reader, SQLite plus Chroma (spec 0007 AC-6).

Implements the application ``IndexReader`` protocol. The reader is read only:
it opens the active generation's SQLite database and Chroma collection, checks
parity, and serves retrieval. Chroma searches only the active record id and
fingerprint pairs supplied by SQLite, so orphan and retired vectors never
enter the candidate pool.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from decision_memory.application.canonical import SourceReference
from decision_memory.application.dto import (
    ActiveChunkDescriptor,
    SemanticMatches,
    SupersessionNotice,
)
from decision_memory.application.query import IndexReader
from decision_memory.infrastructure.chroma_store import (
    CHROMA_COLLECTION,
    CHUNK_ID_KEY,
    _client,
    verify_vectors,
)
from decision_memory.infrastructure.sqlite_store import (
    open_store_database,
    verify_schema_version,
)
from decision_memory.infrastructure.store import (
    generation_paths,
    read_active,
    read_format,
    read_generation_json,
)


class SqliteChromaIndexReader(IndexReader):
    """The concrete read side over one store directory."""

    def __init__(self, store_dir: Path) -> None:
        self._store_dir = store_dir

    def generation_id(self) -> str | None:
        return read_active(self._store_dir)

    def store_format(self) -> int | None:
        return read_format(self._store_dir)

    def pipeline_signature(self) -> str:
        generation_id = self.generation_id()
        if generation_id is None:
            return ""
        metadata = read_generation_json(self._store_dir, generation_id)
        return metadata.pipeline_signature if metadata is not None else ""

    def parity_problems(self) -> list[str]:
        generation_id = self.generation_id()
        if generation_id is None:
            return ["no active generation"]
        rows = self._active_chunk_rows(generation_id)
        if not rows:
            return []
        ids: list[str] = []
        expected: dict[str, dict[str, str | int]] = {}
        for row in rows:
            chunk_id = str(row[0])
            ids.append(chunk_id)
            expected[chunk_id] = {
                "generation_id": str(row[1]),
                "record_id": str(row[2]),
                "fingerprint": str(row[3]),
                "value_path": str(row[4]),
                "ordinal": int(row[5]),
                "chunk_id": chunk_id,
            }
        return verify_vectors(self._chroma_client(generation_id), ids, expected)

    def eligible_tuples(self) -> tuple[tuple[str, str, str], ...]:
        generation_id = self.generation_id()
        if generation_id is None:
            return ()
        rows = self._active_chunk_rows(generation_id)
        tuples: list[tuple[str, str, str]] = []
        for row in rows:
            candidate = (str(row[1]), str(row[2]), str(row[3]))
            if candidate not in tuples:
                tuples.append(candidate)
        return tuple(tuples)

    def active_chunks(self) -> tuple[ActiveChunkDescriptor, ...]:
        """Every active chunk with its record metadata, chunk id sorted (AC-4, AC-16).

        All reads happen in one SQLite read transaction, so the returned
        snapshot is immutable for the query. Provenance comes from the chunk
        source rows and tags from the record tag rows.
        """
        generation_id = self.generation_id()
        if generation_id is None:
            return ()
        connection = self._connection(generation_id)
        try:
            verify_schema_version(connection)
            connection.execute("BEGIN")
            try:
                rows = connection.execute(
                    "SELECT c.chunk_id, c.record_id, s.title, s.status, "
                    "c.active_fingerprint, c.value_path, c.ordinal, c.text "
                    "FROM chunk c "
                    "JOIN record_snapshot s ON s.record_id = c.record_id "
                    "ORDER BY c.chunk_id"
                ).fetchall()
                tag_rows = connection.execute(
                    "SELECT record_id, tag FROM record_tag ORDER BY record_id, tag"
                ).fetchall()
                source_rows = connection.execute(
                    "SELECT chunk_id, path, section FROM chunk_source "
                    "ORDER BY chunk_id, path, section"
                ).fetchall()
            finally:
                connection.execute("COMMIT")
            tag_lists: dict[str, list[str]] = {}
            for record_id, tag in tag_rows:
                tag_lists.setdefault(str(record_id), []).append(str(tag))
            source_lists: dict[str, list[SourceReference]] = {}
            for chunk_id, path, section in source_rows:
                source_lists.setdefault(str(chunk_id), []).append(
                    SourceReference(str(path), str(section))
                )
            descriptors = [
                ActiveChunkDescriptor(
                    chunk_id=str(row[0]),
                    record_id=str(row[1]),
                    record_title=str(row[2]),
                    record_status=str(row[3]) if row[3] is not None else None,
                    record_tags=tuple(tag_lists.get(str(row[1]), ())),
                    value_path=str(row[4]),
                    fingerprint=str(row[5]),
                    ordinal=int(row[6]),
                    text=str(row[7]),
                    provenance=tuple(source_lists.get(str(row[0]), ())),
                )
                for row in rows
            ]
            return tuple(
                sorted(descriptors, key=lambda descriptor: descriptor.chunk_id)
            )
        finally:
            connection.close()

    def semantic_search(
        self,
        embedding: Sequence[float],
        accepted_chunk_ids: Sequence[str],
    ) -> SemanticMatches:
        """Retrieve every accepted vector under the exact id constraint (AC-6).

        Requests ``n_results`` equal to the accepted count with an ``$in`` over
        the accepted chunk ids, so Chroma can never cap the result below the
        accepted set. Returned ids and distances are positionally aligned.
        """
        accepted = list(accepted_chunk_ids)
        if not accepted:
            return SemanticMatches((), ())
        generation_id = self.generation_id()
        if generation_id is None:
            return SemanticMatches((), ())
        client = self._chroma_client(generation_id)
        try:
            collection = client.get_collection(CHROMA_COLLECTION)
        except Exception:  # noqa: BLE001 - collection absent means no result
            return SemanticMatches((), ())
        where: dict[str, Any] = {CHUNK_ID_KEY: {"$in": accepted}}
        result = collection.query(
            query_embeddings=[list(embedding)],
            n_results=len(accepted),
            where=where,
            include=["distances"],
        )
        ids = result.get("ids", [[]])[0] if result.get("ids") else []
        distances = result.get("distances", [[]])[0] if result.get("distances") else []
        return SemanticMatches(tuple(ids), tuple(distances))

    def manifest_metadata(
        self,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        """Return records_manifest_path, semantic, raw digest, source root hint."""
        generation_id = self.generation_id()
        if generation_id is None:
            return (None, None, None, None)
        connection = self._connection(generation_id)
        try:
            verify_schema_version(connection)
            row = connection.execute(
                "SELECT records_manifest_path, semantic_manifest_digest, "
                "raw_manifest_digest, source_root_hint "
                "FROM index_metadata WHERE id = 1"
            ).fetchone()
            if row is None:
                return (None, None, None, None)
            return (
                str(row[0]) if row[0] is not None else None,
                str(row[1]) if row[1] is not None else None,
                str(row[2]) if row[2] is not None else None,
                str(row[3]) if row[3] is not None else None,
            )
        finally:
            connection.close()

    def ledger_fingerprints(self) -> dict[str, str | None]:
        """Live record id to desired fingerprint pairs (AC-17)."""
        generation_id = self.generation_id()
        if generation_id is None:
            return {}
        connection = self._connection(generation_id)
        try:
            verify_schema_version(connection)
            rows = connection.execute(
                "SELECT record_id, desired_fingerprint FROM record_state "
                "WHERE state != 'removed'"
            ).fetchall()
            return {
                str(row[0]): str(row[1]) if row[1] is not None else None for row in rows
            }
        finally:
            connection.close()

    def ledger_entry_digests(self) -> dict[str, str | None]:
        """Live record id to desired entry digest pairs (AC-17)."""
        generation_id = self.generation_id()
        if generation_id is None:
            return {}
        connection = self._connection(generation_id)
        try:
            verify_schema_version(connection)
            rows = connection.execute(
                "SELECT record_id, desired_entry_digest FROM record_state "
                "WHERE state != 'removed'"
            ).fetchall()
            return {
                str(row[0]): str(row[1]) if row[1] is not None else None for row in rows
            }
        finally:
            connection.close()

    def has_failed_records(self) -> bool:
        generation_id = self.generation_id()
        if generation_id is None:
            return False
        connection = self._connection(generation_id)
        try:
            verify_schema_version(connection)
            row = connection.execute(
                "SELECT 1 FROM record_state WHERE state = 'failed' LIMIT 1"
            ).fetchone()
            return row is not None
        finally:
            connection.close()

    def active_fingerprint(self, record_id: str) -> str | None:
        generation_id = self.generation_id()
        if generation_id is None:
            return None
        connection = self._connection(generation_id)
        try:
            verify_schema_version(connection)
            row = connection.execute(
                "SELECT active_fingerprint FROM chunk WHERE record_id = ? LIMIT 1",
                (record_id,),
            ).fetchone()
            return str(row[0]) if row is not None else None
        finally:
            connection.close()

    def _active_chunk_rows(
        self, generation_id: str
    ) -> list[tuple[str, str, str, str, str, int]]:
        connection = self._connection(generation_id)
        try:
            verify_schema_version(connection)
            raw = connection.execute(
                "SELECT chunk_id, generation_id, record_id, active_fingerprint, "
                "value_path, ordinal FROM chunk"
            ).fetchall()
            return [
                (
                    str(row[0]),
                    str(row[1]),
                    str(row[2]),
                    str(row[3]),
                    str(row[4]),
                    int(row[5]),
                )
                for row in raw
            ]
        finally:
            connection.close()

    def _connection(self, generation_id: str) -> Any:
        database, _, _ = generation_paths(self._store_dir, generation_id)
        return open_store_database(database)

    def _chroma_client(self, generation_id: str) -> Any:
        _, _, chroma_dir = generation_paths(self._store_dir, generation_id)
        return _client(chroma_dir)

    def supersession_notices(
        self, predecessor_id: str
    ) -> tuple[SupersessionNotice, ...]:
        """Immediate eligible successors of a predecessor, sorted by id (AC-18)."""
        generation_id = self.generation_id()
        if generation_id is None:
            return ()
        connection = self._connection(generation_id)
        try:
            verify_schema_version(connection)
            rows = connection.execute(
                "SELECT s.successor_id, snap.title, snap.status, snap.date, "
                "me.evidence_id "
                "FROM supersession_link s "
                "JOIN record_snapshot snap ON snap.record_id = s.successor_id "
                "JOIN metadata_evidence me ON me.record_id = s.successor_id "
                "WHERE s.predecessor_id = ? ORDER BY s.successor_id",
                (predecessor_id,),
            ).fetchall()
            return tuple(
                SupersessionNotice(
                    predecessor_id=predecessor_id,
                    successor_id=str(row[0]),
                    successor_title=str(row[1]),
                    successor_status=str(row[2]),
                    successor_date=str(row[3]) if row[3] is not None else None,
                    metadata_evidence_id=str(row[4]),
                )
                for row in rows
            )
        finally:
            connection.close()
