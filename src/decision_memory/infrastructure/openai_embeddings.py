"""Infrastructure: the one module that calls the OpenAI embeddings SDK.

Spec 0007 AC-20 concentrates every embedding provider call here; no provider
class exists and application code receives narrow callables. Embedding
requests process one record at a time in batches capped at 64 chunks and
50,000 input tokens (AC-7). The model and dimensions come from the pipeline
signature constants, so a change forces an explicit rebuild.
"""

from __future__ import annotations

from collections.abc import Sequence

from decision_memory.application.dto import ProviderAttempt
from decision_memory.application.pipeline import (
    EMBEDDING_DIMENSIONS,
    EMBEDDING_MODEL,
)
from decision_memory.infrastructure.openai_common import (
    _client,
    require_api_key,
    run_with_retries,
)

# Per record batch caps (spec 0007 AC-7).
BATCH_CHUNK_CAP = 64
BATCH_TOKEN_CAP = 50_000


class EmbeddingError(Exception):
    """The embedding provider failed after retries or refused the request."""


def batch_limits() -> tuple[int, int]:
    """The fixed (chunk, input token) batch caps."""
    return BATCH_CHUNK_CAP, BATCH_TOKEN_CAP


def embed_texts(
    texts: Sequence[str],
    attempts: list[ProviderAttempt] | None = None,
) -> list[list[float]]:
    """Embed texts with the pipeline model, under the AC-16 retry policy.

    Returns one vector per input text. Provider attempts are appended to
    ``attempts`` when given, so the ingest trace keeps them after a failure.
    """
    require_api_key()
    client = _client()

    def call() -> list[list[float]]:
        response = client.embeddings.create(model=EMBEDDING_MODEL, input=list(texts))
        return [list(item.embedding) for item in response.data]

    try:
        return run_with_retries("embedding", call, attempts)
    except Exception as exc:  # noqa: BLE001 - normalized at the boundary
        raise EmbeddingError(str(exc)) from None


def embedding_dimensions() -> int:
    """The expected vector dimensions, from the pipeline signature."""
    return EMBEDDING_DIMENSIONS
