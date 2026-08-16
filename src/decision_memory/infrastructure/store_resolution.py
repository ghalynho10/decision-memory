"""Infrastructure: resolve a store's records manifest and corpus root (spec 0014).

A store records the absolute paths of the machine that built it. That works
until the store moves, and a shipped bundle moves by definition: it is built
here and read on a stranger's clone. Both stored fields are therefore written
empty in a shipped store (AC-6), and both are resolved at read time by the
same three step order.

Manifest path: the stored path when it names a real file, else the bundle's
``snapshot.json`` layout, else the convention ``<store>/../records/manifest.json``.
Corpus root: the stored hint when it names a real directory, else the
snapshot, else the convention ``<store>/../..`` (AC-1c), which is the real
corpus root for the default ``<root>/.decision-memory/query-index`` layout.

Resolution never turns a mismatch into a pass. It only says where to look; the
manifest found this way is digest compared exactly as one found by a stored
path is, so a store sitting beside a different corpus reads ``DRIFT`` and not
``CURRENT`` (AC-4).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from decision_memory.application.adapter import Manifest
from decision_memory.application.dto import ResolutionState
from decision_memory.infrastructure.bundle_snapshot import (
    MANIFEST_FILENAME,
    RECORDS_DIRNAME,
    snapshot_layout,
)
from decision_memory.infrastructure.manifest_reader import (
    load_manifest,
    raw_manifest_digest,
)
from decision_memory.infrastructure.source_resolver import resolve_source_path


def bundle_root(store_dir: Path) -> Path:
    """The directory holding both ``records/`` and the store directory."""
    return store_dir.parent


def resolve_manifest_path(store_dir: Path, stored: str | None) -> Path:
    """Where this store's records manifest lives, stored path first (AC-1).

    The convention path is returned as the last resort even when nothing is
    there, so the freshness trace shows the path that was tried rather than
    nothing at all. A manifest that does not load is classified ``UNKNOWN`` by
    the caller either way.
    """
    if stored:
        candidate = Path(stored)
        if candidate.is_file():
            return candidate
    root = bundle_root(store_dir)
    layout = snapshot_layout(root)
    if layout is not None:
        return layout.manifest_path
    return root / RECORDS_DIRNAME / MANIFEST_FILENAME


def resolve_corpus_root(store_dir: Path, stored_hint: str | None) -> Path:
    """The root this store's cited source paths are relative to (AC-1c)."""
    if stored_hint:
        candidate = Path(stored_hint)
        if candidate.is_dir():
            return candidate
    root = bundle_root(store_dir)
    layout = snapshot_layout(root)
    if layout is not None:
        return layout.corpus_root
    return root.parent


@dataclass(frozen=True)
class StoreResolution:
    """The manifest and source resolution callables one store needs.

    Built once at a composition root and handed to ``QueryDependencies``, so
    ``query`` and ``evaluate`` resolve a relocated or shipped store through
    exactly the same code and cannot drift back into two behaviours (AC-1a).
    """

    load_manifest: Callable[[], Manifest]
    raw_manifest_digest: Callable[[], str]
    resolve_source: Callable[[str], ResolutionState]


def store_resolution(
    read_metadata: Callable[[], tuple[str | None, str | None, str | None, str | None]],
) -> StoreResolution:
    """Build the shared resolution callables over a reader's metadata.

    ``read_metadata`` is the reader's own ``manifest_metadata``, which already
    returns resolved values, so the callables here read the resolved path
    rather than resolving a second time.
    """

    def _manifest_path() -> Path:
        stored = read_metadata()[0]
        if not stored:
            raise FileNotFoundError("no records manifest path resolved for this store")
        return Path(stored)

    def _load() -> Manifest:
        return load_manifest(_manifest_path())

    def _raw_digest() -> str:
        return raw_manifest_digest(_manifest_path())

    def _resolve(path: str) -> ResolutionState:
        return resolve_source_path(path, read_metadata()[3])

    return StoreResolution(
        load_manifest=_load,
        raw_manifest_digest=_raw_digest,
        resolve_source=_resolve,
    )
