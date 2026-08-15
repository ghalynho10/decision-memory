"""Compare what two independently built stores put in front of the model.

``compare-stores.py`` answers whether two builds hold the same content.
This answers the question one level down, and it is the one that reaches the
answer: given the same question, do two builds of one corpus accept the same
chunks into the generation context?

Retrieval breaks ties on ``chunk_id`` (spec 0012), and a chunk id is fresh on
every build because it hashes the generation id, so before that spec lands two
builds can rank tied candidates differently and hand the model a different
evidence set. This script measures that directly.

**The keying is the point, and it is the lesson of experiment 0015.** The
accepted chunks come back as chunk ids, which share nothing across builds by
construction, so comparing them as ids reports total disagreement whether or
not anything real moved. Every accepted id is therefore translated through the
shipped reader into the stable key ``(record_id, fingerprint, value_path,
ordinal)`` before anything is compared. Read the ids alone and this comparison
inverts its own answer.

Order is compared as well as membership. The accepted list comes back in final
rank order, and that order is what the generation context is built from, so two
builds accepting the same eight chunks in a different order have still been
handed different inputs.

Drives the shipped ``query`` command and the shipped ``SqliteChromaIndexReader``.
No pipeline stage is re implemented here, because a hand written replica of the
pipeline is what put wrong figures into spec 0003.

Requires OPENAI_API_KEY: every question costs one real query per build.

Usage: compare-retrieval.py BUILD_ROOT
       (expects BUILD_ROOT/a/index and BUILD_ROOT/b/index)
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from decision_memory.application.evaluation import (
    QUERY_FIVE,
    QUERY_FOUR,
    QUERY_ONE,
)
from decision_memory.infrastructure.index_reader import SqliteChromaIndexReader

# A small fixed question set (spec 0012 AC-7), taken from the shipped battery
# rather than written here, so it cannot drift from the fixtures. One query
# expected to answer and two expected to abstain, because the accepted set is
# built before either outcome is decided and both paths should be compared.
QUESTIONS: tuple[tuple[str, str], ...] = (
    ("query-1", QUERY_ONE),
    ("query-4", QUERY_FOUR),
    ("query-5", QUERY_FIVE),
)

StableKey = tuple[str, str, str, int]


def stable_keys(store: Path) -> dict[str, StableKey]:
    """Every chunk id in this store mapped to its build stable key.

    Read through the shipped reader, so the mapping sees what retrieval sees.
    """
    reader = SqliteChromaIndexReader(store)
    if reader.generation_id() is None:
        raise SystemExit(f"{store}: no active generation")
    return {
        chunk.chunk_id: (
            chunk.record_id,
            chunk.fingerprint,
            chunk.value_path,
            chunk.ordinal,
        )
        for chunk in reader.active_chunks()
    }


def accepted_chunk_ids(store: Path, question: str) -> list[str]:
    """The accepted chunk ids, in final rank order, from one real query.

    Runs the shipped CLI and reads the ``accepted:`` line of its debug trace.
    A query that abstains or fails at generation still ran retrieval, so the
    line is present; only a retrieval failure has none, and that is reported
    rather than silently read as an empty accepted set.
    """
    result = subprocess.run(
        [
            "uv",
            "run",
            "--env-file",
            ".env",
            "decision-memory",
            "query",
            question,
            "--store",
            str(store),
            "--debug",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    for line in result.stdout.splitlines():
        if line.startswith("  accepted: "):
            value = line[len("  accepted: ") :].strip()
            return [chunk_id for chunk_id in value.split(",") if chunk_id]
    raise SystemExit(
        f"no accepted line for {question!r} against {store} "
        f"(exit {result.returncode}); retrieval did not complete:\n"
        f"{result.stdout[-800:]}"
    )


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    root = Path(sys.argv[1])
    keys = {build: stable_keys(root / build / "index") for build in ("a", "b")}

    print("--- retrieval: accepted chunks per build ---")
    print(
        "keyed by (record_id, fingerprint, value_path, ordinal); chunk ids are "
        "not comparable across builds and are never compared here"
    )
    agree_set = agree_order = 0
    for name, question in QUESTIONS:
        accepted = {
            build: [
                keys[build][chunk_id]
                for chunk_id in accepted_chunk_ids(root / build / "index", question)
            ]
            for build in ("a", "b")
        }
        same_order = accepted["a"] == accepted["b"]
        same_set = set(accepted["a"]) == set(accepted["b"])
        agree_set += same_set
        agree_order += same_order
        only_a = [key for key in accepted["a"] if key not in set(accepted["b"])]
        only_b = [key for key in accepted["b"] if key not in set(accepted["a"])]
        print(
            f"{name}: a={len(accepted['a'])} b={len(accepted['b'])} "
            f"same set: {same_set} | same order: {same_order}"
        )
        for key in only_a:
            print(f"    only in a: {key[0]} {key[2]} ordinal {key[3]}")
        for key in only_b:
            print(f"    only in b: {key[0]} {key[2]} ordinal {key[3]}")
        if same_set and not same_order:
            for rank, (left, right) in enumerate(
                zip(accepted["a"], accepted["b"], strict=True), start=1
            ):
                if left != right:
                    print(
                        f"    rank {rank}: a={left[0]} {left[2]} "
                        f"vs b={right[0]} {right[2]}"
                    )
    total = len(QUESTIONS)
    print(
        f"verdict: same accepted set {agree_set}/{total}, "
        f"same accepted order {agree_order}/{total}"
    )


if __name__ == "__main__":
    main()
