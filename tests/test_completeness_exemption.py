"""The AC-21 completeness exemption, locked as a closed set (spec 0010).

The two halves of the AC-11 validity test stopped sharing one vocabulary here.
``FUNCTION_WORDS`` still serves ``tokens_match`` and the additive half;
``COMPLETENESS_EXEMPT`` is read by ``response_is_complete`` and by nothing
else. So the same word can be a function word to one half and a content token
to the other, and these tests prove the asymmetry rather than assume it.

**The exclusion tests matter more than the inclusion tests.** A wrong
inclusion is the failure mode this decision carries: an exempt word is one the
omission guard can no longer catch, so the words deliberately kept out are the
ones worth locking. Both exclusion lists are pinned below by name.

The three tokens with a measured live failure (``where``, ``while``,
``instead``) are tested against the exact sentences experiments 0011 and 0012
quote, so a later reader can see the case rather than a paraphrase of it.
"""

from __future__ import annotations

from decision_memory.application.verification import (
    CLAUSE_CONNECTIVES,
    COMPLETENESS_EXEMPT,
    CONTENT_TOKEN,
    FUNCTION_WORDS,
    response_is_complete,
    sentence_tokens,
    sub_claim_is_additive_free,
    tokens_match,
)

# The pinned enumeration (spec 0010 Feature design), written out here in full
# rather than derived from the constant, so a member added or dropped in the
# source is a test failure rather than a silent change to what the omission
# guard can catch.
_PINNED_CLAUSE_CONNECTIVES = (
    # coordinating conjunctions
    "yet",
    # subordinating conjunctions
    "albeit",
    "although",
    "lest",
    "though",
    "unless",
    "whereas",
    "whether",
    "while",
    "whilst",
    # conjunctive adverbs
    "accordingly",
    "additionally",
    "also",
    "anyway",
    "consequently",
    "conversely",
    "furthermore",
    "hence",
    "however",
    "indeed",
    "instead",
    "likewise",
    "meanwhile",
    "moreover",
    "namely",
    "nevertheless",
    "nonetheless",
    "otherwise",
    "rather",
    "regardless",
    "subsequently",
    "therefore",
    "thereby",
    "thus",
    # relative and interrogative pro-forms
    "how",
    "whatever",
    "whenever",
    "where",
    "whereby",
    "wherein",
    "whereupon",
    "wherever",
    "whichever",
    "who",
    "whoever",
    "whom",
    "whose",
    "why",
)

# The 56 word closed function set (spec 0010 Feature design), unchanged by this
# amendment. Pinned by value because AC-21's whole safety argument rests on the
# additive half reading exactly this and nothing more.
_PINNED_FUNCTION_WORDS = (
    "a",
    "an",
    "the",
    "and",
    "that",
    "which",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "has",
    "have",
    "had",
    "do",
    "does",
    "did",
    "can",
    "could",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    "to",
    "of",
    "for",
    "with",
    "by",
    "as",
    "at",
    "on",
    "in",
    "from",
    "about",
    "so",
    "but",
    "or",
    "if",
    "because",
    "when",
    "then",
    "there",
    "it",
    "this",
    "these",
    "those",
    "their",
    "not",
    "no",
    "never",
    "nor",
)

# Excluded because the primary use is a lexical verb, noun, or adjective.
_EXCLUDED_CONTENT_WORDS = (
    "provided",
    "given",
    "granted",
    "considering",
    "seeing",
)

# Excluded because the second use is truth conditional (a quantity, a
# comparison, a time, a degree, a manner) rather than clause relating.
_EXCLUDED_TRUTH_CONDITIONAL = (
    "once",
    "still",
    "further",
    "finally",
    "specifically",
    "similarly",
    "after",
    "before",
    "since",
    "till",
    "until",
    "than",
    "except",
    "besides",
    "both",
    "either",
    "neither",
)


# ---------------------------------------------------------------------------
# The sets themselves.
# ---------------------------------------------------------------------------


