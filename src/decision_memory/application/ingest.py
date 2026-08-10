"""Application: the ingest use case (spec 0007 AC-3, AC-7, AC-8, AC-21).

``ingest_records`` is incremental by adapter fingerprint. It validates the
manifest schema, every entry and record digest, and complete required
provenance before any provider call for that record; added and changed records
are embedded one record at a time in bounded batches while unchanged records
make no embedding call. Record local validation or provider failure is
recorded in the ledger and later records continue. Records absent from the
manifest become ineligible before their vectors are deleted and finish as a
content free tombstone. ``--rebuild`` stages a fresh generation and switches
``ACTIVE`` only after complete parity. The lock protocol is enforced by the
composition root around this function.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from decision_memory.application.adapter import (
    EXIT_ERROR,
    EXIT_OK,
    Manifest,
    ManifestEntry,
    semantic_manifest_digest,
)
from decision_memory.application.canonical import entry_digest, record_digest
from decision_memory.application.chunking import (
    ChunkingError,
    chunk_record,
    embedding_input,
    missing_provenance,
)
from decision_memory.application.dto import (
    ChunkPlan,
    Failure,
    IngestRequest,
    IngestResult,
    IngestState,
    RecordAction,
    RecordIngestResult,
)
from decision_memory.domain.records import CanonicalDecisionRecord

EXIT_CORPUS_INVALID = 3

BATCH_CHUNK_CAP = 64
BATCH_TOKEN_CAP = 50_000

# The fixed manifest filename inside a records directory (spec 0003 AC-25).
MANIFEST_FILENAME = "manifest.json"

STATE_CURRENT = "current"
STATE_REMOVED = "removed"


class IndexWriter(Protocol):
    """The write side of the store, implemented in infrastructure."""

    def open_generation(self, force_rebuild: bool) -> str: ...
    def existing_states(self) -> dict[str, tuple[str, str | None, str | None]]: ...
    def write_record(
        self,
        generation_id: str,
        record: CanonicalDecisionRecord,
        chunks: Sequence[ChunkPlan],
        embeddings: Sequence[Sequence[float]],
    ) -> list[str]: ...
    def mark_pending_removal(self, record_id: str) -> None: ...
    def mark_failed(
        self,
        record_id: str,
        desired_fingerprint: str,
        active_fingerprint: str | None,
        failure_code: str,
    ) -> None: ...
    def remove_record(
        self, generation_id: str, record_id: str, prior_fingerprint: str | None
    ) -> None: ...
    def delete_vectors(self, chunk_ids: Sequence[str]) -> None: ...
    def cleanup_orphans(self, generation_id: str) -> None: ...
    def set_manifest_metadata(
        self,
        records_manifest_path: str,
        semantic_digest: str,
        raw_digest: str,
        source_root_hint: str,
    ) -> None: ...
    def activate(self, generation_id: str) -> list[str]: ...


@dataclass(frozen=True)
class IngestDependencies:
    """Every concern ingest needs, injected at the composition root."""

    load_manifest: Callable[[], Manifest]
    read_record: Callable[[str], CanonicalDecisionRecord]
    count_tokens: Callable[[str], int]
    embed: Callable[[Sequence[str]], list[list[float]]]
    raw_manifest_digest: Callable[[], str]
    require_api_key: Callable[[], None]
    store: IndexWriter


def ingest_records(request: IngestRequest, deps: IngestDependencies) -> IngestResult:
    """Ingest the records directory into the store and return the outcome.

    Every expected failure is returned as an ``IngestResult`` with the fixed
    exit code; only programming errors raise past this boundary.
    """
    if not request.records_dir.is_dir():
        return _result(EXIT_CORPUS_INVALID, IngestState.FAILED, (), None)
    try:
        manifest = deps.load_manifest()
    except Exception:  # noqa: BLE001 - malformed manifest is a returned result
        return _result(
            EXIT_ERROR,
            IngestState.FAILED,
            (),
            Failure("manifest.invalid", "manifest", "manifest could not be read"),
        )
    if request.dry_run:
        return _dry_run(request, deps, manifest)
    return _run_ingest(request, deps, manifest)


def _run_ingest(
    request: IngestRequest, deps: IngestDependencies, manifest: Manifest
) -> IngestResult:
    """The real incremental run: compare, embed changed, remove absent.

    The plan is read first, so the API key is validated after read only
    planning and before any store mutation (AC-20): a run whose completed
    plan includes an embedding call refuses without a key and leaves the
    store untouched. Unchanged, removal only, and dry runs never call the key
    check.
    """
    states = deps.store.existing_states() if not request.rebuild else {}
    if _plan_needs_provider(manifest, states, request.rebuild):
        try:
            deps.require_api_key()
        except Exception as exc:  # noqa: BLE001 - a missing key is a returned result
            detail = str(exc).strip() or "OPENAI_API_KEY is not set"
            return _result(
                EXIT_ERROR,
                IngestState.FAILED,
                (),
                Failure("provider.key", "planning", detail),
            )
    generation_id = deps.store.open_generation(request.rebuild)
    results: list[RecordIngestResult] = []
    old_vectors: list[list[str]] = []
    for entry in sorted(manifest.entries, key=lambda item: item.id):
        result, old_ids = _ingest_entry(
            request, deps, generation_id, entry, states.get(entry.id)
        )
        results.append(result)
        old_vectors.append(old_ids)

    manifest_ids = {entry.id for entry in manifest.entries}
    for record_id, (state, _desired, active) in states.items():
        if record_id in manifest_ids or state == STATE_REMOVED:
            continue
        deps.store.mark_pending_removal(record_id)
        deps.store.remove_record(generation_id, record_id, active)
        results.append(
            RecordIngestResult(
                record_id=record_id,
                action=RecordAction.REMOVED,
                state="removed",
                desired_fingerprint="",
                active_fingerprint=None,
                chunks=(),
                batch_count=0,
                failure_code=None,
            )
        )

    deps.store.cleanup_orphans(generation_id)
    problems = deps.store.activate(generation_id)
    if problems:
        return _result(
            EXIT_ERROR,
            IngestState.FAILED,
            tuple(results),
            Failure("store.parity", "store", "; ".join(problems)),
        )
    deps.store.set_manifest_metadata(
        records_manifest_path=str((request.records_dir / MANIFEST_FILENAME).resolve()),
        semantic_digest=semantic_manifest_digest(manifest),
        raw_digest=deps.raw_manifest_digest(),
        source_root_hint=manifest.source_root_hint,
    )
    for old_ids in old_vectors:
        deps.store.delete_vectors(old_ids)

    failed = any(result.action == RecordAction.FAILED for result in results)
    state = IngestState.PARTIAL if failed else IngestState.COMPLETED
    return _result(EXIT_ERROR if failed else EXIT_OK, state, tuple(results), None)


def _plan_needs_provider(
    manifest: Manifest,
    states: dict[str, tuple[str, str | None, str | None]],
    rebuild: bool,
) -> bool:
    """True when the completed plan includes at least one embedding call (AC-20)."""
    if not manifest.entries:
        return False
    if rebuild:
        return True
    for entry in manifest.entries:
        existing = states.get(entry.id)
        if not (
            existing is not None
            and existing[0] == STATE_CURRENT
            and existing[2] == entry.fingerprint
        ):
            return True
    return False


def _ingest_entry(
    request: IngestRequest,
    deps: IngestDependencies,
    generation_id: str,
    entry: ManifestEntry,
    existing: tuple[str, str | None, str | None] | None,
) -> tuple[RecordIngestResult, list[str]]:
    """Ingest one manifest entry, returning its result and old chunk ids."""
    if (
        existing is not None
        and existing[0] == STATE_CURRENT
        and existing[2] == entry.fingerprint
    ):
        return _unchanged_entry(deps, entry), []

    try:
        record = deps.read_record(entry.id)
    except Exception:  # noqa: BLE001 - a failed record continues the run
        return _failed(deps, entry, existing, "record.unreadable"), []
    if record_digest(record) != entry.record_digest:
        return _failed(deps, entry, existing, "digest.record_mismatch"), []
    recomputed = entry_digest(
        record_id=entry.id,
        fingerprint=entry.fingerprint,
        contributing_files=entry.contributing_files,
        record_path=entry.record_path,
        record_digest_value=entry.record_digest,
        field_sources=entry.field_sources,
    )
    if recomputed != entry.entry_digest:
        return _failed(deps, entry, existing, "digest.entry_mismatch"), []
    missing = missing_provenance(record, entry.field_sources)
    if missing:
        return _failed(deps, entry, existing, "provenance.missing"), []
    try:
        chunks = chunk_record(
            record,
            entry.field_sources,
            generation_id,
            entry.fingerprint,
            deps.count_tokens,
        )
    except ChunkingError:
        return _failed(deps, entry, existing, "chunking.oversize"), []
    title = record.title or ""
    inputs = [embedding_input(title, chunk.value_path, chunk.text) for chunk in chunks]
    try:
        vectors = _embed_in_batches(inputs, deps)
    except Exception:  # noqa: BLE001 - provider failure is a failed record
        return _failed(deps, entry, existing, "provider.embedding"), []
    old_ids = deps.store.write_record(generation_id, record, chunks, vectors)
    action = (
        RecordAction.UPDATED
        if existing is not None and existing[2] is not None
        else RecordAction.ADDED
    )
    result = RecordIngestResult(
        record_id=entry.id,
        action=action,
        state="current",
        desired_fingerprint=entry.fingerprint,
        active_fingerprint=entry.fingerprint,
        chunks=tuple(chunks),
        batch_count=_batch_count(inputs, deps.count_tokens),
        failure_code=None,
    )
    return result, old_ids


def _unchanged_entry(
    deps: IngestDependencies, entry: ManifestEntry
) -> RecordIngestResult:
    """A current record makes no embedding call; validate only (AC-7)."""
    try:
        record = deps.read_record(entry.id)
    except Exception:  # noqa: BLE001 - a failed record continues the run
        deps.store.mark_failed(
            entry.id, entry.fingerprint, entry.fingerprint, "record.unreadable"
        )
        return _failed_result(entry.id, "record.unreadable")
    if record_digest(record) != entry.record_digest:
        deps.store.mark_failed(
            entry.id, entry.fingerprint, entry.fingerprint, "digest.record_mismatch"
        )
        return _failed_result(entry.id, "digest.record_mismatch")
    if missing_provenance(record, entry.field_sources):
        deps.store.mark_failed(
            entry.id, entry.fingerprint, entry.fingerprint, "provenance.missing"
        )
        return _failed_result(entry.id, "provenance.missing")
    return RecordIngestResult(
        record_id=entry.id,
        action=RecordAction.UNCHANGED,
        state="current",
        desired_fingerprint=entry.fingerprint,
        active_fingerprint=entry.fingerprint,
        chunks=(),
        batch_count=0,
        failure_code=None,
    )


def _failed(
    deps: IngestDependencies,
    entry: ManifestEntry,
    existing: tuple[str, str | None, str | None] | None,
    failure_code: str,
) -> RecordIngestResult:
    """Record a failed addition or update, keeping any prior version."""
    prior = existing[2] if existing is not None else None
    deps.store.mark_failed(entry.id, entry.fingerprint, prior, failure_code)
    return _failed_result(entry.id, failure_code)


def _failed_result(record_id: str, failure_code: str) -> RecordIngestResult:
    return RecordIngestResult(
        record_id=record_id,
        action=RecordAction.FAILED,
        state="failed",
        desired_fingerprint="",
        active_fingerprint=None,
        chunks=(),
        batch_count=0,
        failure_code=failure_code,
    )


def _dry_run(
    request: IngestRequest, deps: IngestDependencies, manifest: Manifest
) -> IngestResult:
    """Preview spend: no provider call, no store mutation, no API key."""
    results: list[RecordIngestResult] = []
    for entry in sorted(manifest.entries, key=lambda item: item.id):
        results.append(_dry_run_entry(deps, entry))
    failed = any(result.action == RecordAction.FAILED for result in results)
    state = IngestState.PARTIAL if failed else IngestState.COMPLETED
    return _result(EXIT_ERROR if failed else EXIT_OK, state, tuple(results), None)


def _dry_run_entry(
    deps: IngestDependencies, entry: ManifestEntry
) -> RecordIngestResult:
    """One record's preview: validate, chunk, and count tokens and batches."""
    try:
        record = deps.read_record(entry.id)
    except Exception:  # noqa: BLE001 - a failed record continues the run
        return _failed_result(entry.id, "record.unreadable")
    if record_digest(record) != entry.record_digest:
        return _failed_result(entry.id, "digest.record_mismatch")
    recomputed = entry_digest(
        record_id=entry.id,
        fingerprint=entry.fingerprint,
        contributing_files=entry.contributing_files,
        record_path=entry.record_path,
        record_digest_value=entry.record_digest,
        field_sources=entry.field_sources,
    )
    if recomputed != entry.entry_digest:
        return _failed_result(entry.id, "digest.entry_mismatch")
    missing = missing_provenance(record, entry.field_sources)
    if missing:
        return _failed_result(entry.id, "provenance.missing")
    try:
        chunks = chunk_record(
            record,
            entry.field_sources,
            "dry-run",
            entry.fingerprint,
            deps.count_tokens,
        )
    except ChunkingError:
        return _failed_result(entry.id, "chunking.oversize")
    title = record.title or ""
    inputs = [embedding_input(title, chunk.value_path, chunk.text) for chunk in chunks]
    return RecordIngestResult(
        record_id=entry.id,
        action=RecordAction.ADDED,
        state="current",
        desired_fingerprint=entry.fingerprint,
        active_fingerprint=None,
        chunks=tuple(chunks),
        batch_count=_batch_count(inputs, deps.count_tokens),
        failure_code=None,
    )


