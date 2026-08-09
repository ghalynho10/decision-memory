"""Application: the version 1 result DTOs for ingest and query (spec 0007).

AC-10 and AC-13 fix these schemas: every DTO is a frozen dataclass using
tuples, never mutable lists. Optional fields are present as ``None``, never
conditionally omitted. ``QueryResult`` always carries state, sentences,
citations, freshness, abstention stage, failure, and a trace, for answered,
abstained, and failed results alike. Expected input, provider, lock, and store
failures return a result through ``Failure``; only programming errors raise
past the application boundary.
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


class CandidateDisposition(StrEnum):
    """What happened to one retrieval candidate."""

    ACCEPTED = "accepted"
    BELOW_FLOOR = "below_floor"
    OUTSIDE_TOP_8 = "outside_top_8"


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
class QueryRequest:
    """The input to ``query_index``."""

    question: str
    store_dir: Path
    allow_stale: bool


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
class Candidate:
    """One retrieval candidate with its full scoring and provenance."""

    chunk_id: str
    record_id: str
    value_path: str
    fingerprint: str
    ordinal: int
    distance: float
    similarity: float
    rank: int
    disposition: CandidateDisposition
    text: str
    provenance: tuple[SourceReference, ...]


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
class RetrievalTrace:
    """The retrieval decision for one query (AC-12)."""

    question: str
    filters: tuple[str, ...]
    eligibility: tuple[tuple[str, str, str], ...]
    candidate_limit: int
    accepted_limit: int
    relevance_floor: float | None
    candidates: tuple[Candidate, ...]


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
class QueryTrace:
    """The always present version 1 trace (AC-13)."""

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
    "AnswerSentence",
    "Candidate",
    "CandidateDisposition",
    "ChunkPlan",
    "Citation",
    "CitationFreshness",
    "CitationKind",
    "CoverageRow",
    "DraftSentence",
    "Facet",
    "Failure",
    "FreshnessState",
    "FreshnessTrace",
    "GenerationTrace",
    "IngestRequest",
    "IngestResult",
    "IngestState",
    "ProviderAttempt",
    "ProviderOutcome",
    "QueryRequest",
    "QueryResult",
    "QueryState",
    "QueryTrace",
    "RecordAction",
    "RecordIngestResult",
    "ResolutionState",
    "ResultTrace",
    "RetrievalTrace",
    "StaleReason",
    "SupersessionNotice",
    "VerificationTrace",
]
