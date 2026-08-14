"""Application: deterministic sentence verification (spec 0007 AC-15).

The deterministic shortcut normalizes a candidate sentence and its cited
chunk text with Unicode NFKC, case folding, line ending normalization, and
whitespace collapse, preserving punctuation and numbers. It passes only when
the complete normalized sentence is a substring of one cited chunk. It never
rejects: every sentence that does not pass goes to model entailment. This
module is pure application code.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

from decision_memory.application.morphology import base_sets_intersect


def normalize_for_containment(text: str) -> str:
    """NFKC, case folding, LF normalization, and whitespace collapse."""
    normalized = unicodedata.normalize("NFKC", text).casefold()
    normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
    return " ".join(normalized.split())


# The sub claim sanity bound: a cap against a runaway decomposition
# response, not a value tuned against data (spec 0010 AC-11). A response
# over the cap is rejected as ``over_cap``.
MAX_SUB_CLAIMS = 8


def deterministic_containment(sentence: str, chunk_texts: Sequence[str]) -> bool:
    """True when the normalized sentence is a substring of a cited chunk.

    This is the pass only shortcut: it returns False to send the sentence to
    entailment, never to reject it (AC-15).
    """
    target = normalize_for_containment(sentence)
    if not target:
        return False
    return any(target in normalize_for_containment(chunk) for chunk in chunk_texts)


# The closed function word set (spec 0010, Feature design). It is exhaustive
# by decision, not a grammatical category the builder extends: a word outside
# it is a content token that must find a parent match, so an unlisted word
# makes the test drop the parent sentence, which loses content but never
# admits a fabrication. Adding a word is a spec edit, not a build time
# judgment.
FUNCTION_WORDS = frozenset(
    {
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
    }
)

# The closed clause relating set (spec 0010 AC-21, enumerated in Feature
# design). A word belongs here when it relates one clause to another, so that
# a decomposition into standalone one clause statements leaves it nothing to
# do. That is decidable by construction: split the sentence and ask whether the
# word still has work. The set is enumerated from that rule, never from the
# next observed failure, and adding a word is a spec edit.
#
# Two exclusion rules keep words out, and both matter more than the inclusions.
# A word whose primary use is a lexical verb, noun, or adjective stays a
# content token (``provided``, ``given``, ``granted``, ``considering``,
# ``seeing``). A word whose second use is truth conditional (a quantity, a
# comparison, a time, a degree, a manner) stays demanded too, which is why
# every temporal subordinator and every correlative marker except ``whether``
# is absent (``once``, ``still``, ``after``, ``than``, ``both``, and the rest).
#
# Members already in ``FUNCTION_WORDS`` are not repeated: the union covers
# them, and the two sets are disjoint by construction. The categories below are
# a reader's aid written as source comments inside the one flat literal; they
# are not a nested structure and nothing flattens anything at runtime.
CLAUSE_CONNECTIVES = frozenset(
    {
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
        # correlative markers: none survive the second exclusion rule
    }
)

# The set the completeness half exempts, and its only reader is
# ``response_is_complete`` (spec 0010 AC-21). The two halves of the AC-11
# validity test deliberately no longer read one vocabulary: the additive half
# keeps ``FUNCTION_WORDS`` alone, because nothing measured implicates it and it
# is the guard standing behind AC-2. So the same word can be a function word to
# one half and a content token to the other, and ``while`` is exactly that.
COMPLETENESS_EXEMPT = FUNCTION_WORDS | CLAUSE_CONNECTIVES

# How many function word tokens one sub claim may add without a parent match,
# counted as instances whatever the words are (spec 0010 AC-11): a sub claim
# adding ``is``, ``not``, and ``there`` fails on the third.
MAX_ADDED_FUNCTION_WORDS = 2

# The edge punctuation stripped from a token; internal apostrophes and
# hyphens remain (spec 0010 AC-11).
_TOKEN_STRIP = ".,;:!?\"'()[]{}<>"


def sentence_tokens(text: str) -> list[str]:
    """The casefolded, edge punctuation stripped tokens of a sentence.

    The decomposition contract check uses these to detect content a response
    introduced that the parent sentence does not contain (spec 0010 AC-11).
    Punctuation and numbers survive only as part of a token; a bare
    punctuation token is dropped. Internal apostrophes and hyphens remain.
    Multiplicity is kept so the multiset matcher can count each token.
    """
    tokens: list[str] = []
    for token in normalize_for_containment(text).split():
        stripped = token.strip(_TOKEN_STRIP)
        if stripped:
            tokens.append(stripped)
    return tokens


def tokens_match(a: str, b: str) -> bool:
    """Whether two tokens are the same word under the AC-11 rules.

    Exact equality always matches, and carries no character floor: it
    transforms no suffix, so the floor guards nothing there, and a token
    already present in the parent is not new vocabulary however short it is
    (``db`` reused verbatim must match). Otherwise a function word never
    matches, on either side, since a function word matches only by exact
    normalized token equality, so the base set is never consulted for one.
    Two content tokens match when they **share a stem**, and sharing a stem is
    symmetric: each token maps to its base set and the two match when those
    sets intersect. This is the one matcher both halves of the validity test
    use, which is why widening it widens the safety critical completeness half
    too, and why task 18 re runs both AC-1 attack tests rather than assuming
    they survive.
    """
    if a == b:
        return True
    if a in FUNCTION_WORDS or b in FUNCTION_WORDS:
        return False
    return base_sets_intersect(a, b)


# The closed categories the additive half can fail in (spec 0010 AC-19). They
# are observational: the tolerance knob, ``MAX_ADDED_FUNCTION_WORDS``, can only
# ever reach ``FUNCTION_WORD_OVERRUN``, and the ``not_additive`` figure task 13
# calibrates against has never been split into the part the knob reaches and
# the part it cannot.
CONTENT_TOKEN = "content_token"
FUNCTION_WORD_OVERRUN = "function_word_overrun"

# The closed sides a validity failure can stop on (spec 0010 AC-20).
# ``SUB_CLAIM_SIDE`` is the additive half stopping on a sub claim token no
# unused parent token matched; ``PARENT_SIDE`` is the completeness half
# stopping on a parent content token no sub claim matched. ``over_cap`` and
# ``duplicate`` stop before any token is examined and carry neither.
SUB_CLAIM_SIDE = "sub_claim"
PARENT_SIDE = "parent"


def sub_claim_is_additive_free(
    sub_tokens: Sequence[str], parent_tokens: Sequence[str]
) -> tuple[str, str] | None:
    """Why one sub claim adds content the parent sentence lacks, or None.

    Returns ``None`` when the sub claim is additive free. Otherwise it returns
    ``(category, token)`` for the token it stopped on: ``CONTENT_TOKEN`` for an
    unmatched content token, ``FUNCTION_WORD_OVERRUN`` for the function word
    that went past ``MAX_ADDED_FUNCTION_WORDS`` (spec 0010 AC-19), paired with
    that token itself (spec 0010 AC-20). Neither value is claim text: the
    category is a closed vocabulary and a single token is not a claim, so the
    trace's no claim text rule is intact.

    The additive half of the AC-11 validity test, scoped **per sub claim**:
    the sub claim is checked alone against the full parent token pool, and
    the caller resets the pool for the next sub claim. A decomposition
    restates the shared subject in each part, which is normal and adds
    nothing, so consuming those tokens across the response would reject a
    correct split of any sentence with a repeated subject.

    Each token takes the first unused parent token it matches, in parent
    order; the assignment is greedy and never backtracks, so two conforming
    builds reach the same verdict. A content token with no match fails the
    sub claim. A function word with no match is instead counted against
    ``MAX_ADDED_FUNCTION_WORDS`` instances per sub claim, whatever the words
    are, and fails only past that bound.

    **The category and the token are read off the point this check already
    stops at, and nothing scans further.** A sub claim carrying both an over
    budget function word and a later unmatched content token records whichever
    came first in token order, so the figures count **first causes**, not
    causes present. Reporting the other would turn this early return into a
    full survey and make the report a second traversal that could disagree
    with the verdict.
    """
    used = [False] * len(parent_tokens)
    added_function_words = 0
    for token in sub_tokens:
        matched = False
        for index, parent_token in enumerate(parent_tokens):
            if not used[index] and tokens_match(token, parent_token):
                used[index] = True
                matched = True
                break
        if matched:
            continue
        if token not in FUNCTION_WORDS:
            return CONTENT_TOKEN, token
        added_function_words += 1
        if added_function_words > MAX_ADDED_FUNCTION_WORDS:
            return FUNCTION_WORD_OVERRUN, token
    return None


def response_is_complete(
    sub_claim_texts: Sequence[str], parent_tokens: Sequence[str]
) -> str | None:
    """The parent content token the sub claims omit, or None when complete.

    The completeness half of the AC-11 validity test, scoped **across the
    whole response**: every distinct content token of the parent must match
    a token in at least one sub claim. Matching is presence based, not
    multiset based, so one occurrence in one sub claim satisfies every
    occurrence of that token in the parent, and a response that splits one
    parent clause across two sub claims still passes. Parent tokens in
    ``COMPLETENESS_EXEMPT`` need no match: the function words, plus the clause
    relating words a decomposition into standalone clauses dissolves by
    construction (spec 0010 AC-21). This is the one place the two halves of the
    validity test read different sets, and the divergence is the decision: the
    additive half still reads ``FUNCTION_WORDS`` alone, so a connective a sub
    claim *introduces* is still content there.

    This is the half that stops the decomposition quietly dropping a clause,
    the omission attack of AC-1: a dropped clause takes its content words out
    of the response entirely. The exemption widens that half for the second
    time in two days, and the residual is named rather than closed: a clause
    carrying no lexical verb, noun, or adjective can now be omitted without
    failing completeness. A fabricated decision names an entity, an action, or
    a property, and every word that does so is a noun, a lexical verb, or an
    adjective, none of which is ever exempt.

    Returns ``None`` when the response is complete, otherwise the first parent
    content token no sub claim matched, in parent token order (spec 0010
    AC-20). **The value is a first cause, not the set of causes present**: a
    later parent token that would also have failed is never recorded, so a
    distribution of these values is the set of tokens that fail *first*. The
    walk stops where the previous ``all(...)`` stopped, so no second traversal
    is introduced and the verdict cannot move.
    """
    response_tokens = [
        token for text in sub_claim_texts for token in sentence_tokens(text)
    ]
    for parent_token in parent_tokens:
        if parent_token in COMPLETENESS_EXEMPT:
            continue
        if not any(tokens_match(parent_token, token) for token in response_tokens):
            return parent_token
    return None


# The dispositions the two half validity test can return, the only ones that
# earn a decomposition retry (spec 0010 AC-11). An ``over_cap`` or
# ``duplicate`` response is rejected outright.
RETRYABLE_DISPOSITIONS = frozenset({"not_additive", "incomplete"})


@dataclass(frozen=True)
class DecompositionVerdict:
    """One classification of one decomposition response (spec 0010 AC-20).

    ``disposition`` decides everything: the retry, the rejection row, and the
    drop. It is one closed value, ``over_cap``, ``duplicate``,
    ``not_additive``, or ``incomplete``, or None when the response is valid.
    The other three fields are observational and no pipeline decision reads
    them.

    ``additive_failure`` is one closed value, ``content_token`` or
    ``function_word_overrun``, and is empty for every disposition other than
    ``not_additive`` (AC-19). ``failure_token`` is the single token the check
    stopped at, and ``failure_side`` is one closed value, ``SUB_CLAIM_SIDE``
    when the additive half stopped, ``PARENT_SIDE`` when the completeness half
    stopped, empty for ``over_cap`` and ``duplicate``, which stop before any
    token is examined.

    This is a named object rather than a four value tuple on purpose. Three of
    the four fields are closed vocabularies that share nothing but their type,
    and two adjacent same typed values read positionally in the wrong order is
    a defect this project has already shipped once (commit ``004dc3c``), where
    the type checker could not see it and the evaluation harness had to.

    ``failure_token`` is the only free string here, and it is a token rather
    than claim text, which is what keeps the trace's no claim text rule
    intact. It is a **first cause**: the token the check stopped at in token
    order, never the set of tokens that would also have failed.
    """

    disposition: str | None
    additive_failure: str = ""
    failure_token: str = ""
    failure_side: str = ""


def classify_decomposition_detail(
    sub_claim_texts: Sequence[str], parent_text: str
) -> DecompositionVerdict:
    """The AC-11 verdict plus its observational detail (AC-19, AC-20).

    One traversal produces one verdict. ``classify_decomposition`` is a
    derivation of this function and never a parallel implementation, so the
    disposition and the detail can never disagree.

    The detail names why the first failing check stopped: for the additive
    half, the category and the token of the first failing sub claim, since the
    scan runs sub claims in order and stops at the first invalid one; for the
    completeness half, the first unmatched parent content token.
    """
    if len(sub_claim_texts) > MAX_SUB_CLAIMS:
        return DecompositionVerdict("over_cap")
    normalized = [normalize_for_containment(text) for text in sub_claim_texts]
    if len(set(normalized)) != len(normalized):
        return DecompositionVerdict("duplicate")
    parent_tokens = sentence_tokens(parent_text)
    for text in sub_claim_texts:
        additive = sub_claim_is_additive_free(sentence_tokens(text), parent_tokens)
        if additive is not None:
            category, token = additive
            return DecompositionVerdict("not_additive", category, token, SUB_CLAIM_SIDE)
    omitted = response_is_complete(sub_claim_texts, parent_tokens)
    if omitted is not None:
        return DecompositionVerdict("incomplete", "", omitted, PARENT_SIDE)
    return DecompositionVerdict(None)


def classify_decomposition(
    sub_claim_texts: Sequence[str], parent_text: str
) -> str | None:
    """Test one nonempty decomposition response for validity (AC-6, AC-11).

    Returns None when the response is a faithful division of the parent
    sentence, so that verifying its sub claims is the same as verifying the
    parent. Otherwise it returns one closed disposition: ``over_cap``,
    ``duplicate``, ``not_additive``, or ``incomplete``.

    The whole response checks run first, in this fixed order and each without
    calling entailment: more than the sanity bound is ``over_cap``, then a
    normalized duplicate row is ``duplicate``. (A malformed row, empty after
    trimming, already failed as ``provider.decompose`` before this, and a
    genuine empty array is handled by the caller.) The two half test runs
    only on a response that survives both: not additive per sub claim
    against a fresh parent pool, then complete across the whole response.

    Validity is a property of the **response**, never of an individual sub
    claim. There is no per sub claim drop: removing a sub claim from a
    response would break the completeness half by construction.

    The test proves only that the sub claims neither add content to the
    parent nor omit content from it, under its token rules. It is not a proof
    that actors, negation, scope, order, or factual relations were preserved.
    A decomposition that preserves every content token while inverting the
    meaning passes it; entailment is the only check that can catch that.

    This is the thin half of ``classify_decomposition_detail``: one
    implementation, so the disposition and its observational detail can never
    disagree.
    """
    return classify_decomposition_detail(sub_claim_texts, parent_text).disposition
