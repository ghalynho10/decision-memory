"""Application: the version 2 result DTOs for ingest and query (spec 0008).

Every DTO is a frozen dataclass using tuples, never mutable lists. Optional
fields are present as ``None``, never conditionally omitted. ``QueryResult``
always carries state, sentences, citations, freshness, abstention stage,
failure, and a trace, for answered, abstained, and failed results alike.
Expected input, provider, lock, and store failures return a result through
``Failure``; only programming errors raise past the application boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from decision_memory.application.canonical import SourceReference


class IngestState(StrEnum):
    """The overall ingest result state."""

    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"


class RecordAction(StrEnum):
    """What ingest did with one record."""

    ADDED = "added"
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    REMOVED = "removed"
    FAILED = "failed"


class QueryState(StrEnum):
    """The overall query result state."""

    ANSWERED = "answered"
    ABSTAINED = "abstained"
    FAILED = "failed"


class FreshnessState(StrEnum):
    """Manifest freshness at query or ingest time."""

    CURRENT = "current"
    DRIFT = "drift"
    UNKNOWN = "unknown"
    INCOMPATIBLE = "incompatible"


class StaleReason(StrEnum):
    """One reason a manifest no longer matches the index ledger."""

    RECORD_ADDED = "record_added"
    RECORD_CHANGED = "record_changed"
    RECORD_REMOVED = "record_removed"
    MANIFEST_UNAVAILABLE = "manifest_unavailable"
    MANIFEST_CHANGED_DURING_QUERY = "manifest_changed_during_query"
    FAILED_INGEST = "failed_ingest"


class FilterState(StrEnum):
    """The closed state of one filtered chunk (AC-4)."""

    ACCEPTED = "accepted"
    EXCLUDED = "excluded"


class FilterExclusionReason(StrEnum):
    """One failed filter constraint, in the fixed AC-4 order."""

    RECORD_ID = "record_id"
    STATUS = "status"
    TAG = "tag"
    VALUE_PATH = "value_path"


class LexicalDisposition(StrEnum):
    """What happened to one lexical candidate (AC-5)."""

    NO_TERM_MATCH = "no_term_match"
    NONPOSITIVE_SCORE = "nonpositive_score"
    RANKED = "ranked"
    OUTSIDE_TOP_24 = "outside_top_24"


class SemanticDisposition(StrEnum):
    """What happened to one semantic candidate (AC-6)."""

    RANKED = "ranked"
    OUTSIDE_TOP_24 = "outside_top_24"


class BreadthDisposition(StrEnum):
    """What the breadth diversity pass decided for one candidate (AC-8)."""

    ACCEPTED = "accepted"
    RECORD_CAP = "record_cap"
    ACCEPTED_LIMIT_REACHED = "accepted_limit_reached"


class SelectionPass(StrEnum):
    """Which diversity pass accepted a candidate (AC-8)."""

    BREADTH = "breadth"
    FILL = "fill"


class FinalDisposition(StrEnum):
    """What happened to one fused candidate (AC-8)."""

    ACCEPTED = "accepted"
    OUTSIDE_TOP_8 = "outside_top_8"


class RetrievalStage(StrEnum):
    """The closed terminal stage of a retrieval integrity failure (AC-9)."""

    FILTER = "filter"
    LEXICAL = "lexical"
    SEMANTIC = "semantic"
    FUSION = "fusion"
    DIVERSITY = "diversity"


class AbstentionStage(StrEnum):
    """Where an honest abstention happened."""

    RETRIEVAL = "retrieval"
    CLAIM_VERIFICATION = "claim_verification"


class ProviderOutcome(StrEnum):
    """The outcome of one provider attempt."""

    SUCCESS = "success"
    RETRYABLE_FAILURE = "retryable_failure"
    FINAL_FAILURE = "final_failure"
    SCHEMA_FAILURE = "schema_failure"


class CitationKind(StrEnum):
    """What a citation points at."""

    CHUNK = "chunk"
    SUPERSESSION = "supersession"


class ResolutionState(StrEnum):
    """How a stored source path resolved at read time."""

    RESOLVED = "resolved"
    MISSING = "missing"
    HINT_UNAVAILABLE = "hint_unavailable"
    INVALID_RELATIVE_PATH = "invalid_relative_path"


class CitationFreshness(StrEnum):
    """Whether a citation's record is current in the ledger."""

    CURRENT = "current"
    STALE_VERSION = "stale_version"


