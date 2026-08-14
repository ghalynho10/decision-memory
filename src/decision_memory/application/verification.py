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

# How many function word tokens one sub claim may add without a parent match,
# counted as instances whatever the words are (spec 0010 AC-11): a sub claim
# adding ``is``, ``not``, and ``there`` fails on the third.
MAX_ADDED_FUNCTION_WORDS = 2

# The plain suffixes that make a longer token an inflection of a shorter one.
INFLECTION_SUFFIXES = ("s", "es", "ed", "ing")

# The floor a shorter token must reach before any inflection rule may match
# it, measured on the untransformed token (spec 0010 AC-11).
MIN_STEM_LENGTH = 3

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


def _stem_match(a: str, b: str) -> bool:
    """True when two content tokens share a stem (spec 0010 AC-11).

    The five exact rules, naming the two tokens by length: ``longer`` equals
    ``shorter``; or ``longer`` is ``shorter`` plus ``s``, ``es``, ``ed``, or
    ``ing``; or ``shorter`` loses a final ``e`` and gains ``ed`` or ``ing``
    (``use`` and ``using``); or ``shorter`` repeats its own final character
    and gains ``ed`` or ``ing`` (``ship`` and ``shipped``); or ``shorter``
    trades a final ``y`` for ``i`` and gains ``es`` or ``ed`` (``rely`` and
    ``relies``).

    The four inflection rules require ``shorter`` to reach
    ``MIN_STEM_LENGTH``, measured on the untransformed token. Exact equality
    carries no floor, and ``tokens_match`` settles it before reaching here.
    """
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    if len(shorter) < MIN_STEM_LENGTH:
        return False
    if any(longer == shorter + suffix for suffix in INFLECTION_SUFFIXES):
        return True
    for suffix in ("ed", "ing"):
        if shorter.endswith("e") and longer == shorter[:-1] + suffix:
            return True
        if longer == shorter + shorter[-1] + suffix:
            return True
    return any(
        shorter.endswith("y") and longer == shorter[:-1] + "i" + suffix
        for suffix in ("es", "ed")
    )


def tokens_match(a: str, b: str) -> bool:
    """Whether two tokens are the same word under the AC-11 rules.

    Exact equality always matches, and carries no character floor: it
    transforms no suffix, so the floor guards nothing there, and a token
    already present in the parent is not new vocabulary however short it is
    (``db`` reused verbatim must match). Otherwise a function word never
    matches, on either side, since a function word matches only by exact
    normalized token equality. Two content tokens match when they share a
    stem. This is the one matcher both halves of the validity test use.
    """
    if a == b:
        return True
    if a in FUNCTION_WORDS or b in FUNCTION_WORDS:
        return False
    return _stem_match(a, b)


# The closed categories the additive half can fail in (spec 0010 AC-19). They
# are observational: the tolerance knob, ``MAX_ADDED_FUNCTION_WORDS``, can only
# ever reach ``FUNCTION_WORD_OVERRUN``, and the ``not_additive`` figure task 13
# calibrates against has never been split into the part the knob reaches and
# the part it cannot.
CONTENT_TOKEN = "content_token"
FUNCTION_WORD_OVERRUN = "function_word_overrun"


def sub_claim_is_additive_free(
    sub_tokens: Sequence[str], parent_tokens: Sequence[str]
) -> str | None:
    """Why one sub claim adds content the parent sentence lacks, or None.

    Returns ``None`` when the sub claim is additive free. Otherwise it returns
    the closed category of the token it stopped on: ``CONTENT_TOKEN`` for an
    unmatched content token, ``FUNCTION_WORD_OVERRUN`` for the function word
    that went past ``MAX_ADDED_FUNCTION_WORDS`` (spec 0010 AC-19). The
    category is never claim text, so the trace's no claim text rule is intact.

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

    **The category is read off the point this check already stops at, and
    nothing scans further.** A sub claim carrying both an over budget function
    word and a later unmatched content token records whichever came first in
    token order, so the figure counts **first causes**, not causes present.
    Reporting the other would turn this early return into a full survey and
    make the category a second traversal that could disagree with the verdict.
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
            return CONTENT_TOKEN
        added_function_words += 1
        if added_function_words > MAX_ADDED_FUNCTION_WORDS:
            return FUNCTION_WORD_OVERRUN
    return None


def response_is_complete(
    sub_claim_texts: Sequence[str], parent_tokens: Sequence[str]
) -> bool:
    """Whether the sub claims omit no content of the parent sentence.

    The completeness half of the AC-11 validity test, scoped **across the
    whole response**: every distinct content token of the parent must match
    a token in at least one sub claim. Matching is presence based, not
    multiset based, so one occurrence in one sub claim satisfies every
    occurrence of that token in the parent, and a response that splits one
    parent clause across two sub claims still passes. Parent function words
    need no match.

    This is the half that stops the decomposition quietly dropping a clause,
    the omission attack of AC-1: a dropped clause takes its content words out
    of the response entirely.
    """
    response_tokens = [
        token for text in sub_claim_texts for token in sentence_tokens(text)
    ]
    return all(
        any(tokens_match(parent_token, token) for token in response_tokens)
        for parent_token in parent_tokens
        if parent_token not in FUNCTION_WORDS
    )


# The dispositions the two half validity test can return, the only ones that
# earn a decomposition retry (spec 0010 AC-11). An ``over_cap`` or
# ``duplicate`` response is rejected outright.
RETRYABLE_DISPOSITIONS = frozenset({"not_additive", "incomplete"})


def classify_decomposition_detail(
    sub_claim_texts: Sequence[str], parent_text: str
) -> tuple[str | None, str]:
    """The AC-11 verdict plus the AC-19 additive failure category.

    Returns ``(disposition, additive_failure)``. The disposition is exactly
    what ``classify_decomposition`` returns and decides everything: the retry,
    the rejection row, and the drop. The category is observational and empty
    for every disposition other than ``not_additive``; it names why the first
    failing sub claim stopped, on the first sub claim that failed, since
    ``classify_decomposition`` scans sub claims in order and stops at the
    first invalid one.
    """
    if len(sub_claim_texts) > MAX_SUB_CLAIMS:
        return "over_cap", ""
    normalized = [normalize_for_containment(text) for text in sub_claim_texts]
    if len(set(normalized)) != len(normalized):
        return "duplicate", ""
    parent_tokens = sentence_tokens(parent_text)
    for text in sub_claim_texts:
        additive_failure = sub_claim_is_additive_free(
            sentence_tokens(text), parent_tokens
        )
        if additive_failure is not None:
            return "not_additive", additive_failure
    if not response_is_complete(sub_claim_texts, parent_tokens):
        return "incomplete", ""
    return None, ""


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
    implementation, so the disposition and the AC-19 category can never
    disagree.
    """
    return classify_decomposition_detail(sub_claim_texts, parent_text)[0]
