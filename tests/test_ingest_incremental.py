"""Incremental, removal, rebuild, and spend preview tests (spec 0007 AC-7, AC-8).

``ingest_records`` is incremental: a second run embeds only new and changed
records, removes records absent from the manifest as content free tombstones,
and on a parity failed rebuild leaves the active generation untouched.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fake_index import FakeIndex, fake_embed
from spec_factory import INDEX, RATIONALE, make_corpus, write_spec

from decision_memory.application.adapter import adapt_corpus
from decision_memory.application.chunking import chunk_record, embedding_input
from decision_memory.application.dto import (
    IngestRequest,
    IngestState,
    RecordAction,
)
from decision_memory.application.ingest import IngestDependencies, ingest_records
from decision_memory.infrastructure.chroma_store import CHROMA_COLLECTION, _client
from decision_memory.infrastructure.file_reader import write_record_file
from decision_memory.infrastructure.index_lock import store_lock
from decision_memory.infrastructure.index_store import SqliteChromaIndexWriter
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter
from decision_memory.infrastructure.manifest_reader import (
    load_manifest,
    manifest_path,
    raw_manifest_digest,
    record_loader,
)
from decision_memory.infrastructure.store import generation_paths, read_active
from decision_memory.infrastructure.tokenization import tiktoken_count

INDEX_OTHER = INDEX.replace("0012", "0013").replace(
    "Portfolio private access gate", "Billing alert settings"
)


def _adapt(corpus: Path, specs: list[str], out: Path | None = None) -> Path:
    """Adapt the named specs into a records directory."""
    for spec in specs:
        if spec.startswith("0013"):
            write_spec(corpus, spec, index=INDEX_OTHER, rationale=RATIONALE)
        else:
            write_spec(corpus, spec)
    records_dir = out if out is not None else corpus / ".decision-memory" / "records"
    outcome = adapt_corpus(
        corpus, JsmasteryAdapter(), write_record_file, output=records_dir
    )
    assert outcome.exit_code == 0
    return records_dir


def _ingest_with(records_dir: Path, index: FakeIndex):
    calls: list[list[str]] = []

    def counting_embed(texts):
        calls.append(list(texts))
        return fake_embed(texts)

    result = ingest_records(
        IngestRequest(
            records_dir=records_dir,
            store_dir=Path("/fake/store"),
            rebuild=False,
            dry_run=False,
        ),
        IngestDependencies(
            load_manifest=lambda: load_manifest(manifest_path(records_dir)),
            read_record=record_loader(records_dir),
            count_tokens=tiktoken_count,
            embed=counting_embed,
            raw_manifest_digest=lambda: raw_manifest_digest(manifest_path(records_dir)),
            store=index,
        ),
    )
    return result, calls


def test_incremental_embeds_only_new_records(tmp_path) -> None:
    records_dir = _adapt(make_corpus(tmp_path), ["0012-portfolio"])
    index = FakeIndex()
    first, calls1 = _ingest_with(records_dir, index)
    assert [record.record_id for record in first.records] == ["DM-0012"]
    assert first.records[0].action == RecordAction.ADDED
    assert calls1

    # A second corpus adds DM-0013; DM-0012's source is byte identical.
    records2 = _adapt(
        make_corpus(tmp_path / "two"), ["0012-portfolio", "0013-portfolio"]
    )
    second, calls2 = _ingest_with(records2, index)
    actions = {record.record_id: record.action for record in second.records}
    assert actions["DM-0012"] == RecordAction.UNCHANGED
    assert actions["DM-0013"] == RecordAction.ADDED
    # Only DM-0013 was embedded; the unchanged record made no embedding call.
    joined = " ".join(" ".join(batch) for batch in calls2)
    assert "Billing alert settings" in joined
    assert "Portfolio private access gate" not in joined


def test_removed_record_becomes_a_tombstone(tmp_path) -> None:
    records_dir = _adapt(make_corpus(tmp_path), ["0012-portfolio"])
    index = FakeIndex()
    first, _ = _ingest_with(records_dir, index)
    assert first.exit_code == 0
    assert index.chunks

    # A new corpus drops DM-0012 and adds DM-0013 instead.
    records2 = _adapt(make_corpus(tmp_path / "two"), ["0013-portfolio"])
    second, _ = _ingest_with(records2, index)
    actions = {record.record_id: record.action for record in second.records}
    assert actions["DM-0012"] == RecordAction.REMOVED
    assert actions["DM-0013"] == RecordAction.ADDED
    assert index.record_states["DM-0012"][0] == "removed"
    assert index.record_states["DM-0013"][0] == "current"
    # The removed record owns no chunks and is no longer eligible.
    assert all(chunk.record_id != "DM-0012" for chunk in index.chunks.values())
    assert ("gen-fake", "DM-0012", first.records[0].desired_fingerprint) not in (
        index.eligible_tuples()
    )


def test_dry_run_counts_batches_without_writes(tmp_path) -> None:
    records_dir = _adapt(make_corpus(tmp_path), ["0012-portfolio"])
    index = FakeIndex()
    result = ingest_records(
        IngestRequest(
            records_dir=records_dir,
            store_dir=Path("/fake/store"),
            rebuild=False,
            dry_run=True,
        ),
        IngestDependencies(
            load_manifest=lambda: load_manifest(manifest_path(records_dir)),
            read_record=record_loader(records_dir),
            count_tokens=tiktoken_count,
            embed=fake_embed,
            raw_manifest_digest=lambda: raw_manifest_digest(manifest_path(records_dir)),
            store=index,
        ),
    )
    assert result.state == IngestState.COMPLETED
    assert result.exit_code == 0
    assert result.records[0].action == RecordAction.ADDED
    assert result.records[0].batch_count > 0
    assert result.provider_attempts == result.records[0].batch_count
    assert index.generation is None
    assert index.chunks == {}


@pytest.mark.integration
def test_real_ingest_under_exclusive_lock_succeeds(tmp_path) -> None:
    """The real writer must work inside the CLI's exclusive lock (AC-9).

    Regression: open_generation used to reopen the lock database while the
    exclusive lock was already held, which raised a database locked error that
    store_lock mislabeled as a lock conflict, so every real ingest exited 1
    with ``store is locked``.
    """
    records_dir = _adapt(make_corpus(tmp_path), ["0012-portfolio"])
    store = tmp_path / "store"
    writer = SqliteChromaIndexWriter(store)
    try:
        with store_lock(store, exclusive=True):
            result = ingest_records(
                IngestRequest(
                    records_dir=records_dir,
                    store_dir=store,
                    rebuild=False,
                    dry_run=False,
                ),
                IngestDependencies(
                    load_manifest=lambda: load_manifest(manifest_path(records_dir)),
                    read_record=record_loader(records_dir),
                    count_tokens=tiktoken_count,
                    embed=fake_embed,
                    raw_manifest_digest=lambda: raw_manifest_digest(
                        manifest_path(records_dir)
                    ),
                    store=writer,
                ),
            )
    finally:
        writer.close()
    assert result.state == IngestState.COMPLETED
    assert result.exit_code == 0
    assert result.records[0].action == RecordAction.ADDED


@pytest.mark.integration
def test_rebuild_failure_preserves_old_generation(tmp_path) -> None:
    """A parity failed rebuild leaves the previous active generation live."""
    records_dir = _adapt(make_corpus(tmp_path), ["0012-portfolio"])
    store = tmp_path / "store"
    # Phase 1: a normal ingest activates generation G1.
    writer = SqliteChromaIndexWriter(store)
    try:
        first = ingest_records(
            IngestRequest(
                records_dir=records_dir,
                store_dir=store,
                rebuild=False,
                dry_run=False,
            ),
            IngestDependencies(
                load_manifest=lambda: load_manifest(manifest_path(records_dir)),
                read_record=record_loader(records_dir),
                count_tokens=tiktoken_count,
                embed=fake_embed,
                raw_manifest_digest=lambda: raw_manifest_digest(
                    manifest_path(records_dir)
                ),
                store=writer,
            ),
        )
    finally:
        writer.close()
    assert first.exit_code == 0
    active_before = read_active(store)
    assert active_before is not None

    # Phase 2: a forced rebuild stages a fresh generation, writes the record,
    # then one of its vectors is deleted so the pre activation parity check
    # fails. The previous generation must remain active.
    writer2 = SqliteChromaIndexWriter(store)
    try:
        staging = writer2.open_generation(force_rebuild=True)
        assert staging != active_before
        manifest = load_manifest(manifest_path(records_dir))
        entry = manifest.entries[0]
        record = record_loader(records_dir)(entry.id)
        chunks = chunk_record(
            record,
            entry.field_sources,
            staging,
            entry.fingerprint,
            tiktoken_count,
        )
        inputs = [
            embedding_input(record.title or "", chunk.value_path, chunk.text)
            for chunk in chunks
        ]
        writer2.write_record(staging, record, chunks, fake_embed(inputs))
        _, _, chroma_dir = generation_paths(store, staging)
        collection = _client(chroma_dir).get_collection(CHROMA_COLLECTION)
        ids = (collection.get(include=[]) or {}).get("ids", [])
        assert ids
        collection.delete(ids=[ids[0]])
        problems = writer2.activate(staging)
        assert problems
    finally:
        writer2.close()
    # The previous generation is still the active one.
    assert read_active(store) == active_before
