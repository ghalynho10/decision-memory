"""Infrastructure: the BM25 lexical scorer (spec 0008 AC-5, AC-16).

``rank_bm25`` is the one place BM25 lives, and application code receives it as
the injected ``LexicalScorer`` callable, so no application module imports it.
Each query rebuilds a small in memory BM25Okapi corpus from the accepted chunk
token tuples in chunk id order and returns one finite raw score per document,
positionally aligned.
"""

from __future__ import annotations

from collections.abc import Sequence

from rank_bm25 import BM25Okapi  # type: ignore[import-untyped]


def bm25_lexical_scorer(
    query_tokens: Sequence[str],
    document_tokens: Sequence[Sequence[str]],
) -> Sequence[float]:
    """One finite BM25 score per document, positionally aligned (AC-5).

    Uses ``BM25Okapi`` with library defaults. An empty corpus scores nothing.
    """
    corpus = [list(tokens) for tokens in document_tokens]
    if not corpus:
        return ()
    model = BM25Okapi(corpus)
    return tuple(model.get_scores(list(query_tokens)))
