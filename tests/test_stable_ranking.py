"""Build stable ranking tests (spec 0012).

Retrieval used to break ties on ``chunk_id``, which hashes the generation id
and is therefore fresh on every build even when the content is byte identical,
so which chunks reached the model depended on which build ran. These lock the
replacement key and the properties that make it a real fix rather than a
different arbitrary one:

* the key is total, so nothing ever falls back to an unstable value
* ranking output is unchanged when every chunk id is replaced
* the trace reordering moves rows only, never a rank or a disposition
* the lexical scorer does not read document order, which is the other way a
  build could have leaked into ranking
"""

from __future__ import annotations

import random

from decision_memory.application.dto import (
    ActiveChunkDescriptor,
    LexicalDisposition,
)
from decision_memory.application.lexical import tokenize
from decision_memory.application.query import (
    ACCEPTED_LIMIT,
    _diversity_stage,
    _fusion_stage,
    _lexical_stage,
    stable_sort_key,
)
from decision_memory.infrastructure.bm25 import bm25_lexical_scorer


def _desc(
    chunk_id: str,
    record_id: str,
    text: str = "server side database text",
    value_path: str = "body[0]",
    ordinal: int = 0,
    fingerprint: str = "fp",
) -> ActiveChunkDescriptor:
    return ActiveChunkDescriptor(
        chunk_id=chunk_id,
        record_id=record_id,
        record_title="Title",
        record_status="accepted",
        record_tags=(),
        value_path=value_path,
        fingerprint=fingerprint,
        ordinal=ordinal,
        text=text,
        provenance=(),
    )


def _corpus(chunk_ids: list[str]) -> dict[str, ActiveChunkDescriptor]:
    """Twelve chunks over six records, keyed by the given ids in order.

    The content and the stable key of the chunk at each position are fixed; the
    only thing a caller varies is which chunk id is attached to it.
    """
    return {
        chunk_id: _desc(
            chunk_id,
            f"DM-{index // 2:04d}",
            text=f"server database record {index // 2} part {index % 2}",
            value_path=f"body[{index % 2}]",
        )
        for index, chunk_id in enumerate(chunk_ids)
    }


ORDERED_IDS = [f"ch_{index:02d}" for index in range(12)]
# The same twelve positions with ids that sort the other way, which is what a
# rebuild effectively does: same content, different names, different order.
REVERSED_IDS = [f"ch_{99 - index:02d}" for index in range(12)]


# --- AC-2: the key is total -------------------------------------------------


def test_stable_key_is_total_over_a_realistic_accepted_set() -> None:
    """No two chunks of one store share the key, so the sort never falls back.

    The store's own ``UNIQUE (generation_id, record_id, active_fingerprint,
    value_path, ordinal)`` makes this hold, and one reader reads one
    generation, so the constraint reduces to this quadruple.
    """
    corpus = _corpus(ORDERED_IDS)
    keys = [stable_sort_key(chunk) for chunk in corpus.values()]
    assert len(set(keys)) == len(keys)


def test_fingerprint_keeps_the_key_total_when_a_triple_is_duplicated() -> None:
    """The stale chunk case (scope feature 21) must still rank deterministically.

    An in place record update currently leaves the superseded chunk rows in the
    store, so two active chunks can share ``(record_id, value_path, ordinal)``
    and differ only in fingerprint. This is why the key is a quadruple, and the
    test pins it so a later reader cannot simplify it back to a triple.
    """
    current = _desc("ch_new", "DM-0001", fingerprint="fp-new")
    superseded = _desc("ch_old", "DM-0001", fingerprint="fp-old")
    assert (current.record_id, current.value_path, current.ordinal) == (
        superseded.record_id,
        superseded.value_path,
        superseded.ordinal,
    )
    assert stable_sort_key(current) != stable_sort_key(superseded)
    # Dropping the fingerprint would collapse them, which is the regression
    # this criterion exists to prevent.
    triple = lambda chunk: (chunk.record_id, chunk.value_path, chunk.ordinal)  # noqa: E731
    assert triple(current) == triple(superseded)


# --- AC-3: permutation invariance ------------------------------------------