def test_clause_connectives_match_the_pinned_enumeration() -> None:
    """The set is exactly the 48 members Feature design enumerates.

    Counted as well as compared: a duplicate in the source literal would be
    absorbed silently by the set, so the count is checked against the pinned
    tuple's own distinct length and against the stated 48.
    """
    assert len(_PINNED_CLAUSE_CONNECTIVES) == len(set(_PINNED_CLAUSE_CONNECTIVES))
    assert len(_PINNED_CLAUSE_CONNECTIVES) == 48
    assert frozenset(_PINNED_CLAUSE_CONNECTIVES) == CLAUSE_CONNECTIVES


def test_the_two_sets_are_disjoint_and_the_union_is_the_exempt_set() -> None:
    """Disjoint by construction, so the union absorbs no duplicate.

    Members already in ``FUNCTION_WORDS`` are deliberately not repeated in
    ``CLAUSE_CONNECTIVES``. If one were, the union would still be correct and
    the enumeration would quietly stop matching the spec table, which is the
    kind of drift the count test above cannot see on its own.
    """
    assert CLAUSE_CONNECTIVES.isdisjoint(FUNCTION_WORDS)
    assert COMPLETENESS_EXEMPT == FUNCTION_WORDS | CLAUSE_CONNECTIVES
    assert len(COMPLETENESS_EXEMPT) == len(FUNCTION_WORDS) + len(CLAUSE_CONNECTIVES)


def test_function_words_are_unchanged_by_value() -> None:
    """The additive half's vocabulary did not move.

    AC-21 loosens the completeness half only. Moving a connective into
    ``FUNCTION_WORDS`` instead would convert it from budgeted under
    ``MAX_ADDED_FUNCTION_WORDS`` to free on the additive side, which is the
    trade OD-8 refused, so this set is pinned by value.
    """
    assert frozenset(_PINNED_FUNCTION_WORDS) == FUNCTION_WORDS
    assert len(_PINNED_FUNCTION_WORDS) == len(set(_PINNED_FUNCTION_WORDS))
    assert len(FUNCTION_WORDS) == 56


# ---------------------------------------------------------------------------
# The completeness half: every member exempt, every excluded word demanded.
# ---------------------------------------------------------------------------


def test_every_clause_connective_is_exempt_from_the_completeness_demand() -> None:
    """No member of the set can be the token completeness stops on.

    Each member is placed in a parent sentence and omitted from the response.
    Before AC-21 every one of these returned itself; now the check walks past
    it to the next demanded token, of which the parent has none.
    """
    kept = "The gate accepted the record."
    for word in _PINNED_CLAUSE_CONNECTIVES:
        parent = f"The gate accepted the record, {word} the gate accepted it."
        assert word in COMPLETENESS_EXEMPT
        assert response_is_complete((kept,), sentence_tokens(parent)) is None, word


def test_the_three_measured_tokens_against_the_sentences_they_stopped_on() -> None:
    """``where``, ``while``, and ``instead``, on the real live sentences.

    These are the exact parent sentences experiments 0011 and 0012 quote, each
    of which abstained on the token named here, stable across runs. The
    response is the parent with only that one token removed, which isolates
    the change: the whole rest of the sentence is present, so the only reason
    the check could stop is the connective itself.

    Three tokens in three grammatical categories (a relative adverb, a
    subordinating conjunction, and a conjunctive adverb), which is why AC-21
    is stated over the function rather than over any one part of speech.
    """
    cases = (
        (
            "where",
            "The decision was made to use a fallback behavior for resume "
            "generation, where a role whose bullets are affected by a dropped "
            "number never ends up empty, and only the offending bullet is "
            "dropped first, with the role falling back to the user's own "
            "written text if necessary.",
        ),
        (
            "while",
            "The private beta access gate was added to ensure that only "
            "approved users can access certain features, while unapproved "
            "users are redirected to a private beta screen, preventing "
            "unauthorized access to paid routes.",
        ),
        (
            "instead",
            "The Adzuna job discovery feature refetches data client side "
            "because it needs a real database query against the `jobs` table "
            "for filtering, sorting, and pagination, and building the client "
            "side refetch now contributes toward that path instead of "
            "producing a response shape that would be discarded later.",
        ),
    )
    for token, parent in cases:
        parent_tokens = sentence_tokens(parent)
        assert token in parent_tokens, token
        # The response carries every parent token except the connective.
        response = " ".join(t for t in parent_tokens if t != token)
        assert response_is_complete((response,), parent_tokens) is None, token


