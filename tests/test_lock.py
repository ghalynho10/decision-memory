"""Store lock protocol tests (spec 0007 AC-9).

The lock database is bootstrapped on first use; an exclusive lock blocks both
shared and exclusive holders, while two shared holders coexist. All conflict
paths surface as ``LockError`` rather than a raw SQLite busy error.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from decision_memory.infrastructure.index_lock import LockError, store_lock


def test_shared_locks_coexist(tmp_path: Path) -> None:
    store = tmp_path / "store"
    with store_lock(store, exclusive=False), store_lock(store, exclusive=False):
        pass


def test_exclusive_blocks_shared(tmp_path: Path) -> None:
    store = tmp_path / "store"
    with store_lock(store, exclusive=True), pytest.raises(LockError):  # noqa: SIM117 - the raises wraps the inner acquisition
        with store_lock(store, exclusive=False):
            pass


def test_exclusive_blocks_exclusive(tmp_path: Path) -> None:
    store = tmp_path / "store"
    with store_lock(store, exclusive=True), pytest.raises(LockError):  # noqa: SIM117 - the raises wraps the inner acquisition
        with store_lock(store, exclusive=True):
            pass


def test_shared_blocks_exclusive(tmp_path: Path) -> None:
    store = tmp_path / "store"
    with store_lock(store, exclusive=False), pytest.raises(LockError):  # noqa: SIM117 - the raises wraps the inner acquisition
        with store_lock(store, exclusive=True):
            pass


def test_lock_bootstraps_the_lock_database(tmp_path: Path) -> None:
    store = tmp_path / "store"
    assert not store.exists()
    with store_lock(store, exclusive=False):
        pass
    assert (store / "lock.sqlite3").is_file()


def test_lock_is_released_after_block(tmp_path: Path) -> None:
    store = tmp_path / "store"
    with store_lock(store, exclusive=True):
        pass
    with store_lock(store, exclusive=True):
        pass