class TiedScorer:
    """Scores by content, not position, with deliberate ties.

    The stage hands documents to the scorer in chunk id order, so a scorer that
    scored by position would move its own scores when the ids move and the test
    would be measuring the fixture rather than the tie break. Keying on the
    document's own tokens holds the scores fixed and leaves the tie as the only
    thing the ranking has to resolve.
    """

    def __call__(self, query_tokens, document_tokens):  # type: ignore[no-untyped-def]
        return [2.0 if "record" in tokens else 1.0 for tokens in document_tokens]


def _lexical_order(corpus: dict[str, ActiveChunkDescriptor]) -> list[tuple]:
    _trace, ranked = _lexical_stage("server database record", corpus, TiedScorer())
    return [
        (rank, stable_sort_key(corpus[chunk_id])) for chunk_id, rank in ranked.items()
    ]


def test_lexical_ranking_is_unchanged_when_every_chunk_id_moves() -> None:
    """Every chunk ties with eleven others, so only the tie break decides rank."""
    ordered = _lexical_order(_corpus(ORDERED_IDS))
    renamed = _lexical_order(_corpus(REVERSED_IDS))
    assert len({rank for rank, _key in ordered}) == len(ordered)
    assert sorted(ordered) == sorted(renamed)


def _fused_order(
    corpus: dict[str, ActiveChunkDescriptor],
    lexical: dict[int, int],
    semantic: dict[int, int],
) -> list[tuple]:
    """Fused order as stable keys, given ranks addressed by chunk position."""
    ids = list(corpus)
    ranked_lexical = {ids[position]: rank for position, rank in lexical.items()}
    ranked_semantic = {ids[position]: rank for position, rank in semantic.items()}
    candidates = _fusion_stage(ranked_lexical, ranked_semantic, corpus)
    return [stable_sort_key(corpus[candidate.chunk_id]) for candidate in candidates]


# Today's reachable tie class: a chunk ranked by one retriever at rank r scores
# exactly what a chunk ranked by the other retriever at rank r scores, because
# both contribute 1 / (60 + r). Positions 0 and 1 collide here, as do 2 and 3.
TODAY_LEXICAL = {0: 1, 2: 2, 4: 3}
TODAY_SEMANTIC = {1: 1, 3: 2, 5: 4}

# The class spec 0011 AC-3 and AC-4 make reachable and that is impossible
# today: a chunk ranked by both retrievers colliding with one ranked by a
# single retriever. 1/122 + 1/122 == 1/61, so a chunk at lexical 62 and
# semantic 62 ties with a chunk at semantic 1 alone. Both ranks are past the
# top 24 boundary, which is exactly why this cannot occur before that spec.
POST_0011_LEXICAL = {0: 62, 2: 70}
POST_0011_SEMANTIC = {0: 62, 1: 1, 2: 70, 3: 1}


def test_fusion_order_is_unchanged_when_every_chunk_id_moves_today() -> None:
    ordered = _fused_order(_corpus(ORDERED_IDS), TODAY_LEXICAL, TODAY_SEMANTIC)
    renamed = _fused_order(_corpus(REVERSED_IDS), TODAY_LEXICAL, TODAY_SEMANTIC)
    assert ordered == renamed


def test_fusion_order_is_unchanged_under_the_post_0011_tie_class() -> None:
    """The key must survive the tie population feature 19 replaces.

    A rule that read a retrieval signal would be tuned against today's classes;
    this one reads identity, so it holds under both.
    """
    ordered = _fused_order(_corpus(ORDERED_IDS), POST_0011_LEXICAL, POST_0011_SEMANTIC)
    renamed = _fused_order(_corpus(REVERSED_IDS), POST_0011_LEXICAL, POST_0011_SEMANTIC)
    assert ordered == renamed


def test_the_post_0011_shape_really_does_tie() -> None:
    """Guard the fixture above: a tie that is not a tie proves nothing."""
    corpus = _corpus(ORDERED_IDS)
    ids = list(corpus)
    candidates = _fusion_stage(
        {ids[0]: 62, ids[2]: 70},
        {ids[0]: 62, ids[1]: 1, ids[2]: 70, ids[3]: 1},
        corpus,
    )
    scores = {candidate.chunk_id: candidate.fused_score for candidate in candidates}
    assert scores[ids[0]] == scores[ids[1]]
    assert len({candidate.fused_score for candidate in candidates}) < len(candidates)


