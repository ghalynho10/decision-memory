"""Infrastructure: the shared and exclusive SQLite lock protocol (AC-9).

The lock database lives at the store root, is never rebuilt, uses
``journal_mode=DELETE``, ``foreign_keys=ON``, and ``busy_timeout=0``, and has
one ``lock_guard`` row. Query runs ``BEGIN`` then selects that row to hold a
shared lock for the full query; ingest runs ``BEGIN EXCLUSIVE`` then selects
it and holds the transaction for the full run. With a zero busy timeout a
conflict returns immediately rather than waiting.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from decision_memory.infrastructure.sqlite_store import (
    create_lock_schema,
    open_lock_database,
)
from decision_memory.infrastructure.store import LOCK_DATABASE


class LockError(Exception):
    """A lock conflict, a missing lock database, or a missing guard row."""


@contextmanager
def store_lock(store_dir: Path, *, exclusive: bool) -> Iterator[None]:
    """Hold a shared or exclusive lock on the store for the whole block.

    The lock database is bootstrapped on first use (a store that does not
    exist yet, typically the very first ingest); afterwards it is never
    rebuilt, so a missing file never silently resets a real lock. Opening a
    connection runs the fixed pragmas, which themselves need exclusive access
    while another holder is mid transaction, so any operational error during
    acquisition maps to a ``LockError`` conflict.
    """
    path = store_dir / LOCK_DATABASE
    if not path.is_file():
        store_dir.mkdir(parents=True, exist_ok=True)
        try:
            connection = open_lock_database(path)
            try:
                create_lock_schema(connection)
            finally:
                connection.close()
        except sqlite3.OperationalError:
            raise LockError("lock conflict") from None
    try:
        connection = open_lock_database(path)
    except sqlite3.OperationalError:
        raise LockError("lock conflict") from None
    try:
        connection.execute("BEGIN EXCLUSIVE" if exclusive else "BEGIN")
        row = connection.execute("SELECT id FROM lock_guard WHERE id = 1").fetchone()
        if row is None:
            raise LockError("lock_guard row is missing")
    except sqlite3.OperationalError:
        raise LockError("lock conflict") from None
    try:
        yield
    finally:
        try:
            connection.execute("COMMIT")
        except sqlite3.OperationalError:
            connection.rollback()
        connection.close()
