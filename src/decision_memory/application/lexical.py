"""Application: the exact lexical tokenizer and stopword vocabulary (spec 0008).

``lexical-tokenizer-v1`` is the exact algorithm from the spec: NFC normalize,
single ``str.lower()``, a left to right code point scan, then exact stopword
removal with no stemming. The stopword vocabulary is pinned in this module so
the application stays pure (no file I/O). The pinned digest is verified at
import, so a vocabulary or rule change that moves the digest fails loudly.
``rank_bm25`` itself is an infrastructure concern and never imported here.
"""

from __future__ import annotations

import hashlib
import unicodedata

# The tokenizer and vocabulary identifiers, recorded in every query settings
# trace (AC-10). A tokenizer rule or vocabulary change requires new ids.
LEXICAL_TOKENIZER_VERSION = "lexical-tokenizer-v1"
STOPWORD_SET = "lexical-stopwords-v1"

# The pinned SHA256 over the 171 UTF8 words in ascending code point order,
# joined by LF with no trailing LF (AC-5).
STOPWORD_DIGEST = "fe2b3373712ce97c07caa0da916d1e2bc8bff4f3ba44a109ad059bd8f2459db6"

_STOPWORD_WORDS = (
    "a",
    "about",
    "above",
    "after",
    "again",
    "against",
    "all",
    "am",
    "an",
    "and",
    "any",
    "are",
    "aren't",
    "as",
    "at",
    "be",
    "because",
    "been",
    "before",
    "being",
    "below",
    "between",
    "both",
    "but",
    "by",
    "can't",
    "cannot",
    "could",
    "couldn't",
    "did",
    "didn't",
    "do",
    "does",
    "doesn't",
    "doing",
    "don't",
    "down",
    "during",
    "each",
    "few",
    "for",
    "from",
    "further",
    "had",
    "hadn't",
    "has",
    "hasn't",
    "have",
    "haven't",
    "having",
    "he",
    "he'd",
    "he'll",
    "he's",
    "her",
    "here",
    "here's",
    "hers",
    "herself",
    "him",
    "himself",
    "his",
    "how",
    "how's",
    "i",
    "i'd",
    "i'll",
    "i'm",
    "i've",
    "if",
    "in",
    "into",
    "is",
    "isn't",
    "it",
    "it's",
    "its",
    "itself",
    "let's",
    "me",
    "more",
    "most",
    "mustn't",
    "my",
    "myself",
    "of",
    "off",
    "on",
    "once",
    "only",
    "or",
    "other",
    "ought",
    "our",
    "ours",
    "ourselves",
    "out",
    "over",
    "own",
    "same",
    "shan't",
    "she",
    "she'd",
    "she'll",
    "she's",
    "should",
    "shouldn't",
    "so",
    "some",
    "such",
    "than",
    "that",
    "that's",
    "the",
    "their",
    "theirs",
    "them",
    "themselves",
    "then",
    "there",
    "there's",
    "these",
    "they",
    "they'd",
    "they'll",
    "they're",
    "they've",
    "this",
    "those",
    "through",
    "to",
    "too",
    "under",
    "until",
    "up",
    "very",
    "was",
    "wasn't",
    "we",
    "we'd",
    "we'll",
    "we're",
    "we've",
    "were",
    "weren't",
    "what",
    "what's",
    "when",
    "when's",
    "where",
    "where's",
    "which",
    "while",
    "who",
    "who's",
    "whom",
    "why",
    "why's",
    "with",
    "won't",
    "would",
    "wouldn't",
    "you",
    "you'd",
    "you'll",
    "you're",
    "you've",
    "your",
    "yours",
    "yourself",
    "yourselves",
)

STOPWORDS = frozenset(_STOPWORD_WORDS)

_APOSTROPHES = frozenset(("'", "\u2019"))


def stopword_digest() -> str:
    """The SHA256 over the vocabulary in ascending code point order (AC-5)."""
    payload = "\n".join(sorted(_STOPWORD_WORDS))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


if stopword_digest() != STOPWORD_DIGEST:
    raise RuntimeError("lexical stopword digest moved; update STOPWORD_DIGEST")


def _is_letter(char: str) -> bool:
    return unicodedata.category(char).startswith("L")


def _is_ascii_digit(char: str) -> bool:
    return "0" <= char <= "9"


def _is_combining_mark(char: str) -> bool:
    return unicodedata.category(char) in ("Mn", "Mc", "Me")


def tokenize(text: str) -> tuple[str, ...]:
    """The exact ``lexical-tokenizer-v1`` final tokens (AC-5).

    Tokens preserve order and duplicates. An entire token is removed only when
    it exactly equals a stopword; ``no``, ``not``, and ``nor`` are absent from
    the vocabulary so negation stays searchable.
    """
    lowered = unicodedata.normalize("NFC", text).lower()
    tokens: list[str] = []
    current: list[str] = []
    length = len(lowered)
    for index, char in enumerate(lowered):
        if _is_letter(char) or _is_ascii_digit(char):
            current.append(char)
            continue
        if _is_combining_mark(char):
            if current:
                current.append(char)
            continue
        if char in _APOSTROPHES:
            previous_ok = index > 0 and (
                _is_letter(lowered[index - 1]) or _is_ascii_digit(lowered[index - 1])
            )
            next_ok = index + 1 < length and (
                _is_letter(lowered[index + 1]) or _is_ascii_digit(lowered[index + 1])
            )
            if previous_ok and next_ok:
                current.append(char)
                continue
        if current:
            tokens.append("".join(current))
            current = []
    if current:
        tokens.append("".join(current))
    return tuple(token for token in tokens if token not in STOPWORDS)
