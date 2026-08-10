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
from decision_memory.application.dto import SupersessionNotice
from decision_memory.application.query import (
    CANDIDATE_LIMIT,
    IndexReader,
    RetrievedChunk,
)
from decision_memory.infrastructure.chroma_store import (
    CHROMA_COLLECTION,
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
    read_generation_json,
)


class SqliteChromaIndexReader(IndexReader):
    """The concrete read side over one store directory."""

    def __init__(self, store_dir: Path) -> None:
        self._store_dir = store_dir

    def generation_id(self) -> str | None:
        return read_active(self._store_dir)

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

    def search(
        self,
        embedding: Sequence[float],
        eligible: Sequence[tuple[str, str, str]],
        limit: int = CANDIDATE_LIMIT,
    ) -> list[tuple[str, float]]:
        generation_id = self.generation_id()
        if generation_id is None:
            return []
        client = self._chroma_client(generation_id)
        try:
            collection = client.get_collection(CHROMA_COLLECTION)
        except Exception:  # noqa: BLE001 - collection absent means no result
            return []
        if len(eligible) == 1:
            generation, record_id, fingerprint = eligible[0]
            where: dict[str, Any] = {
                "$and": [
                    {"generation_id": generation},
                    {"record_id": record_id},
                    {"fingerprint": fingerprint},
                ]
            }
        else:
            where = {
                "$or": [
                    {
                        "$and": [
                            {"generation_id": generation},
                            {"record_id": record_id},
                            {"fingerprint": fingerprint},
                        ]
                    }
                    for generation, record_id, fingerprint in eligible
                ]
            }
        result = collection.query(
            query_embeddings=[list(embedding)],
            n_results=limit,
            where=where,
            include=["distances"],
        )
        ids = result.get("ids", [[]])[0] if result.get("ids") else []
        distances = result.get("distances", [[]])[0] if result.get("distances") else []
        return list(zip(ids, distances, strict=False))

    def chunk(self, chunk_id: str) -> RetrievedChunk | None:
        generation_id = self.generation_id()
        if generation_id is None:
            return None
        connection = self._connection(generation_id)
        try:
            row = connection.execute(
                "SELECT c.chunk_id, c.generation_id, c.record_id, "
                "c.active_fingerprint, c.value_path, c.ordinal, c.text, "
                "s.title, s.status "
                "FROM chunk c JOIN record_snapshot s ON s.record_id = c.record_id "
                "WHERE c.chunk_id = ?",
                (chunk_id,),
            ).fetchone()
            if row is None:
                return None
            sources = tuple(
                SourceReference(path=item[0], section=item[1])
                for item in connection.execute(
                    "SELECT path, section FROM chunk_source WHERE chunk_id = ?",
                    (chunk_id,),
                ).fetchall()
            )
            return RetrievedChunk(
                chunk_id=row[0],
                record_id=row[2],
                value_path=row[4],
                fingerprint=row[3],
                ordinal=row[5],
                text=row[6],
                sources=sources,
                record_title=row[7],
                record_status=row[8],
            )
        finally:
            connection.close()

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
