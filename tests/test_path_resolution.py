"""Directory listing cache for case sensitive path resolution.

Resolving many mentions against a corpus root re-probes the same handful of
directories over and over (see the jsmastery adapter's code path extraction,
which can check thousands of tokens against a small tree).
`path_resolves_case_sensitive` accepts a shared cache so repeated lookups
against one directory cost one `os.listdir` call, not one per token.
"""

from __future__ import annotations

import os
from pathlib import Path

from decision_memory.infrastructure.path_resolution import (
    path_resolves_case_sensitive,
)


def test_shared_cache_avoids_repeated_listdir_on_same_directory(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("", encoding="utf-8")

    calls = 0
    real_listdir = os.listdir

    def counting_listdir(path: object) -> list[str]:
        nonlocal calls
        calls += 1
        return real_listdir(path)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "listdir", counting_listdir)

    cache: dict[Path, frozenset[str]] = {}
    for _ in range(50):
        assert path_resolves_case_sensitive(tmp_path, "src/app.py", cache)

    assert calls == 2  # one listdir for tmp_path, one for tmp_path/"src", ever


def test_without_a_cache_each_call_lists_again(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("", encoding="utf-8")

    calls = 0
    real_listdir = os.listdir

    def counting_listdir(path: object) -> list[str]:
        nonlocal calls
        calls += 1
        return real_listdir(path)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "listdir", counting_listdir)

    for _ in range(5):
        assert path_resolves_case_sensitive(tmp_path, "src/app.py")

    # Without a cache each call re lists the directories, so the count is a
    # control against the cached test above (which lists once), not a fixed
    # implementation detail; assert it is clearly above the cached count.
    assert calls > 2


def test_missing_directory_listing_is_attempted_once_when_cached(
    tmp_path: Path, monkeypatch
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("", encoding="utf-8")

    calls = 0
    real_listdir = os.listdir

    def counting_listdir(path: object) -> list[str]:
        nonlocal calls
        calls += 1
        return real_listdir(path)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "listdir", counting_listdir)

    cache: dict[Path, frozenset[str]] = {}
    for _ in range(10):
        # resolving into a file as a directory fails; the failed listing must
        # be cached so it is not re attempted on every call.
        assert not path_resolves_case_sensitive(tmp_path, "src/app.py/x", cache)
    assert calls < 10  # a handful, not once per call


def test_cache_still_reports_case_mismatch_and_missing_entries(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "App.py").write_text("", encoding="utf-8")

    cache: dict[Path, frozenset[str]] = {}
    assert not path_resolves_case_sensitive(tmp_path, "src/app.py", cache)
    assert not path_resolves_case_sensitive(tmp_path, "src/missing.py", cache)
    assert path_resolves_case_sensitive(tmp_path, "src/App.py", cache)
