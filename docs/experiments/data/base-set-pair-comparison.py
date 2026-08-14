"""Compare three matchers over this repository's own vocabulary (spec 0010 OD-8).

Spec 0010 AC-11 was amended on 2026-08-14 to replace the directional stem
comparison with a base set intersection, and the safety argument for that
amendment is a measurement: the base set fixes 622 pairs, loses 0 the shipped
matcher already accepts, and invents 0 false matches, while ``morphology-v1``
fixes 650 but loses 30 and invents 28. Those figures decide the amendment,
because the additive half is the guard standing behind AC-2, the only criterion
in this chain currently green on live evidence.

This script exists so those numbers are **reproducible rather than quoted**. It
records the vocabulary it measured over, its token count, and the pair count
beside every figure, so a later reader can re derive all five and disagree.

It calls the shipped entry points for two of the three matchers:
``_stem_match`` for the directional relation and ``base_sets_intersect`` for
the amended one. Neither is replicated here. That is why ``_stem_match`` is
kept in ``application/morphology.py`` after the guard stopped calling it: an
instrument carrying its own replica of the relation it measures is the shape
that put wrong figures into spec 0003, and the cross check that caught a real
disagreement on experiment 0010's first run.

``morphology-v1`` is the exception, and it is the honest one. It is the
**rejected** candidate and it is not shipped: it arrives with spec 0011 task 4,
which owns the tokenizer side of this move. So it is written here, exactly to
the algorithm pinned in spec 0011's *The canonicalizing stemmer*, and it is
cross checked against that section's normative table before any figure is
reported. A disagreement is reported as a script bug rather than as a finding.
When spec 0011 ships the real entry point, this replica should be deleted and
the import swapped in.

Usage, from the repository root (no provider call, no network):

    uv run python docs/experiments/data/base-set-pair-comparison.py
"""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from pathlib import Path

from decision_memory.application.morphology import (
    MIN_STEM_LENGTH,
    _stem_match,
    base_set,
    base_sets_intersect,
)
from decision_memory.application.verification import FUNCTION_WORDS, sentence_tokens

# The vocabulary rule, pinned here because every figure below is relative to
# it: all lowercase alphabetic tokens appearing at least this many times across
# `docs/**/*.md`, with the AC-11 function word set removed. The corpus is this
# project's own prose, chosen because it is the closest available proxy for the
# token stream the matcher actually sees and because it needs no provider call.
# It is not the JobPilot corpus, which is the main limit on these numbers.
MIN_OCCURRENCES = 3
DOCS_GLOB = "docs/**/*.md"


# ---------------------------------------------------------------------------
# The rejected candidate: `morphology-v1` exactly as spec 0011 pins it. Not
# shipped, so it is written here and cross checked against the pinned table.
# ---------------------------------------------------------------------------

# The entry floor is measured once on the untransformed input token and is the
# same `MIN_STEM_LENGTH` the base set matcher applies to a derived base. The
# round floor is measured on each intermediate result inside a round. They are
# different values serving different steps and must not be harmonized.
ROUND_FLOOR = 2

_STRIP_SUFFIXES = ("ing", "ed", "es", "s")


def _one_round(token: str) -> str:
    """One round of steps 2 to 6, at most one strip and at most one tail rule."""
    result = token
    for suffix in _STRIP_SUFFIXES:
        if result.endswith(suffix) and len(result) - len(suffix) >= ROUND_FLOOR:
            result = result[: -len(suffix)]
            break
    # Steps 3, 4, and 5 are mutually exclusive and apply at most one each.
    if len(result) >= 2 and result[-1] == result[-2]:
        if len(result) - 1 >= ROUND_FLOOR:
            result = result[:-1]
    elif result.endswith("i"):
        result = result[:-1] + "y"
    elif result.endswith("e") and len(result) - 1 >= ROUND_FLOOR:
        result = result[:-1]
    return result


def canonical_stem(token: str) -> str:
    """`morphology-v1`: strip and rewrite until a round changes nothing.

    Termination is bounded by the rules rather than by an iteration cap: every
    round either strictly shortens the token or halts the loop, and the round
    floor bounds the descent. A cap would make this a different algorithm from
    the one pinned.
    """
    if len(token) < MIN_STEM_LENGTH:
        return token
    current = token
    while True:
        nxt = _one_round(current)
        if nxt == current:
            return current
        current = nxt


def canonical_stem_single_round(token: str) -> str:
    """`morphology-v1` as it stood **before** the 2026-08-14 step 7 amendment.

    Kept because spec 0010's rationale table was measured against this form,
    hours before spec 0011 replaced "there is no second pass" with the repeat
    until stable loop. Without it the recorded 30 and 28 look like arithmetic
    errors rather than what they are: correct figures for the algorithm as it
    was pinned at the time of measurement. Both readings are reported so the
    table can be re derived and the amendment's real effect can be seen.
    """
    if len(token) < MIN_STEM_LENGTH:
        return token
    return _one_round(token)


