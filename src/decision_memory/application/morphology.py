"""Application: the one named morphology rule family (spec 0011 AC-7).

One rule set serves two callers that need different shapes. The **base set**
entry point serves the spec 0010 AC-11 verification guard, where a false match
loosens a safety check. The canonicalizing stemmer pinned as ``morphology-v1``
serves the BM25 corpus, where over stripping costs ranking and nothing else.
The two have deliberately different lossiness, which is why the family exposes
two entry points rather than one, and why only one implication holds between
them: a base set match implies equal canonical stems, never the converse.

The family is the five rules, naming the two tokens by length:

    longer equals shorter
    longer equals shorter plus ``s``, ``es``, ``ed``, or ``ing``
    longer equals shorter with its final ``e`` removed, plus ``ed`` or ``ing``
    longer equals shorter plus a repeat of shorter's own final character,
        plus ``ed`` or ``ing``
    longer equals shorter with its final ``y`` replaced by ``i``, plus ``es``
        or ``ed``

The four inflection rules require ``shorter`` to reach ``MIN_STEM_LENGTH``,
measured on the untransformed token. Exact equality carries no floor: it
transforms no suffix, so the floor guards nothing there.

This module is pure application code with no external imports. Any edit to the
family must be measured against the retrieval gate and the verification drop
rate together, since one rule set now moves both.

``morphology-v1`` itself is not here yet; it arrives with spec 0011 task 4,
which owns the tokenizer side of this move.
"""

from __future__ import annotations

from functools import cache

# The plain suffixes that make a longer token an inflection of a shorter one.
INFLECTION_SUFFIXES = ("s", "es", "ed", "ing")

# The floor a shorter token must reach before any inflection rule may match
# it, measured on the untransformed token (spec 0010 AC-11). In the base set
# direction the derived base is that untransformed token, so a base under the
# floor is never added to the set.
MIN_STEM_LENGTH = 3

# The two suffixes the three tail rules attach.
_TAIL_SUFFIXES = ("ed", "ing")


def _stem_match(a: str, b: str) -> bool:
    """True when one token is derivable from the other under the five rules.

    This is the **directional** relation: it derives ``longer`` from
    ``shorter`` and asks whether the two line up. It is deliberately kept
    after the AC-11 amendment moved the verification guard to ``base_set``,
    because the base set is the symmetric closure of exactly this relation,
    and the pair comparison instrument in ``docs/experiments/data/`` needs a
    shipped second side to measure against. An instrument carrying its own
    replica of the relation it measures is the shape that put wrong figures
    into spec 0003, and the cross check that caught a real disagreement on
    experiment 0010's first run.

    It is not the verification matcher. ``tokens_match`` calls
    ``base_sets_intersect``: this relation misses ``falls`` against
    ``falling``, because neither is derivable from the other and both come
    from ``fall``.
    """
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    if len(shorter) < MIN_STEM_LENGTH:
        return False
    if any(longer == shorter + suffix for suffix in INFLECTION_SUFFIXES):
        return True
    for suffix in _TAIL_SUFFIXES:
        if shorter.endswith("e") and longer == shorter[:-1] + suffix:
            return True
        if longer == shorter + shorter[-1] + suffix:
            return True
    return any(
        shorter.endswith("y") and longer == shorter[:-1] + "i" + suffix
        for suffix in ("es", "ed")
    )


@cache
def base_set(token: str) -> frozenset[str]:
    """Every ``shorter`` the five rules could have derived this token from.

    The token itself is always in the set, which is the exact equality rule.
    Then, for each of the four inflection rules whose suffix this token
    carries, the ``shorter`` that rule would have started from, provided that
    ``shorter`` reaches ``MIN_STEM_LENGTH``. A base under the floor is never
    added, so the floor means the same thing here as it does in
    ``_stem_match``.

    **No token is ever reduced to a lossy stem.** The set is derived by
    inverting rules already agreed rather than by stripping toward a canonical
    form, so a base only ever appears when one of the five rules puts it
    there. That is what separates this from the canonicalizing stemmer, whose
    tail rules converge unrelated words (``file`` and ``fill`` both reach
    ``fil``).

    Memoized per token: the additive half consults this inside a greedy walk
    over the parent pool, which would otherwise rebuild the same sets
    quadratically.
    """
    bases = {token}

    def _add(candidate: str) -> None:
        if len(candidate) >= MIN_STEM_LENGTH:
            bases.add(candidate)

    for suffix in INFLECTION_SUFFIXES:
        if token.endswith(suffix) and len(token) > len(suffix):
            _add(token[: -len(suffix)])
    for suffix in _TAIL_SUFFIXES:
        if not token.endswith(suffix) or len(token) <= len(suffix):
            continue
        trimmed = token[: -len(suffix)]
        # The final `e` rule, inverted: `using` came from `use`.
        _add(trimmed + "e")
        # The doubled final character rule, inverted: `shipped` came from
        # `ship`.
        if len(trimmed) >= 2 and trimmed[-1] == trimmed[-2]:
            _add(trimmed[:-1])
    # The final `y` to `i` rule, inverted: `relies` came from `rely`.
    for suffix in ("es", "ed"):
        if not token.endswith(suffix) or len(token) <= len(suffix):
            continue
        trimmed = token[: -len(suffix)]
        if trimmed.endswith("i"):
            _add(trimmed[:-1] + "y")
    return frozenset(bases)


def base_sets_intersect(a: str, b: str) -> bool:
    """Whether two tokens share a base, the AC-11 symmetric stem match.

    AC-11 has always read "two tokens match when they share a stem", and
    sharing a stem is symmetric. ``_stem_match`` implemented something
    directional, so two different inflections of one word never reached their
    common base: ``falls`` and ``falling`` both come from ``fall`` and neither
    is derivable from the other.

    This introduces **no new rule**. Every pair it matches is joined by a base
    one of the same five rules puts in both sets, which is why it accepts
    every pair ``_stem_match`` accepted (if ``longer`` is ``shorter`` plus a
    suffix, then ``shorter`` is in both sets) and adds no false match of its
    own. The measurement is in spec 0010's rationale, *The additive matcher*,
    and its instrument is
    ``docs/experiments/data/base-set-pair-comparison.py``.
    """
    return not base_set(a).isdisjoint(base_set(b))
