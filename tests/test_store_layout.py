"""Store layout and SQLite schema tests (spec 0007 AC-6).

Covers the FORMAT, ACTIVE, generation id, and generation.json primitives,
plus the one migration SQLite schema and the lock database schema.
"""

from __future__ import annotations

import pytest

from decision_memory.infrastructure.sqlite_store import (
    StoreSchemaError,
    create_lock_schema,
    create_schema,
    open_lock_database,
    open_store_database,
    verify_integrity,
)
from decision_memory.infrastructure.store import (
    new_generation_id,
    read_active,
    read_format,
    read_generation_json,
    store_paths,
    write_active,
    write_format,
    write_generation_json,
)

_EXPECTED_TABLES = {
    "index_metadata",
    "record_state",
    "record_snapshot",
    "record_tag",
    "field_source",
    "chunk",
    "chunk_source",
    "supersession_link",
    "metadata_evidence",
}


def test_format_active_and_generation_primitives(tmp_path) -> None:
    store = tmp_path / "query-index"
    write_format(store)
    assert read_format(store) == 2
    generation_id = new_generation_id()
    assert generation_id == generation_id.lower()
    assert len(generation_id) == 32
    write_active(store, generation_id)
    assert read_active(store) == generation_id
    metadata = write_generation_json(store, generation_id)
    assert metadata.generation_id == generation_id
    assert read_generation_json(store, generation_id) == metadata
    assert store_paths(store).format_file.name == "FORMAT"
    assert store_paths(store).active_file.name == "ACTIVE"
    assert store_paths(store).lock_database.name == "lock.sqlite3"
    assert (store / "generations" / generation_id / "records.sqlite3").parent.exists()


def test_active_write_is_atomic_replace(tmp_path) -> None:
    store = tmp_path / "query-index"
    write_format(store)
    first = new_generation_id()
    second = new_generation_id()
    write_active(store, first)
    write_active(store, second)
    assert read_active(store) == second
    # No temporary file survives an atomic rename.
    assert not store_paths(store).active_file.with_name("ACTIVE.tmp").exists()


def test_schema_creates_every_table_in_one_migration(tmp_path) -> None:
    connection = open_store_database(tmp_path / "records.sqlite3")
    create_schema(connection)
    tables = {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert tables >= _EXPECTED_TABLES
    assert verify_integrity(connection) == []
    with pytest.raises(StoreSchemaError):
        create_schema(connection)
    connection.close()


def test_lock_schema_has_one_guard_row(tmp_path) -> None:
    connection = open_lock_database(tmp_path / "lock.sqlite3")
    create_lock_schema(connection)
    row = connection.execute("SELECT id FROM lock_guard").fetchone()
    assert row == (1,)
    connection.close()
