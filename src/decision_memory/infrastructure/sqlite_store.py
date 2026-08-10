"""Infrastructure: the authoritative SQLite index schema (spec 0007 AC-6).

SQLite is authoritative for index metadata, record state, canonical
snapshots, tags, field sources, chunks, chunk sources, metadata evidence, and
supersession links. All tables and indexes are created in one schema version 1
migration; unknown SQLite schema versions refuse. The lock database is a
separate file with its own tiny schema, never placed inside a generation.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

SQLITE_SCHEMA_VERSION = 1

# Every table and index of the authoritative generation database, created in
# one version 1 migration. TEXT holds ids, enums, digests, canonical JSON, and
# RFC3339 timestamps; INTEGER holds ordinals and token counts. Foreign keys
# are on; snapshots cascade to their tags, field sources, chunks, and metadata.
_SCHEMA_VERSION_1 = """
PRAGMA foreign_keys = ON;

CREATE TABLE index_metadata (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    store_format TEXT NOT NULL,
    sqlite_schema_version INTEGER NOT NULL,
    generation_id TEXT NOT NULL,
    pipeline_signature TEXT NOT NULL,
    semantic_manifest_digest TEXT,
    raw_manifest_digest TEXT,
    active_chunk_count INTEGER NOT NULL DEFAULT 0,
    active_chunk_id_digest TEXT NOT NULL DEFAULT '',
    records_manifest_path TEXT,
    last_ingest_time TEXT,
    source_root_hint TEXT
);

CREATE TABLE record_state (
    record_id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    action TEXT,
    desired_entry_digest TEXT,
    desired_fingerprint TEXT,
    active_fingerprint TEXT,
    record_path TEXT,
    failure_code TEXT,
    indexed_time TEXT,
    removed_time TEXT,
    removal_reason TEXT
);

CREATE TABLE record_snapshot (
    record_id TEXT PRIMARY KEY,
    active_fingerprint TEXT NOT NULL,
    record_digest TEXT NOT NULL,
    title TEXT NOT NULL,
    status TEXT,
    date TEXT,
    supersedes TEXT,
    canonical_json TEXT NOT NULL,
    FOREIGN KEY (record_id) REFERENCES record_state(record_id) ON DELETE CASCADE
);

CREATE TABLE record_tag (
    record_id TEXT NOT NULL,
    tag TEXT NOT NULL,
    PRIMARY KEY (record_id, tag),
    FOREIGN KEY (record_id) REFERENCES record_snapshot(record_id) ON DELETE CASCADE
);

CREATE TABLE field_source (
    record_id TEXT NOT NULL,
    value_path TEXT NOT NULL,
    path TEXT NOT NULL,
    section TEXT NOT NULL,
    PRIMARY KEY (record_id, value_path, path, section),
    FOREIGN KEY (record_id) REFERENCES record_snapshot(record_id) ON DELETE CASCADE
);

CREATE TABLE chunk (
    chunk_id TEXT PRIMARY KEY,
    generation_id TEXT NOT NULL,
    record_id TEXT NOT NULL,
    active_fingerprint TEXT NOT NULL,
    value_path TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    UNIQUE (generation_id, record_id, active_fingerprint, value_path, ordinal)
);

CREATE TABLE chunk_source (
    chunk_id TEXT NOT NULL,
    path TEXT NOT NULL,
    section TEXT NOT NULL,
    PRIMARY KEY (chunk_id, path, section),
    FOREIGN KEY (chunk_id) REFERENCES chunk(chunk_id) ON DELETE CASCADE
);

CREATE TABLE supersession_link (
    predecessor_id TEXT NOT NULL,
    successor_id TEXT NOT NULL,
    PRIMARY KEY (predecessor_id, successor_id)
);

CREATE TABLE metadata_evidence (
    evidence_id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    record_id TEXT NOT NULL,
    value_path TEXT NOT NULL,
    text TEXT NOT NULL
);

CREATE INDEX idx_chunk_generation ON chunk(generation_id);
CREATE INDEX idx_chunk_record ON chunk(record_id);
CREATE INDEX idx_field_source_record ON field_source(record_id);
CREATE INDEX idx_chunk_source_chunk ON chunk_source(chunk_id);
CREATE INDEX idx_metadata_evidence_record ON metadata_evidence(record_id);
CREATE INDEX idx_supersession_successor ON supersession_link(successor_id);
"""


def create_schema(connection: sqlite3.Connection) -> None:
    """Apply the version 1 migration, refusing an unknown existing schema."""
    existing = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?",
        ("index_metadata",),
    ).fetchone()
    if existing is not None:
        raise StoreSchemaError("schema already initialized")
    connection.executescript(_SCHEMA_VERSION_1)
    connection.commit()


def verify_schema_version(connection: sqlite3.Connection) -> None:
    """Raise when the SQLite schema version is not the supported one."""
    row = connection.execute(
        "SELECT sqlite_schema_version FROM index_metadata WHERE id = 1"
    ).fetchone()
    if row is None or int(row[0]) != SQLITE_SCHEMA_VERSION:
        raise StoreSchemaError(
            f"unsupported SQLite schema version {row[0] if row else 'unknown'}"
        )


def verify_integrity(connection: sqlite3.Connection) -> list[str]:
    """The SQLite integrity_check rows; nonempty means corruption (AC-21)."""
    rows = connection.execute("PRAGMA integrity_check").fetchall()
    problems = [str(row[0]) for row in rows if row and str(row[0]) != "ok"]
    return problems


def open_store_database(path: Path) -> sqlite3.Connection:
    """Open the authoritative generation database with foreign keys on."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


class StoreSchemaError(Exception):
    """The SQLite schema is missing, wrong, or unsupported."""


# ---------------------------------------------------------------------------
# The lock database (AC-9): journal_mode DELETE, foreign keys on, busy 0.
# ---------------------------------------------------------------------------

LOCK_SCHEMA_VERSION = 1


def create_lock_schema(connection: sqlite3.Connection) -> None:
    """Create the one row lock_guard table of the lock database."""
    connection.execute("PRAGMA journal_mode = DELETE")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 0")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS lock_guard (
            id INTEGER PRIMARY KEY CHECK (id = 1)
        );
        """
    )
    connection.execute("INSERT OR IGNORE INTO lock_guard (id) VALUES (1)")
    connection.commit()


def open_lock_database(path: Path) -> sqlite3.Connection:
    """Open the lock database with its fixed pragmas."""
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(path))
    connection.execute("PRAGMA journal_mode = DELETE")
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 0")
    return connection