@dataclass(frozen=True)
class Failure:
    """A stable, sanitized application failure (AC-16).

    ``stage`` names the pipeline stage; ``detail`` carries application
    sanitized text, never raw SDK messages or tracebacks.
    """

    code: str
    stage: str
    detail: str


# The query result DTO schema version (spec 0008 AC-10). Version 2 adds the
# explicit filter and retrieval stage traces; there is no version 1 path.
QUERY_SCHEMA_VERSION = 2


# ---------------------------------------------------------------------------
# Ingest DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestRequest:
    """The input to ``ingest_records``."""

    records_dir: Path
    store_dir: Path
    rebuild: bool
    dry_run: bool


@dataclass(frozen=True)
class ChunkPlan:
    """One planned chunk for one record (AC-4)."""

    chunk_id: str
    record_id: str
    fingerprint: str
    value_path: str
    ordinal: int
    text: str
    evidence_token_count: int
    embedding_input_token_count: int
    sources: tuple[SourceReference, ...]


@dataclass(frozen=True)
class RecordIngestResult:
    """What ingest did with one record (AC-7)."""

    record_id: str
    action: RecordAction
    state: str
    desired_fingerprint: str
    active_fingerprint: str | None
    chunks: tuple[ChunkPlan, ...]
    batch_count: int
    failure_code: str | None


@dataclass(frozen=True)
class IngestResult:
    """The full result of an ingest run."""

    schema_version: int
    state: IngestState
    exit_code: int
    store_path: Path
    semantic_manifest_digest: str | None
    raw_manifest_digest: str | None
    records: tuple[RecordIngestResult, ...]
    provider_attempts: int
    failure: Failure | None


# ---------------------------------------------------------------------------
# Query DTOs
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class QueryFilters:
    """Normalized explicit query filters (AC-2).

    Each field holds sorted, unique values. Within one field values use OR;
    across fields they use AND. Statuses are already normalized to the closed
    lowercase values ``proposed``, ``accepted``, ``superseded``, and
    ``rejected``. Record ids, tags, and value paths remain case sensitive.
    """

    record_ids: tuple[str, ...] = ()
    statuses: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    value_paths: tuple[str, ...] = ()


@dataclass(frozen=True)
class ActiveChunkDescriptor:
    """One active chunk with its record metadata (AC-16).

    The immutable input snapshot for application filtering and retrieval,
    produced by ``IndexReader.active_chunks`` from one read transaction.
    """

    chunk_id: str
    record_id: str
    record_title: str
    record_status: str | None
    record_tags: tuple[str, ...]
    value_path: str
    fingerprint: str
    ordinal: int
    text: str
    provenance: tuple[SourceReference, ...]


@dataclass(frozen=True)
class FilterRow:
    """One active chunk with its filter decision (AC-4).

    Every active chunk gets one row, even when no filter is present. ``state``
    is the closed ``accepted`` or ``excluded`` value and ``exclusion_reasons``
    lists every failed constraint in the fixed order.
    """

    chunk_id: str
    record_id: str
    record_status: str | None
    record_tags: tuple[str, ...]
    value_path: str
    state: FilterState
    exclusion_reasons: tuple[FilterExclusionReason, ...]


@dataclass(frozen=True)
class QueryRequest:
    """The input to ``query_index`` (AC-1)."""

    question: str
    store_dir: Path
    allow_stale: bool
    filters: QueryFilters


@dataclass(frozen=True)
class AnswerSentence:
    """One verified answer sentence with its citation ids (AC-10)."""

    sentence_id: str
    text: str
    citation_ids: tuple[str, ...]


@dataclass(frozen=True)
class Citation:
    """One source citation for an answer sentence (AC-10, AC-19)."""

    citation_id: str
    kind: CitationKind
    evidence_id: str
    record_id: str
    chunk_id: str | None
    value_path: str
    relative_path: str
    section: str
    resolution: ResolutionState
    freshness: CitationFreshness


@dataclass(frozen=True)
class SupersessionNotice:
    """One immediate eligible successor of a retrieved predecessor (AC-18).

    It carries only successor identity and metadata, never successor decision
    content, so the generator cannot be tempted to describe how the successor
    changed the decision.
    """

    predecessor_id: str
    successor_id: str
    successor_title: str
    successor_status: str
    successor_date: str | None
    metadata_evidence_id: str


