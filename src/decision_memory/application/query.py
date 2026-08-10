"""Application: the query use case (spec 0007 AC-12, AC-15, AC-16).

``query_index`` reads only the local store. It verifies the pipeline
signature and SQLite to Chroma parity, retrieves up to 24 cosine candidates
against the SQLite supplied eligibility filter, accepts the first eight under
the disabled null floor, extracts facets independently, generates structured
answer sentences, verifies them by deterministic containment or model
entailment, checks coverage, and returns a cited answer or an honest
abstention. Provider, schema, lock, manifest, and store failures are never
abstention. The application receives every provider and store concern as a
narrow callable or protocol (AC-20).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from decision_memory.application.adapter import Manifest, semantic_manifest_digest
from decision_memory.application.canonical import SourceReference
from decision_memory.application.dto import (
    AbstentionStage,
    AnswerSentence,
    Candidate,
    CandidateDisposition,
    Citation,
    CitationFreshness,
    CitationKind,
    CoverageRow,
    DraftSentence,
    Facet,
    Failure,
    FreshnessState,
    FreshnessTrace,
    GenerationTrace,
    ProviderAttempt,
    QueryRequest,
    QueryResult,
    QueryState,
    QueryTrace,
    ResolutionState,
    ResultTrace,
    RetrievalTrace,
    StaleReason,
    SupersessionNotice,
    VerificationTrace,
)
from decision_memory.application.pipeline import (
    MODEL_TOKEN_LIMIT,
    pipeline_signature,
)
from decision_memory.application.verification import deterministic_containment
from decision_memory.infrastructure.chroma_store import is_valid_distance

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

CANDIDATE_LIMIT = 24
ACCEPTED_LIMIT = 8


@dataclass(frozen=True)
class RetrievedChunk:
    """A stored chunk with its record metadata, for generation and citation."""

    chunk_id: str
    record_id: str
    value_path: str
    fingerprint: str
    ordinal: int
    text: str
    sources: tuple[SourceReference, ...]
    record_title: str
    record_status: str | None


class IndexReader(Protocol):
    """The read side of the store, implemented in infrastructure."""

    def pipeline_signature(self) -> str: ...
    def generation_id(self) -> str | None: ...
    def parity_problems(self) -> list[str]: ...
    def eligible_tuples(self) -> tuple[tuple[str, str, str], ...]: ...
    def manifest_metadata(
        self,
    ) -> tuple[str | None, str | None, str | None, str | None]: ...
    def ledger_fingerprints(self) -> dict[str, str | None]: ...
    def has_failed_records(self) -> bool: ...
    def active_fingerprint(self, record_id: str) -> str | None: ...
    def search(
        self,
        embedding: Sequence[float],
        eligible: Sequence[tuple[str, str, str]],
        limit: int = CANDIDATE_LIMIT,
    ) -> list[tuple[str, float]]: ...
    def chunk(self, chunk_id: str) -> RetrievedChunk | None: ...


@dataclass(frozen=True)
class QueryDependencies:
    """Every concern query needs, injected at the composition root."""

    store: IndexReader
    count_tokens: Callable[[str], int]
    embed: Callable[[Sequence[str]], list[list[float]]]
    load_manifest: Callable[[], Manifest]
    raw_manifest_digest: Callable[[], str]
    extract_facets: Callable[[str, list[ProviderAttempt] | None], tuple[Facet, ...]]
    generate_answer: Callable[
        [
            Sequence[Facet],
            Sequence[str],
            Sequence[SupersessionNotice],
            frozenset[str],
            list[ProviderAttempt] | None,
        ],
        tuple[DraftSentence, ...],
    ]
    entail: Callable[
        [str, Sequence[str], list[ProviderAttempt] | None], tuple[bool, str]
    ]
    coverage: Callable[
        [
            str,
            Sequence[Facet],
            Sequence[DraftSentence],
            list[ProviderAttempt] | None,
        ],
        tuple[CoverageRow, ...],
    ]


def _empty_retrieval(
    question: str, eligible: tuple[tuple[str, str, str], ...]
) -> RetrievalTrace:
    return RetrievalTrace(
        question=question,
        filters=("none",),
        eligibility=eligible,
        candidate_limit=CANDIDATE_LIMIT,
        accepted_limit=ACCEPTED_LIMIT,
        relevance_floor=None,
        candidates=(),
    )


def _empty_generation() -> GenerationTrace:
    return GenerationTrace(
        facets=(),
        supersession_notices=(),
        draft_sentences=(),
        cited_chunk_ids=(),
    )


def _empty_verification() -> VerificationTrace:
    return VerificationTrace(
        containment=(),
        entailment=(),
        removed_sentences=(),
        coverage=(),
        uncovered_facets=(),
    )


def query_index(request: QueryRequest, deps: QueryDependencies) -> QueryResult:
    """Run one query and return the full traced result.

    Every expected failure is returned as a ``QueryResult`` with a failure and
    the fixed exit code; only programming errors raise past this boundary.
    """
    attempts: list[ProviderAttempt] = []
    question = request.question

    if not question.strip():
        return _failed_result(
            request,
            _freshness_trace(deps, None, None),
            Failure("usage.empty_question", "usage", "question is empty"),
            EXIT_USAGE,
        )

    if deps.store.generation_id() is None:
        return _failed_result(
            request,
            _freshness_trace(deps, None, None),
            Failure(
                "store.uninitialized",
                "store",
                "store is missing an active generation (corrupt initialized "
                "state); run ingest or rebuild",
            ),
            EXIT_ERROR,
        )

    running_signature = pipeline_signature()
    stored_signature = deps.store.pipeline_signature()
    manifest_path, stored_semantic, stored_raw, _hint = deps.store.manifest_metadata()
    freshness_state, stale_reasons = _manifest_freshness(
        deps, manifest_path, stored_semantic
    )
    freshness = _freshness_trace(
        deps,
        stored_signature,
        running_signature,
        state=freshness_state,
        stale_reasons=stale_reasons,
        manifest_path=manifest_path,
    )
    if stored_signature != running_signature:
        return _failed_result(
            request,
            _with_freshness(freshness, FreshnessState.INCOMPATIBLE),
            Failure(
                "pipeline.incompatible",
                "pipeline",
                "index was built with a different pipeline signature",
            ),
            EXIT_ERROR,
        )
    if freshness_state in (FreshnessState.DRIFT, FreshnessState.UNKNOWN) and not (
        request.allow_stale
    ):
        return _failed_result(
            request,
            freshness,
            Failure(
                "stale.refused",
                "freshness",
                "index is stale; use --allow-stale to read it",
            ),
            EXIT_ERROR,
        )

    eligible = deps.store.eligible_tuples()
    retrieval = _empty_retrieval(question, eligible)
    if not eligible:
        return _abstained_result(
            request, freshness, retrieval, AbstentionStage.RETRIEVAL
        )

    if deps.count_tokens(question) > MODEL_TOKEN_LIMIT:
        return _failed_result(
            request,
            freshness,
            Failure(
                "usage.overlimit_question",
                "usage",
                "question exceeds the model token limit",
            ),
            EXIT_USAGE,
        )

    parity = deps.store.parity_problems()
    if parity:
        return _failed_result(
            request,
            freshness,
            Failure("store.parity", "store", "; ".join(parity)),
            EXIT_ERROR,
        )

    # Embed the question and retrieve.
    try:
        question_vector = deps.embed([question])[0]
    except Exception as exc:  # noqa: BLE001 - provider failure is a result
        return _failed_result(
            request,
            freshness,
            Failure("provider.embedding", "embedding", _safe(exc)),
            EXIT_ERROR,
        )
    try:
        raw = deps.store.search(question_vector, eligible)
    except Exception as exc:  # noqa: BLE001 - store failure is a result
        return _failed_result(
            request,
            freshness,
            Failure("store.retrieval", "retrieval", _safe(exc)),
            EXIT_ERROR,
        )

    candidates: list[Candidate] = []
    accepted: list[RetrievedChunk] = []
    for rank, (chunk_id, distance) in enumerate(raw, start=1):
        if not is_valid_distance(distance):
            return _failed_result(
                request,
                freshness,
                Failure(
                    "store.distance",
                    "retrieval",
                    f"invalid distance for {chunk_id}",
                ),
                EXIT_ERROR,
            )
        chunk = deps.store.chunk(chunk_id)
        if chunk is None:
            return _failed_result(
                request,
                freshness,
                Failure(
                    "store.chunk_missing",
                    "retrieval",
                    f"missing chunk {chunk_id}",
                ),
                EXIT_ERROR,
            )
        disposition = (
            CandidateDisposition.ACCEPTED
            if rank <= ACCEPTED_LIMIT
            else CandidateDisposition.OUTSIDE_TOP_8
        )
        candidates.append(
            Candidate(
                chunk_id=chunk_id,
                record_id=chunk.record_id,
                value_path=chunk.value_path,
                fingerprint=chunk.fingerprint,
                ordinal=chunk.ordinal,
                distance=distance,
                similarity=1.0 - distance,
                rank=rank,
                disposition=disposition,
                text=chunk.text,
                provenance=chunk.sources,
            )
        )
        if disposition == CandidateDisposition.ACCEPTED:
            accepted.append(chunk)

    retrieval = RetrievalTrace(
        question=question,
        filters=("none",),
        eligibility=eligible,
        candidate_limit=CANDIDATE_LIMIT,
        accepted_limit=ACCEPTED_LIMIT,
        relevance_floor=None,
        candidates=tuple(candidates),
    )

    generation = _empty_generation()
    verification = _empty_verification()
    try:
        facets = deps.extract_facets(question, attempts)
    except Exception as exc:  # noqa: BLE001 - provider failure is a result
        return _failed_result(
            request,
            freshness,
            Failure("provider.facets", "generation", _safe(exc)),
            EXIT_ERROR,
        )
    generation = GenerationTrace(
        facets=facets,
        supersession_notices=(),
        draft_sentences=(),
        cited_chunk_ids=(),
    )

    accepted_texts = [chunk.text for chunk in accepted]
    known_ids = frozenset(chunk.chunk_id for chunk in accepted)
    try:
        draft = deps.generate_answer(facets, accepted_texts, (), known_ids, attempts)
    except Exception as exc:  # noqa: BLE001 - provider failure is a result
        return _failed_result(
            request,
            freshness,
            Failure("provider.answer", "generation", _safe(exc)),
            EXIT_ERROR,
        )
    generation = GenerationTrace(
        facets=facets,
        supersession_notices=(),
        draft_sentences=draft,
        cited_chunk_ids=tuple(sorted(known_ids)),
    )

    # Verify each sentence: deterministic containment first, then entailment.
    kept: list[DraftSentence] = []
    containment_rows: list[tuple[str, bool]] = []
    entailment_rows: list[tuple[str, str, str]] = []
    removed: list[str] = []
    chunk_text_by_id = {chunk.chunk_id: chunk.text for chunk in accepted}
    for sentence in draft:
        cited_texts = [
            chunk_text_by_id[chunk_id]
            for chunk_id in sentence.chunk_ids
            if chunk_id in chunk_text_by_id
        ]
        contained = deterministic_containment(sentence.text, cited_texts)
        containment_rows.append((sentence.sentence_id, contained))
        if contained:
            kept.append(sentence)
            continue
        try:
            supported, reason = deps.entail(sentence.text, cited_texts, attempts)
        except Exception as exc:  # noqa: BLE001 - provider failure is a result
            return _failed_result(
                request,
                freshness,
                Failure("provider.entailment", "claim_verification", _safe(exc)),
                EXIT_ERROR,
            )
        entailment_rows.append(
            (
                sentence.sentence_id,
                "supported" if supported else "unsupported",
                reason,
            )
        )
        if supported:
            kept.append(sentence)
        else:
            removed.append(sentence.sentence_id)

    # Independent coverage over the original question, facets, and kept sentences.
    try:
        coverage_rows = deps.coverage(question, facets, kept, attempts)
    except Exception as exc:  # noqa: BLE001 - provider failure is a result
        return _failed_result(
            request,
            freshness,
            Failure("provider.coverage", "claim_verification", _safe(exc)),
            EXIT_ERROR,
        )
    uncovered = tuple(
        facet
        for facet, row in zip(facets, coverage_rows, strict=False)
        if not row.covered
    )
    verification = VerificationTrace(
        containment=tuple(containment_rows),
        entailment=tuple(entailment_rows),
        removed_sentences=tuple(removed),
        coverage=coverage_rows,
        uncovered_facets=uncovered,
    )
    if uncovered:
        return _abstained_result(
            request,
            freshness,
            retrieval,
            AbstentionStage.CLAIM_VERIFICATION,
            generation=generation,
            verification=verification,
        )

    # Build citations by first sentence use, deduplicated by source location.
    chunk_by_id = {chunk.chunk_id: chunk for chunk in accepted}
    stale_record_ids = frozenset(
        record_id
        for record_id, desired in deps.store.ledger_fingerprints().items()
        if desired is not None and deps.store.active_fingerprint(record_id) != desired
    )
    citations, sentence_citation_ids = _allocate_citations(
        kept, chunk_by_id, stale_record_ids
    )
    answer_sentences = tuple(
        AnswerSentence(
            sentence_id=sentence.sentence_id,
            text=sentence.text,
            citation_ids=sentence_citation_ids.get(sentence.sentence_id, ()),
        )
        for sentence in kept
    )

    # Recheck the raw manifest bytes before returning (AC-9).
    if manifest_path is not None:
        try:
            raw_changed = deps.raw_manifest_digest() != stored_raw
        except Exception:  # noqa: BLE001 - an unreadable manifest counts as a change
            raw_changed = True
        if raw_changed:
            freshness = _with_stale_reason(
                freshness, StaleReason.MANIFEST_CHANGED_DURING_QUERY
            )
            if not request.allow_stale:
                return _failed_result(
                    request,
                    freshness,
                    Failure(
                        "stale.refused",
                        "freshness",
                        "manifest changed during query; use --allow-stale to read it",
                    ),
                    EXIT_ERROR,
                )

    result_trace = ResultTrace(
        state=QueryState.ANSWERED,
        abstention_stage=None,
        citations=tuple(citation.citation_id for citation in citations),
        stale_markers=(),
    )
    trace = QueryTrace(
        freshness=freshness,
        retrieval=retrieval,
        generation=generation,
        verification=verification,
        providers=tuple(attempts),
        result=result_trace,
    )
    return QueryResult(
        schema_version=1,
        state=QueryState.ANSWERED,
        exit_code=EXIT_OK,
        sentences=answer_sentences,
        citations=citations,
        freshness=freshness.state,
        abstention_stage=None,
        trace=trace,
        failure=None,
    )


def _allocate_citations(
    sentences: Sequence[DraftSentence],
    chunk_by_id: dict[str, RetrievedChunk],
    stale_record_ids: frozenset[str] = frozenset(),
) -> tuple[tuple[Citation, ...], dict[str, tuple[str, ...]]]:
    """Allocate C1.. by first sentence use, deduplicating by source location."""
    citations: list[Citation] = []
    seen: dict[tuple[str, str, str, str], str] = {}
    sentence_ids: dict[str, tuple[str, ...]] = {}
    for sentence in sentences:
        ids: list[str] = []
        for chunk_id in sentence.chunk_ids:
            chunk = chunk_by_id.get(chunk_id)
            if chunk is None:
                continue
            for source in chunk.sources:
                key = (CitationKind.CHUNK.value, chunk_id, source.path, source.section)
                existing = seen.get(key)
                if existing is not None:
                    ids.append(existing)
                    continue
                citation_id = f"C{len(citations) + 1}"
                seen[key] = citation_id
                freshness = (
                    CitationFreshness.STALE_VERSION
                    if chunk.record_id in stale_record_ids
                    else CitationFreshness.CURRENT
                )
                citations.append(
                    Citation(
                        citation_id=citation_id,
                        kind=CitationKind.CHUNK,
                        evidence_id=chunk_id,
                        record_id=chunk.record_id,
                        chunk_id=chunk_id,
                        value_path=chunk.value_path,
                        relative_path=source.path,
                        section=source.section,
                        resolution=ResolutionState.HINT_UNAVAILABLE,
                        freshness=freshness,
                    )
                )
                ids.append(citation_id)
        ids.sort(key=lambda value: int(value[1:]))
        sentence_ids[sentence.sentence_id] = tuple(ids)
    return tuple(citations), sentence_ids


def _freshness_trace(
    deps: QueryDependencies,
    stored: str | None,
    running: str | None,
    state: FreshnessState = FreshnessState.CURRENT,
    stale_reasons: Sequence[StaleReason] = (),
    manifest_path: str | None = None,
) -> FreshnessTrace:
    return FreshnessTrace(
        state=state,
        stored_pipeline_signature=stored or "",
        running_pipeline_signature=running or "",
        records_manifest_path=manifest_path,
        manifest_available=manifest_path is not None,
        start_semantic_digest=None,
        end_semantic_digest=None,
        start_raw_digest=None,
        end_raw_digest=None,
        fingerprints=tuple(
            (
                record_id,
                desired or "",
                deps.store.active_fingerprint(record_id) or "",
            )
            for record_id, desired in deps.store.ledger_fingerprints().items()
        ),
        stale_reasons=tuple(stale_reasons),
    )


def _manifest_freshness(
    deps: QueryDependencies,
    manifest_path: str | None,
    stored_semantic: str | None,
) -> tuple[FreshnessState, tuple[StaleReason, ...]]:
    """Classify the stored index against the current manifest (AC-17)."""
    if manifest_path is None or stored_semantic is None:
        return FreshnessState.UNKNOWN, (StaleReason.MANIFEST_UNAVAILABLE,)
    try:
        manifest = deps.load_manifest()
    except Exception:  # noqa: BLE001 - an unreadable manifest is unavailable
        return FreshnessState.UNKNOWN, (StaleReason.MANIFEST_UNAVAILABLE,)
    current_semantic = semantic_manifest_digest(manifest)
    if current_semantic == stored_semantic and not deps.store.has_failed_records():
        return FreshnessState.CURRENT, ()
    reasons: list[StaleReason] = []
    ledger = deps.store.ledger_fingerprints()
    manifest_ids = {entry.id for entry in manifest.entries}
    for entry in manifest.entries:
        if entry.id not in ledger:
            reasons.append(StaleReason.RECORD_ADDED)
        elif ledger[entry.id] != entry.fingerprint:
            reasons.append(StaleReason.RECORD_CHANGED)
    for record_id in ledger:
        if record_id not in manifest_ids:
            reasons.append(StaleReason.RECORD_REMOVED)
    if deps.store.has_failed_records():
        reasons.append(StaleReason.FAILED_INGEST)
    unique = sorted(set(reasons), key=lambda reason: reason.value)
    return FreshnessState.DRIFT, tuple(unique)


def _with_stale_reason(trace: FreshnessTrace, reason: StaleReason) -> FreshnessTrace:
    return _with_freshness(
        FreshnessTrace(
            state=trace.state,
            stored_pipeline_signature=trace.stored_pipeline_signature,
            running_pipeline_signature=trace.running_pipeline_signature,
            records_manifest_path=trace.records_manifest_path,
            manifest_available=trace.manifest_available,
            start_semantic_digest=trace.start_semantic_digest,
            end_semantic_digest=trace.end_semantic_digest,
            start_raw_digest=trace.start_raw_digest,
            end_raw_digest=trace.end_raw_digest,
            fingerprints=trace.fingerprints,
            stale_reasons=(*trace.stale_reasons, reason),
        ),
        trace.state,
    )


def _with_freshness(trace: FreshnessTrace, state: FreshnessState) -> FreshnessTrace:
    return FreshnessTrace(
        state=state,
        stored_pipeline_signature=trace.stored_pipeline_signature,
        running_pipeline_signature=trace.running_pipeline_signature,
        records_manifest_path=trace.records_manifest_path,
        manifest_available=trace.manifest_available,
        start_semantic_digest=trace.start_semantic_digest,
        end_semantic_digest=trace.end_semantic_digest,
        start_raw_digest=trace.start_raw_digest,
        end_raw_digest=trace.end_raw_digest,
        fingerprints=trace.fingerprints,
        stale_reasons=trace.stale_reasons,
    )


def _abstained_result(
    request: QueryRequest,
    freshness: FreshnessTrace,
    retrieval: RetrievalTrace,
    stage: AbstentionStage,
    generation: GenerationTrace | None = None,
    verification: VerificationTrace | None = None,
) -> QueryResult:
    trace = QueryTrace(
        freshness=freshness,
        retrieval=retrieval,
        generation=generation or _empty_generation(),
        verification=verification or _empty_verification(),
        providers=(),
        result=ResultTrace(
            state=QueryState.ABSTAINED,
            abstention_stage=stage,
            citations=(),
            stale_markers=(),
        ),
    )
    return QueryResult(
        schema_version=1,
        state=QueryState.ABSTAINED,
        exit_code=EXIT_OK,
        sentences=(),
        citations=(),
        freshness=freshness.state,
        abstention_stage=stage,
        trace=trace,
        failure=None,
    )


def _failed_result(
    request: QueryRequest,
    freshness: FreshnessTrace,
    failure: Failure,
    exit_code: int,
) -> QueryResult:
    trace = QueryTrace(
        freshness=freshness,
        retrieval=_empty_retrieval(request.question, ()),
        generation=_empty_generation(),
        verification=_empty_verification(),
        providers=(),
        result=ResultTrace(
            state=QueryState.FAILED,
            abstention_stage=None,
            citations=(),
            stale_markers=(),
        ),
    )
    return QueryResult(
        schema_version=1,
        state=QueryState.FAILED,
        exit_code=exit_code,
        sentences=(),
        citations=(),
        freshness=freshness.state,
        abstention_stage=None,
        trace=trace,
        failure=failure,
    )


def _safe(exc: Exception) -> str:
    """Sanitized provider or store failure text: class name, never a message."""
    return type(exc).__name__
