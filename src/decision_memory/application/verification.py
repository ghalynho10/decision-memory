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


def sentence_tokens(text: str) -> frozenset[str]:
    """The casefolded, punctuation stripped content tokens of a sentence.

    The decomposition contract check uses this to detect content a response
    introduced that the parent sentence does not contain (spec 0010 AC-11).
    Punctuation and numbers survive only as part of a token; a bare
    punctuation token is dropped.
    """
    tokens: set[str] = set()
    for token in normalize_for_containment(text).split():
        stripped = token.strip(".,;:!?\"'()[]{}<>")
        if stripped:
            tokens.add(stripped)
    return frozenset(tokens)


def decomposition_is_near_subset(
    sub_claim_texts: Sequence[str], parent_text: str
) -> bool:
    """True when every sub claim is a near subset of the parent sentence.

    Each returned sub claim's content tokens must all appear in the parent
    sentence's own text; a response that introduces content absent from the
    parent is not verified as written. The caller discards a violating
    response and treats it as an empty decomposition (spec 0010 AC-11).
    """
    parent_tokens = sentence_tokens(parent_text)
    if not parent_tokens:
        return False
    return all(
        sentence_tokens(sub_claim) <= parent_tokens for sub_claim in sub_claim_texts
    )
