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
# over the cap is discarded as an empty decomposition.
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


# Grammar tokens a sub claim may add at most once each without a parent
# match (spec 0010 AC-11). Exact parent matches consume a parent token first.
ADDED_GRAMMAR_TOKENS = frozenset({"a", "an", "the", "and", "that", "which"})

# The inflections that make a longer token a lexical match of a shorter
# token, provided the shorter token has at least four characters (AC-11).
INFLECTION_SUFFIXES = ("s", "es", "ed", "ing")

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


def _suffix_match(a: str, b: str) -> bool:
    """True when the shorter token has at least four characters and the longer
    is the shorter plus ``s``, ``es``, ``ed``, or ``ing`` (spec 0010 AC-11)."""
    if len(a) == len(b):
        return a == b
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    if len(shorter) < 4:
        return False
    return any(longer == shorter + suffix for suffix in INFLECTION_SUFFIXES)


def _sub_claim_is_lexical_subset(
    sub_tokens: Sequence[str], parent_counts: dict[str, int]
) -> bool:
    """Whether one sub claim's tokens all match an unused parent token.

    Each token matches an unused parent token exactly, or as an added grammar
    token used at most once without a parent match, or through a suffix
    match (spec 0010 AC-11). Matching is per sub claim, never across the
    response, so ``parent_counts`` is copied here.
    """
    counts = dict(parent_counts)
    grammar_used: set[str] = set()
    for token in sub_tokens:
        if counts.get(token, 0) > 0:
            counts[token] -= 1
            continue
        if token in ADDED_GRAMMAR_TOKENS and token not in grammar_used:
            grammar_used.add(token)
            continue
        matched = False
        for parent_token, count in counts.items():
            if count > 0 and _suffix_match(token, parent_token):
                counts[parent_token] -= 1
                matched = True
                break
        if not matched:
            return False
    return True


def decomposition_is_near_subset(
    sub_claim_texts: Sequence[str], parent_text: str
) -> bool:
    """True when every sub claim is a near subset of the parent sentence.

    Each returned sub claim's tokens must all match the parent's token
    multiset under the exact lexical matcher (spec 0010 AC-11); a response
    that introduces vocabulary absent from the parent is not verified as
    written. The check is only a lexical no new vocabulary guardrail. It is
    not a proof that actors, negation, scope, order, or factual relations
    were preserved: deletion and reordering are allowed, which is safe only
    because individually verified sub claims are what get emitted.
    """
    parent_counts: dict[str, int] = {}
    for token in sentence_tokens(parent_text):
        parent_counts[token] = parent_counts.get(token, 0) + 1
    if not parent_counts:
        return False
    return all(
        _sub_claim_is_lexical_subset(sentence_tokens(text), parent_counts)
        for text in sub_claim_texts
    )


def decompose_disposition(
    sub_claim_texts: Sequence[str], parent_text: str
) -> str | None:
    """Classify a nonempty decomposition response (spec 0010 AC-6, AC-11).

    Returns None when the response is accepted, or one closed rejection
    disposition: ``over_cap`` (more than the sanity bound), ``duplicate`` (a
    normalized duplicate row), or ``lexical_guard`` (a sub claim introduces
    vocabulary absent from the parent). The caller records the rejection and
    removes the sentence without calling entailment.
    """
    if len(sub_claim_texts) > MAX_SUB_CLAIMS:
        return "over_cap"
    normalized = [normalize_for_containment(text) for text in sub_claim_texts]
    if len(set(normalized)) != len(normalized):
        return "duplicate"
    if not decomposition_is_near_subset(sub_claim_texts, parent_text):
        return "lexical_guard"
    return None
