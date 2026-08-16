"""The shipped bundle answers and abstains as its snapshot says (spec 0014).

AC-10 and AC-2. Asks the pinned questions straight against the committed
bundle, exactly as a reader would on a fresh clone: no adapt, no ingest, and
no ``--allow-stale``. The questions come from the bundle's own
``snapshot.json`` rather than being repeated here, so the snapshot, the
regeneration script, and this test cannot drift apart.

Marked integration: it calls the real providers, because ``query`` embeds the
question and there is no key free path. Skipped without a key, and skipped
when the bundle is absent.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from decision_memory.application.dto import (
    FreshnessState,
    QueryFilters,
    QueryRequest,
    QueryResult,
    QueryState,
    ResolutionState,
)
from decision_memory.application.query import QueryDependencies, query_index
from decision_memory.infrastructure.bm25 import bm25_lexical_scorer
from decision_memory.infrastructure.bundle_snapshot import read_snapshot
from decision_memory.infrastructure.index_reader import SqliteChromaIndexReader
from decision_memory.infrastructure.openai_embeddings import embed_texts
from decision_memory.infrastructure.openai_generation import (
    coverage_verdict,
    decompose_sentence,
    entail_verdict,
    extract_facets,
    generate_answer,
)
from decision_memory.infrastructure.store_resolution import store_resolution
from decision_memory.infrastructure.tokenization import tiktoken_count

pytestmark = pytest.mark.integration

REPO_ROOT = Path(__file__).resolve().parent.parent
BUNDLE = REPO_ROOT / "examples" / "self-index"
STORE_DIR = BUNDLE / "query-index"


def _require_bundle_and_key() -> None:
    if not STORE_DIR.is_dir():
        pytest.skip("the self index bundle is not present in this checkout")
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not set; query embeds the question")


def _pinned(expected: str) -> str:
    snapshot = read_snapshot(BUNDLE)
    assert snapshot is not None, "the committed snapshot.json is missing or invalid"
    for question in snapshot.demo_questions:
        if question.expected == expected:
            return question.question
    pytest.skip(f"the snapshot pins no {expected!r} question")


def _ask(question: str) -> QueryResult:
    """Ask against the committed bundle the way a reader does, no flags."""
    reader = SqliteChromaIndexReader(STORE_DIR)
    resolution = store_resolution(reader.manifest_metadata)
    return query_index(
        QueryRequest(
            question=question,
            store_dir=STORE_DIR,
            allow_stale=False,
            filters=QueryFilters(),
        ),
        QueryDependencies(
            store=reader,
            count_tokens=tiktoken_count,
            embed=embed_texts,
            lexical_scorer=bm25_lexical_scorer,
            load_manifest=resolution.load_manifest,
            raw_manifest_digest=resolution.raw_manifest_digest,
            resolve_source=resolution.resolve_source,
            extract_facets=extract_facets,
            generate_answer=generate_answer,
            decompose=decompose_sentence,
            entail=entail_verdict,
            coverage=coverage_verdict,
        ),
    )


def test_the_pinned_question_answers_with_resolving_citations() -> None:
    """AC-2 and AC-10: a cited answer with no corpus setup and no stale flag."""
    _require_bundle_and_key()
    result = _ask(_pinned("answered"))

    assert result.freshness == FreshnessState.CURRENT
    assert result.state == QueryState.ANSWERED
    assert result.citations
    for citation in result.citations:
        assert citation.resolution is ResolutionState.RESOLVED, (
            f"{citation.source_path} resolved {citation.resolution.value}; a "
            "reader cannot open the source to check the claim"
        )
        assert (REPO_ROOT / citation.source_path).is_file()


def test_the_pinned_out_of_corpus_question_abstains() -> None:
    """AC-10: the honest no evidence response, not an invented answer."""
    _require_bundle_and_key()
    result = _ask(_pinned("abstained"))

    assert result.freshness == FreshnessState.CURRENT
    assert result.state == QueryState.ABSTAINED
    assert not result.citations


def test_the_bundle_reads_current_without_allow_stale() -> None:
    """AC-2: freshness resolves on the real manifest, not on the missing path."""
    _require_bundle_and_key()
    reader = SqliteChromaIndexReader(STORE_DIR)
    resolved_manifest = reader.manifest_metadata()[0]
    assert resolved_manifest is not None
    assert Path(resolved_manifest).is_file()
