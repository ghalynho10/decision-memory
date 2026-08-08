"""Case sensitive path resolution shared by the adapter and validation.

Spec 0003 requires evidence resolution to check each cited target directly
instead of scanning the project root (AC-22), and to respect case exactly even
on a case insensitive filesystem such as macOS (AC-5). Resolution walks the
path components and requires each entry name to appear exactly, character for
character, in its parent directory's listing. Both the jsmastery adapter and
the application validation path call this so they cannot drift apart.
"""

from __future__ import annotations

import os
from pathlib import Path

from decision_memory.domain.records import CanonicalDecisionRecord, EvidenceKind
from decision_memory.domain.validation import normalize_target


def path_resolves_case_sensitive(root: Path, relative_posix: str) -> bool:
    """Whether ``relative_posix`` names a real entry under ``root``, case exact.

    Each component must appear exactly in its parent directory's listing, so a
    target whose casing differs from the entry on disk does not resolve, even
    on a case insensitive filesystem. Files and directories both resolve.
    """
    current = root
    for part in relative_posix.split("/"):
        if part in ("", "."):
            continue
        try:
            entries = set(os.listdir(current))
        except OSError:
            return False
        if part not in entries:
            return False
        current = current / part
    return True


def resolve_cited_paths(record: CanonicalDecisionRecord, root: Path) -> frozenset[str]:
    """The normalized cited targets that resolve under ``root``.

    Only file and spec evidence is checked; commit evidence resolves through
    git history instead. A target that is not normalized is left out here, and
    the validator rejects it with its own `evidence.target_not_normalized`
    rule rather than silently scanning.
    """
    if not record.evidence:
        return frozenset()
    paths: set[str] = set()
    for evidence in record.evidence:
        if evidence.kind not in (EvidenceKind.FILE, EvidenceKind.SPEC):
            continue
        if evidence.target is None:
            continue
        normalized = normalize_target(evidence.target)
        if path_resolves_case_sensitive(root, normalized):
            paths.add(normalized)
    return frozenset(paths)
