"""Chroma parity integration tests (spec 0007 AC-6).

Uses an ephemeral in memory Chroma client, so it needs no server. Marked
integration because chromadb is a heavy import; the fast unit suite skips it.
"""

from __future__ import annotations

import pytest

from decision_memory.infrastructure.chroma_store import (
    _client,
    is_valid_distance,
    locator_metadata,
    upsert_vectors,
    verify_vectors,
)


@pytest.mark.integration
def test_upsert_and_verify_parity() -> None:
    client = _client()
    ids = ["ch_1", "ch_2"]
    metadatas = [
        locator_metadata("gen-1", "DM-0001", "fp-1", "decision.chosen", 0),
        locator_metadata("gen-1", "DM-0001", "fp-1", "why[0]", 0),
    ]
    embeddings = [[0.1] * 8, [0.2] * 8]
    upsert_vectors(client, ids, embeddings, metadatas)
    expected = dict(zip(ids, metadatas, strict=False))
    assert verify_vectors(client, ids, expected) == []


@pytest.mark.integration
def test_verify_detects_missing_vector_and_metadata_mismatch() -> None:
    client = _client()
    ids = ["ch_1"]
    metadatas = [locator_metadata("gen-1", "DM-0001", "fp-1", "decision.chosen", 0)]
    upsert_vectors(client, ids, [[0.1] * 8], metadatas)
    missing = verify_vectors(
        client,
        ["ch_1", "ch_missing"],
        {"ch_1": metadatas[0], "ch_missing": metadatas[0]},
    )
    assert any("missing" in problem for problem in missing)
    mismatch = verify_vectors(
        client,
        ["ch_1"],
        {"ch_1": locator_metadata("other", "DM-0001", "fp-1", "decision.chosen", 0)},
    )
    assert any("metadata mismatch" in problem for problem in mismatch)


@pytest.mark.integration
def test_valid_cosine_distance_bounds() -> None:
    assert is_valid_distance(0.0)
    assert is_valid_distance(1.0)
    assert is_valid_distance(2.0)
    assert not is_valid_distance(-0.5)
    assert not is_valid_distance(2.5)