@dataclass(frozen=True)
class QueryResult:
    """The full result of a query (AC-10, AC-13)."""

    schema_version: int
    state: QueryState
    exit_code: int
    sentences: tuple[AnswerSentence, ...]
    citations: tuple[Citation, ...]
    freshness: FreshnessState
    abstention_stage: AbstentionStage | None
    trace: QueryTrace
    failure: Failure | None


# ---------------------------------------------------------------------------
# Trace DTOs (version 1, always present on QueryResult)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Facet:
    """One fixed question facet extracted before generation (AC-15)."""

    facet_id: str
    text: str


@dataclass(frozen=True)
class DraftSentence:
    """One structured draft sentence before verification."""

    sentence_id: str
    text: str
    chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class LexicalRow:
    """One lexical retrieval row (AC-5).

    ``rank`` is present only for positive scored rows; the closed disposition
    is ``no_term_match``, ``nonpositive_score``, ``ranked``, or
    ``outside_top_24``.
    """

    chunk_id: str
    score: float
    rank: int | None
    disposition: LexicalDisposition


@dataclass(frozen=True)
class SemanticRow:
    """One semantic retrieval row (AC-6)."""

    chunk_id: str
    rank: int
    distance: float
    similarity: float
    disposition: SemanticDisposition


@dataclass(frozen=True)
class FusedCandidate:
    """One chunk in the fused ranking with its diversity decision (AC-7, AC-8).

    ``lexical_rank`` and ``semantic_rank`` are None when that retriever did
    not rank the chunk. ``selection_pass`` and ``final_rank`` are None for a
    deferred row that never filled. One chunk appears at most once in fusion.
    """

    chunk_id: str
    record_id: str
    value_path: str
    fingerprint: str
    ordinal: int
    text: str
    provenance: tuple[SourceReference, ...]
    lexical_rank: int | None
    semantic_rank: int | None
    fused_score: float
    fused_rank: int
    breadth_disposition: BreadthDisposition
    selection_pass: SelectionPass | None
    final_rank: int | None
    final_disposition: FinalDisposition


@dataclass(frozen=True)
class FreshnessTrace:
    """The freshness decision for one query (AC-17)."""

    state: FreshnessState
    stored_pipeline_signature: str
    running_pipeline_signature: str
    records_manifest_path: str | None
    manifest_available: bool
    start_semantic_digest: str | None
    end_semantic_digest: str | None
    start_raw_digest: str | None
    end_raw_digest: str | None
    fingerprints: tuple[tuple[str, str, str], ...]
    stale_reasons: tuple[StaleReason, ...]


@dataclass(frozen=True)
class FilterTrace:
    """The filter stage rows, sorted by chunk id (AC-4, AC-10)."""

    rows: tuple[FilterRow, ...]


@dataclass(frozen=True)
class LexicalTrace:
    """The lexical stage rows, sorted by chunk id (AC-5, AC-10)."""

    rows: tuple[LexicalRow, ...]


@dataclass(frozen=True)
class SemanticTrace:
    """The semantic stage rows, sorted by chunk id (AC-6, AC-10)."""

    rows: tuple[SemanticRow, ...]


@dataclass(frozen=True)
class FusionTrace:
    """The fused candidates, sorted by fused rank (AC-7, AC-10)."""

    candidates: tuple[FusedCandidate, ...]


@dataclass(frozen=True)
class DiversityTrace:
    """The diversity outcome: accepted ids in final rank order (AC-8, AC-10)."""

    accepted_chunk_ids: tuple[str, ...]
    accepted_limit: int
    record_cap: int


@dataclass(frozen=True)
class RetrievalSettings:
    """The fixed retrieval settings recorded in every trace (AC-10)."""

    tokenizer_version: str
    stopword_set: str
    stopword_digest: str
    bm25_variant: str
    bm25_parameters: str
    lexical_limit: int
    semantic_limit: int
    rrf_constant: int
    accepted_limit: int
    diversity_cap: int
    collection_metric: str
    relevance_floor: float | None


@dataclass(frozen=True)
class RetrievalTrace:
    """The retrieval decision for one query (AC-10).

    Fixed Filter, Lexical, Semantic, Fusion, and Diversity sections after
    Freshness, plus the fixed retrieval settings.
    """

    filters: FilterTrace
    lexical: LexicalTrace
    semantic: SemanticTrace
    fusion: FusionTrace
    diversity: DiversityTrace
    settings: RetrievalSettings


