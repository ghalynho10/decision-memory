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


def deterministic_containment(sentence: str, chunk_texts: Sequence[str]) -> bool:
    """True when the normalized sentence is a substring of a cited chunk.

    This is the pass only shortcut: it returns False to send the sentence to
    entailment, never to reject it (AC-15).
    """
    target = normalize_for_containment(sentence)
    if not target:
        return False
    return any(target in normalize_for_containment(chunk) for chunk in chunk_texts)
