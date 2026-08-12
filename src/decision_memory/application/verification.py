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
# makes the guard drop a sub claim, which loses content but never admits a
# fabrication. Adding a word is a spec edit, not a build time judgment.
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
    carries no floor: it manipulates no suffix, so the floor has nothing to
    guard there, and a token already present in the parent multiset is not
    new vocabulary however short it is. (AC-11 states the floor once for all
    five rules; that literal reading would drop a sub claim reusing a short
    parent token such as ``db`` or a bare number, which contradicts the same
    criterion's opening multiset rule. Owed as a one line spec
    clarification.)
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


def sub_claim_is_lexical_subset(
    sub_tokens: Sequence[str], parent_counts: dict[str, int]
) -> bool:
    """Whether one sub claim introduces no unmatched content vocabulary.

    Each token consumes an unused parent token by exact equality; failing
    that, a function word may be added without a parent match, up to
    ``MAX_ADDED_FUNCTION_WORDS`` instances per sub claim, and a content token
    may consume an unused parent content token that shares its stem (spec
    0010 AC-11). A function word never matches by stem, and a content token
    never consumes a parent function word. Matching is per sub claim, never
    across the response, so ``parent_counts`` is copied here.
    """
    counts = dict(parent_counts)
    added_function_words = 0
    for token in sub_tokens:
        if counts.get(token, 0) > 0:
            counts[token] -= 1
            continue
        if token in FUNCTION_WORDS:
            added_function_words += 1
            if added_function_words > MAX_ADDED_FUNCTION_WORDS:
                return False
            continue
        matched = False
        for parent_token, count in counts.items():
            if (
                count > 0
                and parent_token not in FUNCTION_WORDS
                and _stem_match(token, parent_token)
            ):
                counts[parent_token] -= 1
                matched = True
                break
        if not matched:
            return False
    return True


@dataclass(frozen=True)
class DecompositionOutcome:
    """How one nonempty decomposition response was classified (AC-6, AC-11).

    ``rejection`` is None when at least one sub claim survives, else one
    closed whole response disposition: ``over_cap``, ``duplicate``, or
    ``lexical_guard`` (here meaning no sub claim was acceptable). A wholesale
    rejection carries no ``accepted`` and no ``dropped`` positions, so one
    event is never counted twice. ``accepted`` and ``dropped`` hold zero
    based provider positions, so a dropped sub claim keeps its position and
    the accepted ids skip only where a drop accounts for them.
    """

    rejection: str | None
    accepted: tuple[tuple[int, str], ...] = ()
    dropped: tuple[int, ...] = ()


def classify_decomposition(
    sub_claim_texts: Sequence[str], parent_text: str
) -> DecompositionOutcome:
    """Classify a nonempty decomposition response (spec 0010 AC-6, AC-11).

    The whole response checks run first, in this order: more than the sanity
    bound is ``over_cap``, then a normalized duplicate row is ``duplicate``,
    each without calling entailment. The per sub claim guard runs only on a
    response that survives both, dropping each sub claim that introduces
    unmatched content vocabulary as an individual and rejecting the whole
    response as ``lexical_guard`` only when no sub claim is acceptable.

    The guard is only a lexical no new content vocabulary guardrail. It is
    not a proof that actors, negation, scope, order, or factual relations
    were preserved: deletion and reordering are allowed, which is safe only
    because individually verified sub claims are what get emitted.
    """
    if len(sub_claim_texts) > MAX_SUB_CLAIMS:
        return DecompositionOutcome("over_cap")
    normalized = [normalize_for_containment(text) for text in sub_claim_texts]
    if len(set(normalized)) != len(normalized):
        return DecompositionOutcome("duplicate")
    parent_counts: dict[str, int] = {}
    for token in sentence_tokens(parent_text):
        parent_counts[token] = parent_counts.get(token, 0) + 1
    accepted: list[tuple[int, str]] = []
    dropped: list[int] = []
    for position, text in enumerate(sub_claim_texts):
        if parent_counts and sub_claim_is_lexical_subset(
            sentence_tokens(text), parent_counts
        ):
            accepted.append((position, text))
        else:
            dropped.append(position)
    if not accepted:
        return DecompositionOutcome("lexical_guard")
    return DecompositionOutcome(None, tuple(accepted), tuple(dropped))
