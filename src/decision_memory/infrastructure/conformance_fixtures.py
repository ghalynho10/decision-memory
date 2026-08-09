"""Infrastructure: the fixture workspace port for the conformance suite.

Implements ``ConformanceFixturePort`` with the standard library: copying a
case corpus into an isolated temporary directory, applying the one closed
suite mutation, snapshotting the tree, and preserving or cleaning up failed
workspaces. Every operation returns a typed ``FixtureFailure`` instead of
raising, so the application engine can emit ``fixture.*`` checks and keep
later independent cases running (spec 0006 AC-14, AC-17, AC-18).
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path

from decision_memory.application.conformance import (
    ConformanceFixturePort,
    CorpusSnapshot,
    EntryKind,
    FixtureFailure,
    MutationKind,
    SnapshotEntry,
    Variant,
    Workspace,
)

# The closed suite constants (AC-8, AC-13).
INVALID_UTF8_BYTES = b"\xff\xfe\xfa"
FINGERPRINT_PROBE_BYTES = b"\nconformance fingerprint probe\n"


class WorkspaceFixture:
    """Copies, mutates, snapshots, preserves, and cleans up case corpora."""

    def __init__(self) -> None:
        self._base = Path(tempfile.mkdtemp(prefix="decision-memory-conformance-"))

    def open_case(self, case_id: str, corpus: Path) -> Workspace | FixtureFailure:
        root: Path | None = None
        try:
            parent = Path(tempfile.mkdtemp(prefix=f"{case_id}-", dir=self._base))
            root = parent / "corpus"
            shutil.copytree(corpus, root)
            return Workspace(
                root=root,
                variant=Variant.ORIGINAL,
                baseline=_snapshot(root),
            )
        except Exception as exc:  # noqa: BLE001 - fixture operation failure
            return _prepare_failure(exc, root)

    def open_variant(
        self,
        case_id: str,
        corpus: Path,
        target: Path,
        mutation: MutationKind,
    ) -> Workspace | FixtureFailure:
        root: Path | None = None
        try:
            parent = Path(tempfile.mkdtemp(prefix=f"{case_id}-", dir=self._base))
            root = parent / "corpus"
            shutil.copytree(corpus, root)
            _apply_mutation(root / target, mutation)
            return Workspace(
                root=root,
                variant=_variant_for(mutation),
                mutation_path=target,
                mutation_kind=mutation,
                baseline=_snapshot(root),
            )
        except Exception as exc:  # noqa: BLE001 - fixture operation failure
            return _prepare_failure(exc, root)

    def snapshot(self, root: Path) -> CorpusSnapshot | FixtureFailure:
        try:
            return _snapshot(root)
        except Exception as exc:  # noqa: BLE001 - fixture operation failure
            return FixtureFailure(
                "snapshot", type(exc).__name__, str(exc) or type(exc).__name__
            )

    def preserve(self, root: Path) -> Path | FixtureFailure:
        try:
            parent = Path(tempfile.mkdtemp(prefix="preserved-", dir=self._base))
            destination = parent / "artifact"
            shutil.copytree(root, destination)
            return destination
        except Exception as exc:  # noqa: BLE001 - fixture operation failure
            return FixtureFailure(
                "preserve",
                type(exc).__name__,
                str(exc) or type(exc).__name__,
                last_known_path=root if root.exists() else None,
            )

    def cleanup(self, workspace: Workspace) -> None | FixtureFailure:
        try:
            shutil.rmtree(workspace.root)
            return None
        except Exception as exc:  # noqa: BLE001 - fixture operation failure
            return FixtureFailure(
                "cleanup",
                type(exc).__name__,
                str(exc) or type(exc).__name__,
                last_known_path=workspace.root if workspace.root.exists() else None,
            )


def _prepare_failure(exc: Exception, root: Path | None) -> FixtureFailure:
    if root is not None and root.exists():
        return FixtureFailure(
            "prepare",
            type(exc).__name__,
            str(exc) or type(exc).__name__,
            last_known_path=root,
        )
    return FixtureFailure("prepare", type(exc).__name__, str(exc) or type(exc).__name__)


def _variant_for(mutation: MutationKind) -> Variant:
    if mutation == MutationKind.EMPTY:
        return Variant.EMPTY
    if mutation == MutationKind.INVALID_UTF8:
        return Variant.INVALID_UTF8
    return Variant.FINGERPRINT_PROBE


def _apply_mutation(path: Path, mutation: MutationKind) -> None:
    if mutation == MutationKind.EMPTY:
        path.write_bytes(b"")
    elif mutation == MutationKind.INVALID_UTF8:
        path.write_bytes(INVALID_UTF8_BYTES)
    else:
        with path.open("ab") as handle:
            handle.write(FINGERPRINT_PROBE_BYTES)


def _snapshot(root: Path) -> CorpusSnapshot:
    """A full ordered snapshot of one copied corpus (AC-14)."""
    entries: list[SnapshotEntry] = []
    for current, dirs, files in os.walk(root):
        directory = Path(current)
        for name in sorted(dirs):
            entry_path = directory / name
            entries.append(
                SnapshotEntry(
                    path=entry_path.relative_to(root),
                    kind=EntryKind.DIRECTORY,
                    permissions=stat.S_IMODE(entry_path.stat().st_mode),
                    content=None,
                )
            )
        for name in sorted(files):
            entry_path = directory / name
            entries.append(
                SnapshotEntry(
                    path=entry_path.relative_to(root),
                    kind=EntryKind.FILE,
                    permissions=stat.S_IMODE(entry_path.stat().st_mode),
                    content=entry_path.read_bytes(),
                )
            )
    entries.sort(key=lambda entry: entry.path.as_posix())
    return CorpusSnapshot(entries=tuple(entries))


def conformance_fixture_port() -> ConformanceFixturePort:
    """A fresh concrete fixture port for the CLI composition root."""
    return WorkspaceFixture()