def test_both_exclusion_lists_are_still_demanded() -> None:
    """The words deliberately kept out still fail completeness.

    This is the half of the enumeration worth locking. A word that slipped
    into the set would be one the omission guard silently stopped catching,
    and nothing else in the suite would notice.
    """
    kept = "The gate accepted the record."
    for word in _EXCLUDED_CONTENT_WORDS + _EXCLUDED_TRUTH_CONDITIONAL:
        parent = f"The gate accepted the record, {word} the gate ran."
        assert word not in COMPLETENESS_EXEMPT, word
        assert response_is_complete((kept,), sentence_tokens(parent)) == word


def test_the_named_cost_of_excluding_both() -> None:
    """``both`` is the sharpest exclusion, and its cost is a real drop.

    Its two uses point opposite ways: the correlative use really is dissolved
    by a split, and the quantifier use really does carry content. The
    exclusion takes the quantifier reading, so a correlative sentence can be
    dropped on ``both``. That is the exclusion being paid for, recorded here
    so a live ``failure_token`` of ``both`` reads as expected rather than as a
    surprise, and it is the one member of either list worth revisiting on
    evidence.
    """
    parent = "The pipeline uses both BM25 and Chroma."
    response = ("The pipeline uses BM25.", "The pipeline uses Chroma.")
    assert response_is_complete(response, sentence_tokens(parent)) == "both"


# ---------------------------------------------------------------------------
# The additive half, which deliberately does not share the list.
# ---------------------------------------------------------------------------


def test_every_clause_connective_is_still_content_to_the_additive_half() -> None:
    """The asymmetry, proven rather than assumed.

    A sub claim that *introduces* a connective the parent never had is adding
    a clause relation, which is adding content, so it still fails as
    ``not_additive`` with ``additive_failure=content_token``. Nothing measured
    implicates the additive half, and it is the guard behind AC-2, so it keeps
    reading ``FUNCTION_WORDS`` alone.
    """
    parent_tokens = sentence_tokens("The alpha beta gamma.")
    for word in _PINNED_CLAUSE_CONNECTIVES:
        assert word not in FUNCTION_WORDS, word
        assert sub_claim_is_additive_free((word,), parent_tokens) == (
            CONTENT_TOKEN,
            word,
        ), word


def test_tokens_match_is_untouched_by_the_new_set() -> None:
    """The matcher both halves share keeps the exact OD-8 semantics.

    ``tokens_match`` reads ``FUNCTION_WORDS`` and never
    ``COMPLETENESS_EXEMPT``, so no safety argument about the base set matcher
    has to be made a second time. A connective still stem matches like any
    content token, which is what shows the new set did not leak into the
    matcher as a second exact only class.
    """
    # The OD-8 pairs, unchanged.
    assert tokens_match("falls", "falling")
    assert tokens_match("drops", "dropped")
    assert tokens_match("decides", "deciding")
    assert tokens_match("use", "using")
    assert tokens_match("ship", "shipped")
    assert tokens_match("rely", "relies")
    # Function words still match by exact equality only.
    assert not tokens_match("no", "not")
    # A connective is still a content token to the matcher: it stem matches,
    # which an exact only class would not.
    assert tokens_match("while", "whiles")
    # The exemption itself is exact membership, never a stem lookup, so an
    # inflection of an exempt word is not reached by accident.
    assert "wheres" not in COMPLETENESS_EXEMPT
