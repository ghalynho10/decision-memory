"""The shared morphology rule family (spec 0010 AC-11, spec 0011 AC-7).

These lock the base set entry point the AC-11 verification guard now uses, and
the directional relation it is the symmetric closure of. The family is one rule
set with two shapes, so a change here moves both the additive half and the
completeness half of the validity test, and the completeness half is the safety
critical direction.

The measurement behind the amendment is
``docs/experiments/data/base-set-pair-comparison.py``; these tests lock the
rules, not the corpus figures.
"""

from __future__ import annotations

import pytest

from decision_memory.application.morphology import (
    MIN_STEM_LENGTH,
    _stem_match,
    base_set,
    base_sets_intersect,
)
from decision_memory.application.verification import FUNCTION_WORDS, tokens_match

# The five rules, each as a (shorter, longer) pair the rule joins. The base set
# must reach every one of these **from both sides**, which is the whole content
# of the amendment: the directional relation already accepted each pair when
# asked in the shorter to longer direction.
_RULE_PAIRS = [
    ("record", "records"),  # plain plural, the `s` suffix
    ("box", "boxes"),  # the `es` suffix
    ("accept", "accepted"),  # the `ed` suffix
    ("accept", "accepting"),  # the `ing` suffix
    ("use", "used"),  # final `e` removed, plus `ed`
    ("use", "using"),  # final `e` removed, plus `ing`
    ("ship", "shipped"),  # final character repeated, plus `ed`
    ("ship", "shipping"),  # final character repeated, plus `ing`
    ("rely", "relies"),  # final `y` to `i`, plus `es`
    ("rely", "relied"),  # final `y` to `i`, plus `ed`
]


@pytest.mark.parametrize(("shorter", "longer"), _RULE_PAIRS)
def test_every_rule_is_reached_from_both_sides(shorter: str, longer: str) -> None:
    """Each of the five rules joins its pair whichever way round it is asked.

    ``base_set`` inverts the rules, so the derived base has to land in the
    longer token's set for the intersection to find it (AC-11).
    """
    assert base_sets_intersect(shorter, longer)
    assert base_sets_intersect(longer, shorter)
    assert shorter in base_set(longer)
    assert shorter in base_set(shorter)


def test_two_inflections_of_one_word_now_match() -> None:
    """The experiment 0010 case: ``falls`` against the parent's ``falling``.

    Neither is derivable from the other, so the directional relation missed
    them; both come from ``fall``, so the base sets intersect there. This is
    the defect class the amendment exists to close, and it generalises, since
    turning a subordinate clause into a standalone sub claim is exactly what
    converts a participle into a finite verb.
    """
    assert not _stem_match("falls", "falling")
    assert base_sets_intersect("falls", "falling")
    assert "fall" in base_set("falls")
    assert "fall" in base_set("falling")
    # The same shape, on the two pairs AC-11 names beside it.
    assert base_sets_intersect("drops", "dropped")
    assert base_sets_intersect("decides", "deciding")


def test_the_base_set_accepts_every_pair_the_directional_relation_did() -> None:
    """No pair is lost, and this is true by construction rather than measured.

    If ``longer`` is ``shorter`` plus a suffix under one of the five rules,
    then ``shorter`` is in both base sets. The loosening is therefore strictly
    one directional, which is what lets the 0 lost column be a property rather
    than a corpus reading.
    """
    for shorter, longer in _RULE_PAIRS:
        assert _stem_match(shorter, longer)
        assert base_sets_intersect(shorter, longer)


def test_the_base_set_adds_no_pair_the_five_rules_reject_both_ways() -> None:
    """Every base set match is joined by a base the five rules actually reach.

    This is what "invents no false match" means, and it is a real check on the
    inversion rather than a restatement of it: a base set built by a looser
    inversion than the rules allow would put a base in the set that
    ``_stem_match`` cannot derive the token from, and this would catch it.
    """
    vocabulary = [
        "falls",
        "falling",
        "fall",
        "file",
        "fill",
        "site",
        "sits",
        "role",
        "rolling",
        "bar",
        "bare",
        "decide",
        "decision",
        "setting",
        "settings",
        "need",
        "needs",
        "process",
        "chose",
        "chosen",
    ]
    for first in vocabulary:
        for second in vocabulary:
            if not base_sets_intersect(first, second):
                continue
            shared = base_set(first) & base_set(second)
            assert any(
                _stem_match(base, first) and _stem_match(base, second)
                for base in shared
            ), f"{first}/{second} joined by no base the five rules reach"


def test_the_stemmer_false_matches_are_not_inherited() -> None:
    """The pairs ``morphology-v1`` invents stay unmatched here (OD-8).

    These are the reason the canonicalizing stemmer was rejected for
    verification: its tail rules converge two different words, and each false
    match is a substitution the additive guard would begin to accept.
    """
    for first, second in (
        ("file", "fill"),
        ("site", "sits"),
        ("role", "rolling"),
        ("bar", "bare"),
    ):
        assert not base_sets_intersect(first, second)
        assert not tokens_match(first, second)


def test_the_three_character_floor_refuses_a_base_below_it() -> None:
    """A derived base under ``MIN_STEM_LENGTH`` never enters the set (AC-11).

    ``sing`` would reach ``s`` by stripping ``ing``, which is the degenerate
    collapse the floor exists to refuse, so ``sing`` and ``sang`` stay apart
    while ``sing`` and ``sings`` still meet at ``sing`` itself.
    """
    assert MIN_STEM_LENGTH == 3
    assert "s" not in base_set("sing")
    assert not base_sets_intersect("sing", "sat")
    # The floor bites on the derived base, not on the token: `sing` is still
    # reachable from `sings` and `singing`, since that base clears the floor.
    assert base_sets_intersect("sing", "sings")
    assert base_sets_intersect("sing", "singing")


def test_exact_equality_carries_no_floor() -> None:
    """A token reused verbatim matches itself however short it is (AC-11).

    Equality transforms no suffix, so the floor guards nothing there, and a
    token already present in the parent is not new vocabulary.
    """
    assert tokens_match("db", "db")
    assert base_sets_intersect("db", "db")
    # And a two character token still derives no base, so it matches nothing
    # else.
    assert base_set("db") == frozenset({"db"})


def test_the_function_word_short_circuit_survives() -> None:
    """A function word matches only by exact equality, never through a base.

    The short circuit sits ahead of the stem test in ``tokens_match``, so the
    base set is never consulted for a function word even where the two sets
    would intersect.
    """
    assert "no" in FUNCTION_WORDS
    assert "not" in FUNCTION_WORDS
    assert tokens_match("not", "not")
    # `is` and `it` are both function words: no base set path may join them.
    assert not tokens_match("is", "it")
    # A content token never reaches a function word through the base set
    # either, on either side of the comparison.
    assert "the" in FUNCTION_WORDS
    assert not tokens_match("the", "theory")
    assert not tokens_match("theory", "the")


def test_the_base_set_always_contains_the_token_itself() -> None:
    """The exact equality rule, as a property of the set (AC-11)."""
    for token in ("db", "record", "records", "falling", "x"):
        assert token in base_set(token)