# The normative table from spec 0011, *The canonicalizing stemmer*. The Rounds
# column of that table is deliberately not asserted: it is inconsistent between
# `chose` (2) and `process` (3) for traces of the same shape, so only the stems
# are treated as normative here. That inconsistency belongs to spec 0011.
_NORMATIVE = {
    "decide": "decid",
    "decides": "decid",
    "decided": "decid",
    "deciding": "decid",
    "decision": "decision",
    "use": "us",
    "using": "us",
    "ship": "ship",
    "shipped": "ship",
    "rely": "rely",
    "relies": "rely",
    "records": "record",
    "chose": "cho",
    "chosen": "chosen",
    "retrieve": "retriev",
    "retrieval": "retrieval",
    "process": "proc",
    "setting": "set",
    "settings": "set",
    "need": "ne",
    "needs": "ne",
    "falls": "fal",
    "falling": "fal",
    "sing": "sing",
    "singing": "sing",
}


def cross_check_the_replica() -> list[str]:
    """Where the replica disagrees with spec 0011's pinned table."""
    return [
        f"{token}: pinned {expected!r}, replica {canonical_stem(token)!r}"
        for token, expected in _NORMATIVE.items()
        if canonical_stem(token) != expected
    ]


# ---------------------------------------------------------------------------
# The vocabulary.
# ---------------------------------------------------------------------------


def build_vocabulary(root: Path) -> tuple[list[str], int, int]:
    """The measured vocabulary, the files read, and the running token total."""
    counts: Counter[str] = Counter()
    files = 0
    total = 0
    for path in sorted(root.glob(DOCS_GLOB)):
        if not path.is_file():
            continue
        files += 1
        for token in sentence_tokens(path.read_text(encoding="utf-8")):
            total += 1
            if token.isalpha() and token.isascii():
                counts[token] += 1
    vocabulary = sorted(
        token
        for token, count in counts.items()
        if count >= MIN_OCCURRENCES and token not in FUNCTION_WORDS
    )
    return vocabulary, files, total


# ---------------------------------------------------------------------------
# The comparison.
# ---------------------------------------------------------------------------


def rule_justified(a: str, b: str) -> bool:
    """Whether the five rules join this pair through a common base.

    A pair is justified when some token sits in both base sets and the five
    rules derive each side from it. This is what "invents no false match"
    means: a matcher that joins a pair no common base reaches is joining two
    different words. It is also a real check on the base set entry point
    rather than a restatement of it, since a base set built by a looser
    inversion than the rules allow would fail it here.
    """
    shared = base_set(a) & base_set(b)
    return any(_stem_match(base, a) and _stem_match(base, b) for base in shared)


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    disagreements = cross_check_the_replica()
    if disagreements:
        print("SCRIPT BUG: the morphology-v1 replica disagrees with spec 0011:")
        for line in disagreements:
            print(f"  {line}")
        print("Every figure below would be measured against the wrong algorithm.")
        return 1
    print(
        f"morphology-v1 replica agrees with all {len(_NORMATIVE)} pinned stems "
        "in spec 0011's normative table"
    )

    vocabulary, files, total = build_vocabulary(root)
    pairs = len(vocabulary) * (len(vocabulary) - 1) // 2
    print()
    print("Vocabulary")
    print(f"  rule            lowercase alphabetic tokens from {DOCS_GLOB},")
    print(f"                  appearing at least {MIN_OCCURRENCES} times,")
    print("                  with the AC-11 function word set removed")
    print(f"  files read      {files}")
    print(f"  tokens scanned  {total}")
    print(f"  vocabulary      {len(vocabulary)} distinct content tokens")
    print(f"  unordered pairs {pairs}")

    shipped: set[tuple[str, str]] = set()
    base: set[tuple[str, str]] = set()
    looped: set[tuple[str, str]] = set()
    single: set[tuple[str, str]] = set()
    loop_stems = {token: canonical_stem(token) for token in vocabulary}
    round_stems = {token: canonical_stem_single_round(token) for token in vocabulary}
    for a, b in combinations(vocabulary, 2):
        if _stem_match(a, b):
            shipped.add((a, b))
        if base_sets_intersect(a, b):
            base.add((a, b))
        if loop_stems[a] == loop_stems[b]:
            looped.add((a, b))
        if round_stems[a] == round_stems[b]:
            single.add((a, b))

    candidates = (
        ("base set intersection", base),
        ("morphology-v1, as pinned now", looped),
        ("morphology-v1, single round", single),
    )

    print()
    print(f"Matched pairs, out of {pairs}")
    print(f"  {'_stem_match as shipped':28} {len(shipped)}")
    for name, matched in candidates:
        print(f"  {name:28} {len(matched)}")

    print()
    print(f"  {'':28} {'fixes':>7} {'loses':>7} {'invents':>8}")
    for name, matched in candidates:
        invents = {pair for pair in matched if not rule_justified(*pair)}
        print(
            f"  {name:28} {len(matched - shipped):>7} "
            f"{len(shipped - matched):>7} {len(invents):>8}"
        )

    print()
    print("Samples, so the categories can be read rather than trusted")
    for name, matched in candidates:
        print(f"  {name}")
        for label, subset in (
            ("fixes  ", matched - shipped),
            ("loses  ", shipped - matched),
            ("invents", {p for p in matched if not rule_justified(*p)}),
        ):
            sample = ", ".join(f"{a}/{b}" for a, b in sorted(subset)[:6])
            print(f"    {label} {len(subset):>4}  {sample or '(none)'}")

    print()
    print("Construction properties, checked rather than assumed")
    print(f"  every shipped pair survives the base set:  {shipped <= base}")
    print(
        "  every base set pair is joined by a common base the five rules reach:  "
        f"{all(rule_justified(*pair) for pair in base)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
