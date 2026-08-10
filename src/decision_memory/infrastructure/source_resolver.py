"""Infrastructure: source path resolution against the stored root hint (AC-19).

``resolve_source_path`` turns a stored relative POSIX path plus the absolute
``source_root_hint`` into a ``ResolutionState``. It first rejects a malformed
relative path, then reports ``hint_unavailable`` when no usable root exists.
With a root it verifies lexical and resolved containment, rejects a symlink
escape, and checks exact entry case at every segment. An existing regular file
is ``resolved``; a directory or an absent entry is ``missing``. Resolution is
informative only and never changes query state.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

from decision_memory.application.dto import ResolutionState


def _is_valid_relative(path: str) -> bool:
    """True for a normalized relative POSIX path with no escape segments."""
    if not path:
        return False
    if path.startswith("/") or path.endswith("/"):
        return False
    segments = path.split("/")
    return not (".." in segments or "" in segments)


def _matches_case_exactly(root: Path, relative_path: str) -> bool:
    """True when every segment exists under the root with exact entry case."""
    current = root
    for part in PurePosixPath(relative_path).parts:
        try:
            if not current.is_dir():
                return False
            names = {entry.name for entry in current.iterdir()}
        except OSError:
            return False
        if part not in names:
            return False
        current = current / part
    return True


def resolve_source_path(relative_path: str, hint: str | None) -> ResolutionState:
    """Classify a stored relative source path against the root hint."""
    if not _is_valid_relative(relative_path):
        return ResolutionState.INVALID_RELATIVE_PATH
    if not hint:
        return ResolutionState.HINT_UNAVAILABLE
    root = Path(hint)
    try:
        resolved_root = root.resolve()
    except OSError:
        return ResolutionState.MISSING
    if not _matches_case_exactly(root, relative_path):
        return ResolutionState.MISSING
    candidate = root / relative_path
    try:
        resolved = candidate.resolve()
    except OSError:
        return ResolutionState.MISSING
    try:
        contained = resolved.is_relative_to(resolved_root)
    except ValueError:
        contained = False
    if not contained:
        return ResolutionState.MISSING
    try:
        return (
            ResolutionState.RESOLVED if candidate.is_file() else ResolutionState.MISSING
        )
    except OSError:
        return ResolutionState.MISSING