@dataclass(frozen=True)
class GenerationTrace:
    """What the generation concern produced (AC-15)."""

    facets: tuple[Facet, ...]
    supersession_notices: tuple[SupersessionNotice, ...]
    draft_sentences: tuple[DraftSentence, ...]
    cited_chunk_ids: tuple[str, ...]


@dataclass(frozen=True)
class CoverageRow:
    """One fixed facet's independent coverage verdict."""

    facet_id: str
    covered: bool
    reason: str
    sentence_ids: tuple[str, ...]


@dataclass(frozen=True)
class VerificationTrace:
    """The verification decision for one query (AC-15)."""

    containment: tuple[tuple[str, bool], ...]
    entailment: tuple[tuple[str, str, str], ...]
    removed_sentences: tuple[str, ...]
    coverage: tuple[CoverageRow, ...]
    uncovered_facets: tuple[Facet, ...]


@dataclass(frozen=True)
class ProviderAttempt:
    """One provider attempt with its timing and outcome."""

    concern: str
    attempt_number: int
    elapsed_ms: int
    outcome: ProviderOutcome


@dataclass(frozen=True)
class ResultTrace:
    """The terminal result section of the trace."""

    state: QueryState
    abstention_stage: AbstentionStage | None
    citations: tuple[str, ...]
    stale_markers: tuple[str, ...]


@dataclass(frozen=True)
class PartialQueryTrace:
    """The partial trace carried by a retrieval integrity failure (AC-9).

    A completed stage is retained; the failing stage and every later stage are
    absent rather than synthesized as empty.
    """

    freshness: FreshnessTrace
    filters: FilterTrace | None
    lexical: LexicalTrace | None
    semantic: SemanticTrace | None
    fusion: FusionTrace | None
    diversity: DiversityTrace | None
    providers: tuple[ProviderAttempt, ...]


@dataclass(frozen=True)
class SemanticMatches:
    """Positionally aligned plain semantic search results (AC-6, AC-16)."""

    ids: tuple[str, ...]
    distances: tuple[float, ...]


class RetrievalFailure(Exception):
    """A typed retrieval integrity failure, never a QueryResult (AC-9, AC-10).

    ``stage`` is the closed terminal retrieval stage and ``trace`` is the
    partial query trace completed before the failure.
    """

    def __init__(self, stage: RetrievalStage, trace: PartialQueryTrace) -> None:
        super().__init__(stage.value)
        self.stage = stage
        self.trace = trace


@dataclass(frozen=True)
class QueryTrace:
    """The always present version 2 trace (AC-10)."""

    freshness: FreshnessTrace
    retrieval: RetrievalTrace
    generation: GenerationTrace
    verification: VerificationTrace
    providers: tuple[ProviderAttempt, ...]
    result: ResultTrace


# Import the circular reference at the end: QueryTrace names QueryTrace in its
# own module, which is fine since the module is self contained. The forward
# reference above is resolved by ``from __future__ import annotations``.
__all__ = [
    "AbstentionStage",
    "ActiveChunkDescriptor",
    "AnswerSentence",
    "BreadthDisposition",
    "ChunkPlan",
    "Citation",
    "CitationFreshness",
    "CitationKind",
    "CoverageRow",
    "DiversityTrace",
    "DraftSentence",
    "Facet",
    "Failure",
    "FilterExclusionReason",
    "FilterRow",
    "FilterState",
    "FilterTrace",
    "FinalDisposition",
    "FreshnessState",
    "FreshnessTrace",
    "FusedCandidate",
    "FusionTrace",
    "GenerationTrace",
    "IngestRequest",
    "IngestResult",
    "IngestState",
    "LexicalDisposition",
    "LexicalRow",
    "LexicalTrace",
    "PartialQueryTrace",
    "ProviderAttempt",
    "ProviderOutcome",
    "QUERY_SCHEMA_VERSION",
    "QueryFilters",
    "QueryRequest",
    "QueryResult",
    "QueryState",
    "QueryTrace",
    "RecordAction",
    "RecordIngestResult",
    "ResolutionState",
    "ResultTrace",
    "RetrievalFailure",
    "RetrievalSettings",
    "RetrievalStage",
    "RetrievalTrace",
    "SemanticDisposition",
    "SemanticMatches",
    "SemanticRow",
    "SemanticTrace",
    "SelectionPass",
    "StaleReason",
    "SupersessionNotice",
    "VerificationTrace",
]