def _embed_in_batches(
    inputs: Sequence[str], deps: IngestDependencies
) -> list[list[float]]:
    """Embed one record's inputs in bounded batches (AC-7 caps)."""
    vectors: list[list[float]] = []
    batch: list[str] = []
    batch_tokens = 0
    for text in inputs:
        tokens = deps.count_tokens(text)
        if batch and (
            len(batch) >= BATCH_CHUNK_CAP or batch_tokens + tokens > BATCH_TOKEN_CAP
        ):
            vectors.extend(deps.embed(batch))
            batch = []
            batch_tokens = 0
        batch.append(text)
        batch_tokens += tokens
    if batch:
        vectors.extend(deps.embed(batch))
    return vectors


def _batch_count(inputs: Sequence[str], count_tokens: Callable[[str], int]) -> int:
    """The number of batches the caps produce, matching ``_embed_in_batches``."""
    count = 0
    batch_size = 0
    batch_tokens = 0
    for text in inputs:
        tokens = count_tokens(text)
        if batch_size and (
            batch_size >= BATCH_CHUNK_CAP or batch_tokens + tokens > BATCH_TOKEN_CAP
        ):
            count += 1
            batch_size = 0
            batch_tokens = 0
        batch_size += 1
        batch_tokens += tokens
    if batch_size:
        count += 1
    return count


def _result(
    exit_code: int,
    state: IngestState,
    records: tuple[RecordIngestResult, ...],
    failure: Failure | None,
) -> IngestResult:
    return IngestResult(
        schema_version=1,
        state=state,
        exit_code=exit_code,
        store_path=Path("/unset"),
        semantic_manifest_digest=None,
        raw_manifest_digest=None,
        records=records,
        provider_attempts=sum(record.batch_count for record in records),
        failure=failure,
    )
