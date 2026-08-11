"""Live provider check for query 1 against real JobPilot (spec 0007 AC-11).

This is the behavior integration test the deterministic fake cannot replace.
It is marked integration and skipped unless both ``OPENAI_API_KEY`` and
``DECISION_MEMORY_JOBPILOT_DIR`` (a JobPilot checkout with ``docs/specs/``)
are set, so the default suites never touch the network.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from decision_memory.application.adapter import adapt_corpus
from decision_memory.application.dto import (
    IngestRequest,
    QueryFilters,
    QueryRequest,
    QueryState,
)
from decision_memory.application.ingest import IngestDependencies, ingest_records
from decision_memory.application.query import QueryDependencies, query_index
from decision_memory.infrastructure.bm25 import bm25_lexical_scorer
from decision_memory.infrastructure.file_reader import write_record_file
from decision_memory.infrastructure.index_reader import SqliteChromaIndexReader
from decision_memory.infrastructure.index_store import SqliteChromaIndexWriter
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter
from decision_memory.infrastructure.manifest_reader import (
    load_manifest,
    manifest_path,
    raw_manifest_digest,
    record_loader,
)
from decision_memory.infrastructure.openai_common import require_api_key
from decision_memory.infrastructure.openai_embeddings import embed_texts
from decision_memory.infrastructure.openai_generation import (
    coverage_verdict,
    entail_verdict,
    extract_facets,
    generate_answer,
)
from decision_memory.infrastructure.source_resolver import resolve_source_path
from decision_memory.infrastructure.tokenization import tiktoken_count

pytestmark = pytest.mark.integration

_REQUIRED = {"OPENAI_API_KEY", "DECISION_MEMORY_JOBPILOT_DIR"}


@pytest.mark.skipif(
    not _REQUIRED.issubset(os.environ),
    reason="requires OPENAI_API_KEY and DECISION_MEMORY_JOBPILOT_DIR",
)
def test_query_one_against_real_jobpilot(tmp_path) -> None:
    corpus = Path(os.environ["DECISION_MEMORY_JOBPILOT_DIR"])
    records_dir = tmp_path / "records"
    outcome = adapt_corpus(
        corpus, JsmasteryAdapter(), write_record_file, output=records_dir
    )
    assert outcome.exit_code == 0

    store_dir = tmp_path / "store"
    writer = SqliteChromaIndexWriter(store_dir)
    try:
        ingest_result = ingest_records(
            IngestRequest(
                records_dir=records_dir,
                store_dir=store_dir,
                rebuild=False,
                dry_run=False,
            ),
            IngestDependencies(
                load_manifest=lambda: load_manifest(manifest_path(records_dir)),
                read_record=record_loader(records_dir),
                count_tokens=tiktoken_count,
                embed=embed_texts,
                raw_manifest_digest=lambda: raw_manifest_digest(
                    manifest_path(records_dir)
                ),
                require_api_key=require_api_key,
                store=writer,
            ),
        )
    finally:
        writer.close()
    assert ingest_result.exit_code == 0, ingest_result

    reader = SqliteChromaIndexReader(store_dir)

    def _stored_manifest_path() -> Path | None:
        stored = reader.manifest_metadata()[0]
        return Path(stored) if stored else None

    def load_stored_manifest():
        path = _stored_manifest_path()
        if path is None:
            raise FileNotFoundError("no stored manifest path")
        return load_manifest(path)

    def stored_manifest_digest():
        path = _stored_manifest_path()
        if path is None:
            raise FileNotFoundError("no stored manifest path")
        return raw_manifest_digest(path)

    def _stored_hint() -> str | None:
        return reader.manifest_metadata()[3]

    result = query_index(
        QueryRequest(
            question=(
                "Why was the private beta access gate added, "
                "and what was the alternative?"
            ),
            store_dir=store_dir,
            allow_stale=False,
            filters=QueryFilters(),
        ),
        QueryDependencies(
            store=reader,
            count_tokens=tiktoken_count,
            embed=embed_texts,
            lexical_scorer=bm25_lexical_scorer,
            load_manifest=load_stored_manifest,
            raw_manifest_digest=stored_manifest_digest,
            resolve_source=lambda path: resolve_source_path(path, _stored_hint()),
            extract_facets=extract_facets,
            generate_answer=generate_answer,
            entail=entail_verdict,
            coverage=coverage_verdict,
        ),
    )
    assert result.state == QueryState.ANSWERED
    joined = " ".join(sentence.text for sentence in result.sentences).lower()
    # The answer explains the gate's purpose (protecting paid provider spend).
    assert any(keyword in joined for keyword in ("cost", "bill"))
    # The rejected alternative, the two agent routes only, is named.
    assert "two agent routes" in joined
    # The answer is cited to the DM-0012 record.
    assert any(citation.record_id == "DM-0012" for citation in result.citations)


@pytest.mark.skipif(
    not _REQUIRED.issubset(os.environ),
    reason="requires OPENAI_API_KEY and DECISION_MEMORY_JOBPILOT_DIR",
)
def test_live_smoke_query_two_and_query_four(tmp_path) -> None:
    """AC-15: five query 2 passes and five query 4 abstentions on one store.

    Five consecutive runs of each defining query are a smoke gate against the
    known intermittent verification pattern, not a measured reliability rate.
    One rebuilt format 2 store is reused for all ten runs.
    """
    corpus = Path(os.environ["DECISION_MEMORY_JOBPILOT_DIR"])
    records_dir = tmp_path / "records"
    outcome = adapt_corpus(
        corpus, JsmasteryAdapter(), write_record_file, output=records_dir
    )
    assert outcome.exit_code == 0

    store_dir = tmp_path / "store"
    writer = SqliteChromaIndexWriter(store_dir)
    try:
        ingest_result = ingest_records(
            IngestRequest(
                records_dir=records_dir,
                store_dir=store_dir,
                rebuild=True,
                dry_run=False,
            ),
            IngestDependencies(
                load_manifest=lambda: load_manifest(manifest_path(records_dir)),
                read_record=record_loader(records_dir),
                count_tokens=tiktoken_count,
                embed=embed_texts,
                raw_manifest_digest=lambda: raw_manifest_digest(
                    manifest_path(records_dir)
                ),
                require_api_key=require_api_key,
                store=writer,
            ),
        )
    finally:
        writer.close()
    assert ingest_result.exit_code == 0, ingest_result

    reader = SqliteChromaIndexReader(store_dir)

    def _stored_manifest_path() -> Path | None:
        stored = reader.manifest_metadata()[0]
        return Path(stored) if stored else None

    def load_stored_manifest():
        path = _stored_manifest_path()
        if path is None:
            raise FileNotFoundError("no stored manifest path")
        return load_manifest(path)

    def stored_manifest_digest():
        path = _stored_manifest_path()
        if path is None:
            raise FileNotFoundError("no stored manifest path")
        return raw_manifest_digest(path)

    def _stored_hint() -> str | None:
        return reader.manifest_metadata()[3]

    def deps() -> QueryDependencies:
        return QueryDependencies(
            store=reader,
            count_tokens=tiktoken_count,
            embed=embed_texts,
            lexical_scorer=bm25_lexical_scorer,
            load_manifest=load_stored_manifest,
            raw_manifest_digest=stored_manifest_digest,
            resolve_source=lambda path: resolve_source_path(path, _stored_hint()),
            extract_facets=extract_facets,
            generate_answer=generate_answer,
            entail=entail_verdict,
            coverage=coverage_verdict,
        )

    query_two = "What decisions affect resume generation?"
    for _ in range(5):
        result = query_index(
            QueryRequest(
                question=query_two,
                store_dir=store_dir,
                allow_stale=False,
                filters=QueryFilters(),
            ),
            deps(),
        )
        assert result.state == QueryState.ANSWERED
        cited = {citation.record_id for citation in result.citations}
        assert {"DM-0004", "DM-0014", "DM-0019"}.issubset(cited)

    query_four = (
        "What was decided about separating server side and browser side "
        "database clients, and why?"
    )
    for _ in range(5):
        result = query_index(
            QueryRequest(
                question=query_four,
                store_dir=store_dir,
                allow_stale=False,
                filters=QueryFilters(),
            ),
            deps(),
        )
        assert result.state == QueryState.ABSTAINED
        assert not result.sentences
        assert not result.citations
