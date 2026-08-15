"""Compare two built stores at chunk id, value path, ordinal, and text.

Reads through the shipped ``SqliteChromaIndexReader`` rather than off the
Chroma or SQLite files, so the comparison sees what retrieval sees. Called by
``store-build-determinism.sh`` after both builds land; usable on its own
against any two store directories.

Two keyings, and the pair is the point. By ``chunk_id`` is how the rest of the
system refers to a chunk, and it moves on every build because ``chunk_id``
hashes the generation id (``chunking.py`` ``chunk_id``). By the stable triple
``(record_id, value_path, ordinal)`` is what shows whether the content behind
those moving names is the same. A run reporting every id different and no
content different is the store being deterministic in content and not in
identity, which is a different finding from either half alone.

Usage: compare-stores.py BUILD_ROOT [--by-position]
       (expects BUILD_ROOT/a/index and BUILD_ROOT/b/index)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from decision_memory.infrastructure.index_reader import SqliteChromaIndexReader

Chunk = tuple[str, str, int, str]


def read(root: Path, build: str) -> dict[str, Chunk]:
    """Every active chunk by id, with record id, value path, ordinal, text.

    ``active_chunks`` sorts by ``chunk_id``, so the returned order cannot show
    an ordering difference. ``ordinal`` and ``value_path`` are the fields that
    would, and they are the ones retrieval and generation read.
    """
    reader = SqliteChromaIndexReader(root / build / "index")
    if reader.generation_id() is None:
        raise SystemExit(f"{build}: no active generation")
    return {
        chunk.chunk_id: (chunk.record_id, chunk.value_path, chunk.ordinal, chunk.text)
        for chunk in reader.active_chunks()
    }


def short(ids: list[str]) -> object:
    return [c[:16] for c in ids[:8]] or "none"


def by_position(root: Path) -> int:
    """Compare content under the stable triple, ignoring chunk id entirely."""

    def keyed(build: str) -> dict[tuple[str, str, int], tuple[str, str, str]]:
        reader = SqliteChromaIndexReader(root / build / "index")
        if reader.generation_id() is None:
            raise SystemExit(f"{build}: no active generation")
        return {
            (c.record_id, c.value_path, c.ordinal): (c.text, c.fingerprint, c.chunk_id)
            for c in reader.active_chunks()
        }

    a, b = keyed("a"), keyed("b")
    print("--- chunks by (record_id, value_path, ordinal) ---")
    print(f"key count: a={len(a)} b={len(b)} | same key set: {set(a) == set(b)}")
    shared = sorted(set(a) & set(b))
    text_differ = [k for k in shared if a[k][0] != b[k][0]]
    fp_differ = [k for k in shared if a[k][1] != b[k][1]]
    id_differ = [k for k in shared if a[k][2] != b[k][2]]
    print(f"shared keys:        {len(shared)}")
    print(f"text differs:       {len(text_differ)}")
    print(f"fingerprint differs:{len(fp_differ)}")
    print(f"chunk_id differs:   {len(id_differ)}")
    content_differs = bool(set(a) != set(b) or text_differ or fp_differ)
    if content_differs:
        verdict = "CONTENT DIFFERS: adapt or ingest is nondeterministic"
    elif id_differ:
        verdict = (
            "content identical, every chunk id moved: the store is "
            "deterministic in content and not in identity"
        )
    else:
        verdict = "identical in content and identity"
    print(f"verdict: {verdict}")
    return 1 if content_differs else 0


def main() -> int:
    root = Path(sys.argv[1])
    if "--by-position" in sys.argv[2:]:
        return by_position(root)
    a, b = read(root, "a"), read(root, "b")

    print("--- chunks ---")
    print(f"chunk count: a={len(a)} b={len(b)}")

    only_a = sorted(set(a) - set(b))
    only_b = sorted(set(b) - set(a))
    if only_a or only_b:
        print(f"chunk ids DIFFER: {len(only_a)} only in a, {len(only_b)} only in b")
        print(f"  only in a: {short(only_a)}")
        print(f"  only in b: {short(only_b)}")
    else:
        print("chunk ids: IDENTICAL")

    shared = sorted(set(a) & set(b))
    record_differ = [c for c in shared if a[c][0] != b[c][0]]
    path_differ = [c for c in shared if a[c][1] != b[c][1]]
    ordinal_differ = [c for c in shared if a[c][2] != b[c][2]]
    text_differ = [c for c in shared if a[c][3] != b[c][3]]

    print(f"record_id differs:  {short(record_differ)}")
    print(f"value_path differs: {short(path_differ)}")
    print(f"ordinal differs:    {short(ordinal_differ)}")
    print(f"text differs:       {short(text_differ)}")

    differs = bool(
        only_a
        or only_b
        or record_differ
        or path_differ
        or ordinal_differ
        or text_differ
    )
    print(f"verdict: {'STORES DIFFER' if differs else 'stores identical'}")

    (root / "chunks.json").write_text(
        json.dumps(
            {
                build: {c: v[:3] for c, v in data.items()}
                for build, data in (("a", a), ("b", b))
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    return 1 if differs else 0


if __name__ == "__main__":
    raise SystemExit(main())