def _accepted_keys(
    corpus: dict[str, ActiveChunkDescriptor],
    lexical: dict[int, int],
    semantic: dict[int, int],
) -> list[tuple]:
    ids = list(corpus)
    candidates = _fusion_stage(
        {ids[position]: rank for position, rank in lexical.items()},
        {ids[position]: rank for position, rank in semantic.items()},
        corpus,
    )
    _final, accepted = _diversity_stage(candidates, corpus)
    return [stable_sort_key(chunk) for chunk in accepted]


def test_accepted_context_is_unchanged_when_every_chunk_id_moves() -> None:
    """The property that actually reaches the answer.

    The accepted list is what the generation context is built from, and it is
    compared in order, because two builds accepting the same chunks in a
    different order have still handed the model different input.
    """
    lexical = {position: position + 1 for position in range(0, 12, 2)}
    semantic = {position: position for position in range(1, 12, 2)}
    ordered = _accepted_keys(_corpus(ORDERED_IDS), lexical, semantic)
    renamed = _accepted_keys(_corpus(REVERSED_IDS), lexical, semantic)
    assert ordered == renamed
    assert len(ordered) == ACCEPTED_LIMIT


# --- AC-5 and AC-9: the trace reordering moves rows only --------------------


def test_trace_rows_reorder_without_moving_rank_or_disposition() -> None:
    """Row order changes; rank, score, and disposition come from the score order.

    Re sorting the chunk bearing collection instead would have reassigned rank
    and, on the lexical side, the disposition and the fusion eligible set with
    it. This pins that the ordering is presentational.
    """
    corpus = _corpus(ORDERED_IDS)
    trace, ranked = _lexical_stage(
        "server database record", corpus, bm25_lexical_scorer
    )

    # Rows are in stable key order.
    assert [row.chunk_id for row in trace.rows] == sorted(
        (row.chunk_id for row in trace.rows),
        key=lambda chunk_id: stable_sort_key(corpus[chunk_id]),
    )
    # Rank still follows score descending, which is the order rank was assigned
    # from, and not the row order.
    positive = [row for row in trace.rows if row.rank is not None]
    by_rank = sorted(positive, key=lambda row: row.rank or 0)
    scores = [row.score for row in by_rank]
    assert scores == sorted(scores, reverse=True)
    assert [row.rank for row in by_rank] == list(range(1, len(by_rank) + 1))
    # Every ranked row is in the fusion eligible set, and no other row is.
    assert set(ranked) == {
        row.chunk_id
        for row in trace.rows
        if row.disposition == LexicalDisposition.RANKED
    }


def test_trace_row_order_is_unchanged_when_every_chunk_id_moves() -> None:
    """Two builds of one corpus produce comparable traces (the AC-5 point)."""

    def order(corpus: dict[str, ActiveChunkDescriptor]) -> list[tuple]:
        trace, _ranked = _lexical_stage(
            "server database record", corpus, bm25_lexical_scorer
        )
        return [stable_sort_key(corpus[row.chunk_id]) for row in trace.rows]

    assert order(_corpus(ORDERED_IDS)) == order(_corpus(REVERSED_IDS))


# --- AC-6: the scorer does not read document order --------------------------


def test_lexical_scorer_is_independent_of_document_order() -> None:
    """The other route a build could reach ranking, and it is closed.

    The lexical stage feeds documents to the scorer in chunk id order, which is
    fresh on every build, so a scorer with any order sensitivity would leave
    retrieval build dependent even with a stable tie key. Measured on the real
    corpus at exactly zero difference; pinned here so a scorer swap cannot
    reintroduce it.
    """
    documents = [
        tokenize(f"record {index} server database prose about the decision {index}")
        for index in range(40)
    ]
    query = tokenize("server database decision")
    baseline = list(bm25_lexical_scorer(query, documents))

    order = list(range(len(documents)))
    random.Random(7).shuffle(order)
    shuffled = list(bm25_lexical_scorer(query, [documents[index] for index in order]))
    remapped = [0.0] * len(documents)
    for position, source in enumerate(order):
        remapped[source] = shuffled[position]

    assert remapped == baseline
