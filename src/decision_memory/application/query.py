"""Application: the query use case (spec 0007 AC-12, AC-15, AC-16; spec 0008).

``query_index`` reads only the local store. It applies explicit metadata
filters to an immutable ``active_chunks`` snapshot first (AC-4), so a filter
that matches nothing abstains without any embedding or generation call. It
then runs BM25 lexical and cosine semantic retrieval over the same accepted
chunks, fuses their ranks with reciprocal rank fusion, applies a two pass
record diversity rule, and passes the accepted context to the existing
generation and verification path (AC-5 to AC-8). Provider, schema, lock,
manifest, and store failures are never abstention. The application receives
every provider and store concern as a narrow callable or protocol (AC-20).
"""

from __future__ import annotations

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Protocol

from decision_memory.application.adapter import Manifest, semantic_manifest_digest
from decision_memory.application.canonical import SourceReference
from decision_memory.application.dto import (
    AbstentionStage,
    ActiveChunkDescriptor,
    AnswerSentence,
    BreadthDisposition,
    Citation,
    CitationFreshness,
    CitationKind,
    CoverageRow,
    DiversityTrace,
    DraftSentence,
    DroppedSentence,
    Facet,
    Failure,
    FilterState,
    FilterTrace,
    FinalDisposition,
    FreshnessState,
    FreshnessTrace,
    FusedCandidate,
    FusionTrace,
    GenerationTrace,
    LexicalDisposition,
    LexicalRow,
    LexicalTrace,
    PartialQueryTrace,
    ProviderAttempt,
    QueryRequest,
    QueryResult,
    QueryState,
    QueryTrace,
    RejectedDecomposition,
    ResolutionState,
    ResultTrace,
    RetrievalFailure,
    RetrievalSettings,
    RetrievalStage,
    RetrievalTrace,
    SelectionPass,
    SemanticDisposition,
    SemanticMatches,
    SemanticRow,
    SemanticTrace,
    StaleReason,
    SubClaim,
    SupersessionNotice,
    VerificationTrace,
)
from decision_memory.application.filters import filter_descriptors
from decision_memory.application.lexical import (
    LEXICAL_TOKENIZER_VERSION,
    STOPWORD_DIGEST,
    STOPWORD_SET,
    tokenize,
)
from decision_memory.application.pipeline import (
    MODEL_TOKEN_LIMIT,
    pipeline_signature,
)
from decision_memory.application.store_format import STORE_FORMAT_VERSION
from decision_memory.application.verification import (
    RETRYABLE_DISPOSITIONS,
    classify_decomposition_detail,
    deterministic_containment,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2

# Fixed retrieval limits and constants (spec 0008 AC-7, AC-8, AC-10). These
# are recorded in every settings trace and do not enter the ingestion pipeline
# signature, so Feature 11 may calibrate them without rebuilding embeddings.
CANDIDATE_LIMIT = 24
ACCEPTED_LIMIT = 8
RRF_CONSTANT = 60
DIVERSITY_CAP = 2
BM25_VARIANT = "BM25Okapi"
BM25_PARAMETERS = "k1=1.5,b=0.75"
COLLECTION_METRIC = "cosine"

# The reason on every deterministic uncovered coverage row, written when no
# sentence reached coverage at all (spec 0010 AC-12). It has one home because
# it has more than one reader: the evaluation oracle tells an abstention
# caused by every sentence being dropped from one caused by an uncovered facet
# by reading exactly this string off the coverage rows (spec 0010 AC-15).
NO_EMITTED_SENTENCE_REASON = "no emitted answer sentence"

# A cosine distance is valid when finite and within [0, 2]. The epsilon
# absorbs Chroma float noise at the boundaries (a parallel vector can come
# back as a tiny negative); the value is then clamped so traces hold a real
# cosine distance (AC-6).
DISTANCE_EPSILON = 1e-6


def _valid_distance(distance: float) -> bool:
    """Finite and within ``[0, 2]`` up to float noise (AC-6)."""
    return (
        distance == distance and -DISTANCE_EPSILON <= distance <= 2.0 + DISTANCE_EPSILON
    )


def _partial(
    freshness: FreshnessTrace,
    filters: FilterTrace | None,
    lexical: LexicalTrace | None,
    semantic: SemanticTrace | None,
    fusion: FusionTrace | None,
    diversity: DiversityTrace | None,
    providers: Sequence[ProviderAttempt],
) -> PartialQueryTrace:
    """Build the partial trace carried by a ``RetrievalFailure`` (AC-9)."""
    return PartialQueryTrace(
        freshness=freshness,
        filters=filters,
        lexical=lexical,
        semantic=semantic,
        fusion=fusion,
        diversity=diversity,
        providers=tuple(providers),
    )


class LexicalScorer(Protocol):
    """Scores documents against query tokens, one float per document (AC-16).

    Injected from infrastructure (``rank_bm25``). Document token tuples arrive
    in chunk id order and the returned scores are positionally aligned.
    """

    def __call__(
        self,
        query_tokens: Sequence[str],
        document_tokens: Sequence[Sequence[str]],
    ) -> Sequence[float]: ...


class IndexReader(Protocol):
    """The read side of the store, implemented in infrastructure."""

    def pipeline_signature(self) -> str: ...
    def generation_id(self) -> str | None: ...
    def store_format(self) -> int | None: ...
    def parity_problems(self) -> list[str]: ...
    def active_chunks(self) -> tuple[ActiveChunkDescriptor, ...]: ...
    def manifest_metadata(
        self,
    ) -> tuple[str | None, str | None, str | None, str | None]: ...
    def ledger_fingerprints(self) -> dict[str, str | None]: ...
    def ledger_entry_digests(self) -> dict[str, str | None]: ...
    def has_failed_records(self) -> bool: ...
    def active_fingerprint(self, record_id: str) -> str | None: ...
    def supersession_notices(
        self, predecessor_id: str
    ) -> tuple[SupersessionNotice, ...]: ...
    def semantic_search(
        self,
        embedding: Sequence[float],
        accepted_chunk_ids: Sequence[str],
    ) -> SemanticMatches: ...


@dataclass(frozen=True)
class QueryDependencies:
    """Every concern query needs, injected at the composition root."""

    store: IndexReader
    count_tokens: Callable[[str], int]
    embed: Callable[[Sequence[str], list[ProviderAttempt] | None], list[list[float]]]
    lexical_scorer: LexicalScorer
    load_manifest: Callable[[], Manifest]
    raw_manifest_digest: Callable[[], str]
    resolve_source: Callable[[str], ResolutionState]
    extract_facets: Callable[[str, list[ProviderAttempt] | None], tuple[Facet, ...]]
    # The accepted evidence travels as one sequence of (chunk_id, value_path,
    # text) triples, not as parallel sequences (spec 0010 AC-18). Generation
    # was the one stage that never received a chunk's ``value_path``, and a
    # third parallel list would have widened the silent misalignment the
    # existing non strict zip already allowed.
    generate_answer: Callable[
        [
            Sequence[Facet],
            Sequence[tuple[str, str, str]],
            Sequence[SupersessionNotice],
            frozenset[str],
            list[ProviderAttempt] | None,
        ],
        tuple[DraftSentence, ...],
    ]
    decompose: Callable[
        [str, Sequence[tuple[str, str]], list[ProviderAttempt] | None],
        tuple[str, ...],
    ]
    entail: Callable[
        [str, Sequence[tuple[str, str]], list[ProviderAttempt] | None],
        tuple[bool, str],
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
    if deps.store.store_format() != STORE_FORMAT_VERSION:
        return _failed_result(
            request,
            _freshness_trace(deps, None, None),
            Failure(
                "store.format",
                "store",
                f"index store format {deps.store.store_format()} is not "
                "supported; run ingest --rebuild",
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

    # Filter stage: one immutable SQLite snapshot, one FilterRow per active
    # chunk even when no filter is present (AC-4).
    try:
        active = deps.store.active_chunks()
    except Exception as exc:  # noqa: BLE001 - retrieval integrity failure
        raise RetrievalFailure(
            RetrievalStage.FILTER,
            _partial(freshness, None, None, None, None, None, attempts),
        ) from exc
    if not active:
        return _abstained_result(
            request, freshness, _empty_retrieval(), AbstentionStage.RETRIEVAL
        )
    filter_rows = filter_descriptors(active, request.filters)
    filter_trace = FilterTrace(
        rows=tuple(sorted(filter_rows, key=lambda row: row.chunk_id))
    )
    accepted_ids = frozenset(
        row.chunk_id for row in filter_rows if row.state == FilterState.ACCEPTED
    )
    if not accepted_ids:
        return _abstained_result(
            request,
            freshness,
            _retrieval_with_filter(filter_trace),
            AbstentionStage.RETRIEVAL,
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

    accepted_by_id = {
        chunk.chunk_id: chunk for chunk in active if chunk.chunk_id in accepted_ids
    }

    # Lexical stage: BM25 over accepted chunk text, no provider call (AC-5).
    try:
        lexical_trace, ranked_lexical = _lexical_stage(
            question, accepted_by_id, deps.lexical_scorer
        )
    except Exception as exc:  # noqa: BLE001 - retrieval integrity failure
        raise RetrievalFailure(
            RetrievalStage.LEXICAL,
            _partial(freshness, filter_trace, None, None, None, None, attempts),
        ) from exc

    # Semantic retrieval over the exact accepted ids (AC-6): Chroma receives
    # the accepted count as n_results and an $in over the accepted ids, and the
    # application validates the returned set before local ranking.
    try:
        question_vector = deps.embed([question], attempts)[0]
    except Exception as exc:  # noqa: BLE001 - provider failure is a result
        return _failed_result(
            request,
            freshness,
            Failure("provider.embedding", "embedding", _safe(exc)),
            EXIT_ERROR,
            attempts,
        )
    try:
        matches = deps.store.semantic_search(
            question_vector, tuple(sorted(accepted_ids))
        )
    except Exception as exc:  # noqa: BLE001 - retrieval integrity failure
        raise RetrievalFailure(
            RetrievalStage.SEMANTIC,
            _partial(
                freshness, filter_trace, lexical_trace, None, None, None, attempts
            ),
        ) from exc
    if len(matches.ids) != len(accepted_ids) or set(matches.ids) != accepted_ids:
        raise RetrievalFailure(
            RetrievalStage.SEMANTIC,
            _partial(
                freshness, filter_trace, lexical_trace, None, None, None, attempts
            ),
        )
    if len(matches.distances) != len(matches.ids):
        raise RetrievalFailure(
            RetrievalStage.SEMANTIC,
            _partial(
                freshness, filter_trace, lexical_trace, None, None, None, attempts
            ),
        )

    scored: list[tuple[ActiveChunkDescriptor, float]] = []
    for chunk_id, raw_distance in zip(matches.ids, matches.distances, strict=True):
        chunk = accepted_by_id.get(chunk_id)
        if chunk is None:
            raise RetrievalFailure(
                RetrievalStage.SEMANTIC,
                _partial(
                    freshness, filter_trace, lexical_trace, None, None, None, attempts
                ),
            )
        if not _valid_distance(raw_distance):
            raise RetrievalFailure(
                RetrievalStage.SEMANTIC,
                _partial(
                    freshness, filter_trace, lexical_trace, None, None, None, attempts
                ),
            )
        scored.append((chunk, max(0.0, min(2.0, raw_distance))))
    # Local sort by distance ascending then chunk id; application decides the
    # top 24 boundary, never Chroma ordering (AC-6).
    scored.sort(key=lambda pair: (pair[1], pair[0].chunk_id))

    semantic_rows = [
        SemanticRow(
            chunk_id=chunk.chunk_id,
            rank=rank,
            distance=distance,
            similarity=1.0 - distance,
            disposition=(
                SemanticDisposition.RANKED
                if rank <= CANDIDATE_LIMIT
                else SemanticDisposition.OUTSIDE_TOP_24
            ),
        )
        for rank, (chunk, distance) in enumerate(scored, start=1)
    ]
    semantic_trace = SemanticTrace(
        rows=tuple(sorted(semantic_rows, key=lambda row: row.chunk_id))
    )
    ranked_semantic = {
        row.chunk_id: row.rank
        for row in semantic_rows
        if row.disposition == SemanticDisposition.RANKED
    }

    # Reciprocal rank fusion over the ranked lexical and semantic union (AC-7).
    try:
        fused = _fusion_stage(ranked_lexical, ranked_semantic, accepted_by_id)
    except Exception as exc:  # noqa: BLE001 - retrieval integrity failure
        raise RetrievalFailure(
            RetrievalStage.FUSION,
            _partial(
                freshness,
                filter_trace,
                lexical_trace,
                semantic_trace,
                None,
                None,
                attempts,
            ),
        ) from exc
    if not fused:
        # Ranked union empty after a nonempty filter result: retrieval
        # abstention, both complete traces preserved, no generation call (AC-9).
        retrieval = RetrievalTrace(
            filters=filter_trace,
            lexical=lexical_trace,
            semantic=semantic_trace,
            fusion=FusionTrace(candidates=()),
            diversity=DiversityTrace(
                accepted_chunk_ids=(),
                accepted_limit=ACCEPTED_LIMIT,
                record_cap=DIVERSITY_CAP,
            ),
            settings=_retrieval_settings(),
        )
        return _abstained_result(
            request,
            freshness,
            retrieval,
            AbstentionStage.RETRIEVAL,
            attempts=attempts,
        )

    # Two pass record diversity over the fused candidates (AC-8).
    try:
        final_candidates, accepted_chunks = _diversity_stage(fused, accepted_by_id)
    except Exception as exc:  # noqa: BLE001 - retrieval integrity failure
        raise RetrievalFailure(
            RetrievalStage.DIVERSITY,
            _partial(
                freshness,
                filter_trace,
                lexical_trace,
                semantic_trace,
                FusionTrace(candidates=tuple(fused)),
                None,
                attempts,
            ),
        ) from exc
    retrieval = RetrievalTrace(
        filters=filter_trace,
        lexical=lexical_trace,
        semantic=semantic_trace,
        fusion=FusionTrace(candidates=tuple(final_candidates)),
        diversity=DiversityTrace(
            accepted_chunk_ids=tuple(chunk.chunk_id for chunk in accepted_chunks),
            accepted_limit=ACCEPTED_LIMIT,
            record_cap=DIVERSITY_CAP,
        ),
        settings=_retrieval_settings(),
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
            attempts,
        )
    generation = GenerationTrace(
        facets=facets,
        supersession_notices=(),
        draft_sentences=(),
        cited_chunk_ids=(),
    )

    # One sequence of triples, so the id, the field label source, and the text
    # cannot drift apart on the way to generation (AC-18).
    accepted_evidence = [
        (chunk.chunk_id, chunk.value_path, chunk.text) for chunk in accepted_chunks
    ]
    known_ids = frozenset(chunk.chunk_id for chunk in accepted_chunks)
    notices = _collect_notices(deps.store, accepted_chunks)
    try:
        draft = deps.generate_answer(
            facets, accepted_evidence, notices, known_ids, attempts
        )
    except Exception as exc:  # noqa: BLE001 - provider failure is a result
        return _failed_result(
            request,
            freshness,
            Failure("provider.answer", "generation", _safe(exc)),
            EXIT_ERROR,
            attempts,
        )
    generation = GenerationTrace(
        facets=facets,
        supersession_notices=notices,
        draft_sentences=draft,
        cited_chunk_ids=tuple(sorted(known_ids)),
    )

    # Verify each sentence: whole containment shortcut, then sub claim
    # decomposition and per sub claim verification (spec 0010). Decomposition
    # is a check on the draft sentence, not a rewrite of it: the verification
    # unit is the sub claim, the output unit is the sentence (AC-4).
    #
    # A sentence that is verbatim in one of its available cited chunks is
    # emitted and never pays a decomposition call (AC-5). Before any
    # containment or provider call, the parent citation ids are deduplicated
    # in parent order and split into available and missing citations: every
    # containment, decomposition, entailment, and output citation uses only
    # the available ids, and a missing id is trace only (AC-8). Any other
    # sentence is decomposed, the response is tested for validity as a whole,
    # and each sub claim is verified alone. The parent is emitted verbatim
    # only when its decomposition is valid and every sub claim is supported;
    # either failure drops the whole parent, so a verbatim borrowed clause can
    # no longer survive on its own carrying an invented decision (AC-1, AC-4).
    emitted_sentences: list[DraftSentence] = []
    containment_rows: list[tuple[str, bool]] = []
    entailment_rows: list[tuple[str, str, str]] = []
    removed: list[str] = []
    decomposed_rows: list[SubClaim] = []
    empty_decompositions: list[str] = []
    rejected_decompositions: list[RejectedDecomposition] = []
    dropped_sentences: list[DroppedSentence] = []
    missing_chunk_refs: list[tuple[str, tuple[str, ...]]] = []
    chunk_text_by_id = {chunk.chunk_id: chunk.text for chunk in accepted_chunks}
    for sentence in draft:
        # Deduplicate parent citation ids in parent order (first occurrence),
        # then partition into available and missing (AC-8).
        deduped_ids: list[str] = []
        for chunk_id in sentence.chunk_ids:
            if chunk_id not in deduped_ids:
                deduped_ids.append(chunk_id)
        available_ids = tuple(
            chunk_id for chunk_id in deduped_ids if chunk_id in chunk_text_by_id
        )
        missing_ids = tuple(
            chunk_id for chunk_id in deduped_ids if chunk_id not in chunk_text_by_id
        )
        if missing_ids:
            missing_chunk_refs.append((sentence.sentence_id, missing_ids))
        available_texts = [chunk_text_by_id[chunk_id] for chunk_id in available_ids]
        available_evidence = tuple(zip(available_ids, available_texts, strict=True))
        contained = deterministic_containment(sentence.text, available_texts)
        containment_rows.append((sentence.sentence_id, contained))
        if contained:
            # Whole sentence contained: emit the parent, narrowed to its
            # available citations only (AC-5, AC-8).
            emitted_sentences.append(
                DraftSentence(sentence.sentence_id, sentence.text, available_ids)
            )
            continue
        if not available_texts:
            # Verified against empty evidence: never supported (AC-8). The
            # missing refs are already recorded above.
            removed.append(sentence.sentence_id)
            dropped_sentences.append(
                DroppedSentence(sentence.sentence_id, "no_available_citations")
            )
            continue
        # Decompose, then test the response for validity. A two half failure
        # earns one retry at the same fixed settings, because an invalid
        # decomposition is usually a stochastic paraphrase rather than a
        # property of the sentence; an over cap or duplicate response is
        # rejected outright (AC-11).
        rejection: str | None = None
        additive_failure = ""
        sub_claim_texts: tuple[str, ...] = ()
        for attempt in range(2):
            try:
                sub_claim_texts = deps.decompose(
                    sentence.text, available_evidence, attempts
                )
            except Exception as exc:  # noqa: BLE001 - provider failure is a result
                return _failed_result(
                    request,
                    freshness,
                    Failure("provider.decompose", "claim_verification", _safe(exc)),
                    EXIT_ERROR,
                    attempts,
                )
            if not sub_claim_texts:
                break
            rejection, additive_failure = classify_decomposition_detail(
                sub_claim_texts, sentence.text
            )
            if rejection is None or rejection not in RETRYABLE_DISPOSITIONS:
                break
            if attempt == 1:
                break
        if not sub_claim_texts:
            # Genuine empty response: drop the sentence and record the empty
            # signal, which is distinct from a rejected response and carries
            # no disposition of its own (AC-6).
            empty_decompositions.append(sentence.sentence_id)
            removed.append(sentence.sentence_id)
            dropped_sentences.append(
                DroppedSentence(sentence.sentence_id, "decomposition_invalid")
            )
            continue
        if rejection is not None:
            # Invalid response: one closed disposition, paired with one
            # dropped sentence row, so the two are one event described at two
            # levels. No entailment call is made, and rejected claim text is
            # never recorded (AC-6, AC-11).
            rejected_decompositions.append(
                RejectedDecomposition(
                    sentence.sentence_id,
                    len(sub_claim_texts),
                    rejection,
                    additive_failure,
                )
            )
            removed.append(sentence.sentence_id)
            dropped_sentences.append(
                DroppedSentence(sentence.sentence_id, "decomposition_invalid")
            )
            continue
        # Valid response: verify every sub claim alone, in provider order,
        # containment first then entailment. A sub claim is never removed
        # from a valid response, so the ids are contiguous (AC-6).
        rows: list[SubClaim] = []
        all_supported = True
        for position, text in enumerate(sub_claim_texts):
            sub_claim_id = f"{sentence.sentence_id}.{position + 1}"
            matching_ids = tuple(
                chunk_id
                for chunk_id in available_ids
                if deterministic_containment(text, [chunk_text_by_id[chunk_id]])
            )
            if matching_ids:
                rows.append(
                    SubClaim(
                        sub_claim_id=sub_claim_id,
                        sentence_id=sentence.sentence_id,
                        text=text,
                        contained=True,
                        entailment="skipped",
                        reason="",
                        citations=matching_ids,
                    )
                )
                continue
            try:
                supported, reason = deps.entail(text, available_evidence, attempts)
            except Exception as exc:  # noqa: BLE001 - provider failure is a result
                return _failed_result(
                    request,
                    freshness,
                    Failure("provider.entailment", "claim_verification", _safe(exc)),
                    EXIT_ERROR,
                    attempts,
                )
            rows.append(
                SubClaim(
                    sub_claim_id=sub_claim_id,
                    sentence_id=sentence.sentence_id,
                    text=text,
                    contained=False,
                    entailment="supported" if supported else "unsupported",
                    reason=reason,
                    citations=available_ids,
                )
            )
            if not supported:
                all_supported = False
        decomposed_rows.extend(rows)
        if all_supported:
            # Every sub claim supported: emit the parent sentence verbatim,
            # with its available citations and its own sentence id. Sub claims
            # stay in the trace and are never emitted (AC-4).
            emitted_sentences.append(
                DraftSentence(sentence.sentence_id, sentence.text, available_ids)
            )
        else:
            # Any unsupported sub claim drops the whole parent, so a grounded
            # clause cannot survive on its own. The unsupported row above
            # names the exact claim that caused the drop (AC-1, AC-6).
            removed.append(sentence.sentence_id)
            dropped_sentences.append(
                DroppedSentence(sentence.sentence_id, "unsupported_sub_claim")
            )

    # Independent coverage over the original question, the unchanged
    # canonical facet tuple, and the emitted sentences, in draft order. With
    # no emitted sentences, every facet is deterministically uncovered and no
    # coverage call is made (spec 0010 AC-12).
    if emitted_sentences:
        try:
            coverage_rows = deps.coverage(question, facets, emitted_sentences, attempts)
        except Exception as exc:  # noqa: BLE001 - provider failure is a result
            return _failed_result(
                request,
                freshness,
                Failure("provider.coverage", "claim_verification", _safe(exc)),
                EXIT_ERROR,
                attempts,
            )
    else:
        coverage_rows = tuple(
            CoverageRow(facet.facet_id, False, NO_EMITTED_SENTENCE_REASON, ())
            for facet in facets
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
        decomposed=tuple(decomposed_rows),
        empty_decompositions=tuple(empty_decompositions),
        rejected_decompositions=tuple(rejected_decompositions),
        dropped_sentences=tuple(dropped_sentences),
        missing_chunk_refs=tuple(missing_chunk_refs),
    )
    if uncovered:
        return _abstained_result(
            request,
            freshness,
            retrieval,
            AbstentionStage.CLAIM_VERIFICATION,
            generation=generation,
            verification=verification,
            attempts=attempts,
        )

    # Build citations by first sentence use, deduplicated by source location.
    chunk_by_id = {chunk.chunk_id: chunk for chunk in accepted_chunks}
    stale_record_ids = frozenset(
        record_id
        for record_id, desired in deps.store.ledger_fingerprints().items()
        if desired is not None and deps.store.active_fingerprint(record_id) != desired
    )
    chunk_citations, chunk_sentence_ids = _allocate_citations(
        emitted_sentences, chunk_by_id, stale_record_ids, deps.resolve_source
    )
    try:
        manifest = deps.load_manifest()
    except Exception:  # noqa: BLE001 - no manifest means no supersedes provenance
        manifest = None
    disclosure_sentences, disclosure_citations = _render_disclosures(
        manifest,
        notices,
        deps.resolve_source,
        stale_record_ids,
        start_at=len(chunk_citations),
    )
    citations = chunk_citations + disclosure_citations
    answer_sentences = (
        tuple(
            AnswerSentence(
                sentence_id=sentence.sentence_id,
                text=sentence.text,
                citation_ids=chunk_sentence_ids.get(sentence.sentence_id, ()),
            )
            for sentence in emitted_sentences
        )
        + disclosure_sentences
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
                    attempts,
                )

    result_trace = ResultTrace(
        state=QueryState.ANSWERED,
        abstention_stage=None,
        citations=tuple(citation.citation_id for citation in citations),
        stale_markers=tuple(
            citation.citation_id
            for citation in citations
            if citation.freshness == CitationFreshness.STALE_VERSION
        ),
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
        schema_version=2,
        state=QueryState.ANSWERED,
        exit_code=EXIT_OK,
        sentences=answer_sentences,
        citations=citations,
        freshness=freshness.state,
        abstention_stage=None,
        trace=trace,
        failure=None,
    )


def _lexical_stage(
    question: str,
    accepted_by_id: dict[str, ActiveChunkDescriptor],
    scorer: LexicalScorer,
) -> tuple[LexicalTrace, dict[str, int]]:
    """BM25 over accepted chunk text, returning the trace and ranked ids (AC-5).

    Dispositions use the fixed precedence: no query token intersects the chunk
    tokens gives ``no_term_match``; a score at or below zero gives
    ``nonpositive_score``; positive rows sort by score descending then chunk id
    and receive ranks starting at 1, with ranks 1 through 24 ``ranked`` and
    later positive ranks ``outside_top_24``. Only ``ranked`` rows contribute to
    fusion.
    """
    ordered = sorted(accepted_by_id.values(), key=lambda chunk: chunk.chunk_id)
    query_tokens = tokenize(question)
    document_tokens = [tokenize(chunk.text) for chunk in ordered]
    scores = list(scorer(query_tokens, document_tokens))
    if len(scores) != len(ordered):
        raise ValueError("lexical scorer returned a wrong count")
    rows: list[LexicalRow] = []
    positive: list[tuple[ActiveChunkDescriptor, float]] = []
    for chunk, score, doc_tokens in zip(ordered, scores, document_tokens, strict=True):
        if not isinstance(score, (int, float)) or not math.isfinite(score):
            raise ValueError(f"nonfinite lexical score for {chunk.chunk_id}")
        value = float(score)
        if not query_tokens or not (set(query_tokens) & set(doc_tokens)):
            rows.append(
                LexicalRow(
                    chunk.chunk_id, value, None, LexicalDisposition.NO_TERM_MATCH
                )
            )
        elif value <= 0.0:
            rows.append(
                LexicalRow(
                    chunk.chunk_id, value, None, LexicalDisposition.NONPOSITIVE_SCORE
                )
            )
        else:
            positive.append((chunk, value))
    positive.sort(key=lambda pair: (-pair[1], pair[0].chunk_id))
    ranked: dict[str, int] = {}
    for rank, (chunk, score) in enumerate(positive, start=1):
        disposition = (
            LexicalDisposition.RANKED
            if rank <= CANDIDATE_LIMIT
            else LexicalDisposition.OUTSIDE_TOP_24
        )
        if disposition == LexicalDisposition.RANKED:
            # Only ranked rows (ranks 1 through 24) contribute to fusion
            # (AC-5), symmetric with the semantic stage below.
            ranked[chunk.chunk_id] = rank
        rows.append(LexicalRow(chunk.chunk_id, score, rank, disposition))
    rows.sort(key=lambda row: row.chunk_id)
    return LexicalTrace(rows=tuple(rows)), ranked


def _fusion_stage(
    ranked_lexical: dict[str, int],
    ranked_semantic: dict[str, int],
    accepted_by_id: dict[str, ActiveChunkDescriptor],
) -> list[FusedCandidate]:
    """Reciprocal rank fusion over the ranked union (AC-7).

    For each chunk, ``fused_score`` is the sum of ``1 / (60 + rank)`` for each
    present contribution; a missing contribution adds zero. Fused candidates
    sort by score descending then chunk id. No raw score normalization or cross
    scale comparison occurs. The returned candidates carry placeholder
    diversity facts that the diversity stage replaces.
    """
    chunk_ids = sorted(set(ranked_lexical) | set(ranked_semantic))
    scored: list[tuple[str, float, int | None, int | None]] = []
    for chunk_id in chunk_ids:
        lexical_rank = ranked_lexical.get(chunk_id)
        semantic_rank = ranked_semantic.get(chunk_id)
        fused = 0.0
        if lexical_rank is not None:
            fused += 1.0 / (RRF_CONSTANT + lexical_rank)
        if semantic_rank is not None:
            fused += 1.0 / (RRF_CONSTANT + semantic_rank)
        scored.append((chunk_id, fused, lexical_rank, semantic_rank))
    scored.sort(key=lambda item: (-item[1], item[0]))
    candidates: list[FusedCandidate] = []
    for fused_rank, (chunk_id, fused, lexical_rank, semantic_rank) in enumerate(
        scored, start=1
    ):
        chunk = accepted_by_id[chunk_id]
        candidates.append(
            FusedCandidate(
                chunk_id=chunk_id,
                record_id=chunk.record_id,
                value_path=chunk.value_path,
                fingerprint=chunk.fingerprint,
                ordinal=chunk.ordinal,
                text=chunk.text,
                provenance=chunk.provenance,
                lexical_rank=lexical_rank,
                semantic_rank=semantic_rank,
                fused_score=fused,
                fused_rank=fused_rank,
                breadth_disposition=BreadthDisposition.RECORD_CAP,
                selection_pass=None,
                final_rank=None,
                final_disposition=FinalDisposition.OUTSIDE_TOP_8,
            )
        )
    return candidates


def _diversity_stage(
    candidates: Sequence[FusedCandidate],
    accepted_by_id: dict[str, ActiveChunkDescriptor],
) -> tuple[list[FusedCandidate], list[ActiveChunkDescriptor]]:
    """Two pass record diversity, returning final candidates and accepts (AC-8).

    The breadth pass walks fused rank from 1 upward, accepting at most two per
    record. A candidate at the record cap is deferred with ``record_cap``. As
    soon as eight are accepted, every unvisited candidate gets
    ``accepted_limit_reached``. If breadth exhausts the input below eight, the
    fill pass revisits only deferred rows in fused order and accepts them until
    eight or exhaustion. Accepted chunks come back in final rank (append)
    order.
    """
    states: list[
        tuple[FusedCandidate, BreadthDisposition, SelectionPass | None, int | None]
    ] = []
    accepted_count = 0
    record_counts: dict[str, int] = {}
    deferred: list[int] = []
    for candidate in candidates:
        if accepted_count >= ACCEPTED_LIMIT:
            states.append(
                (candidate, BreadthDisposition.ACCEPTED_LIMIT_REACHED, None, None)
            )
            continue
        record_count = record_counts.get(candidate.record_id, 0)
        if record_count >= DIVERSITY_CAP:
            deferred.append(len(states))
            states.append((candidate, BreadthDisposition.RECORD_CAP, None, None))
            continue
        accepted_count += 1
        record_counts[candidate.record_id] = record_count + 1
        states.append(
            (
                candidate,
                BreadthDisposition.ACCEPTED,
                SelectionPass.BREADTH,
                accepted_count,
            )
        )
    for index in deferred:
        if accepted_count >= ACCEPTED_LIMIT:
            break
        candidate, breadth, _selection_pass, _final_rank = states[index]
        accepted_count += 1
        states[index] = (candidate, breadth, SelectionPass.FILL, accepted_count)
    final_candidates = [
        FusedCandidate(
            chunk_id=candidate.chunk_id,
            record_id=candidate.record_id,
            value_path=candidate.value_path,
            fingerprint=candidate.fingerprint,
            ordinal=candidate.ordinal,
            text=candidate.text,
            provenance=candidate.provenance,
            lexical_rank=candidate.lexical_rank,
            semantic_rank=candidate.semantic_rank,
            fused_score=candidate.fused_score,
            fused_rank=candidate.fused_rank,
            breadth_disposition=breadth,
            selection_pass=selection_pass,
            final_rank=final_rank,
            final_disposition=(
                FinalDisposition.ACCEPTED
                if final_rank is not None
                else FinalDisposition.OUTSIDE_TOP_8
            ),
        )
        for candidate, breadth, selection_pass, final_rank in states
    ]
    accepted = sorted(
        (final_rank, candidate.chunk_id)
        for candidate, _breadth, _selection_pass, final_rank in states
        if final_rank is not None
    )
    accepted_chunks = [accepted_by_id[chunk_id] for _final_rank, chunk_id in accepted]
    return final_candidates, accepted_chunks


def _allocate_citations(
    sentences: Sequence[DraftSentence],
    chunk_by_id: dict[str, ActiveChunkDescriptor],
    stale_record_ids: frozenset[str] = frozenset(),
    resolve_source: Callable[[str], ResolutionState] | None = None,
) -> tuple[tuple[Citation, ...], dict[str, tuple[str, ...]]]:
    """Allocate C1.. by first sentence use, deduplicating by source location."""
    if resolve_source is None:
        resolve_source = _unresolved
    citations: list[Citation] = []
    seen: dict[tuple[str, str, str, str], str] = {}
    sentence_ids: dict[str, tuple[str, ...]] = {}
    for sentence in sentences:
        ids: list[str] = []
        for chunk_id in sentence.chunk_ids:
            chunk = chunk_by_id.get(chunk_id)
            if chunk is None:
                continue
            for source in chunk.provenance:
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
                        resolution=resolve_source(source.path),
                        freshness=freshness,
                    )
                )
                ids.append(citation_id)
        ids.sort(key=lambda value: int(value[1:]))
        sentence_ids[sentence.sentence_id] = tuple(ids)
    return tuple(citations), sentence_ids


def _unresolved(_path: str) -> ResolutionState:
    """The fallback resolver when none is injected: no hint is available."""
    return ResolutionState.HINT_UNAVAILABLE


def _collect_notices(
    store: IndexReader, accepted: Sequence[ActiveChunkDescriptor]
) -> tuple[SupersessionNotice, ...]:
    """Immediate eligible successors of every retrieved predecessor record (AC-18)."""
    collected: list[SupersessionNotice] = []
    seen: set[tuple[str, str]] = set()
    for record_id in sorted({chunk.record_id for chunk in accepted}):
        for notice in store.supersession_notices(record_id):
            key = (notice.predecessor_id, notice.successor_id)
            if key not in seen:
                seen.add(key)
                collected.append(notice)
    return tuple(sorted(collected, key=lambda n: (n.successor_id, n.predecessor_id)))


def _render_disclosures(
    manifest: Manifest | None,
    notices: Sequence[SupersessionNotice],
    resolve_source: Callable[[str], ResolutionState],
    stale_record_ids: frozenset[str],
    start_at: int,
) -> tuple[tuple[AnswerSentence, ...], tuple[Citation, ...]]:
    """Deterministic disclosure sentences citing successor supersedes evidence.

    Disclosure does not depend on model output: each notice renders one
    sentence naming the successor by title and id, sorted by successor id,
    and cites the successor's stored ``supersedes`` provenance (AC-18).
    """
    if not notices:
        return (), ()
    manifest_by_id = (
        {entry.id: entry for entry in manifest.entries} if manifest is not None else {}
    )
    sentences: list[AnswerSentence] = []
    citations: list[Citation] = []
    for index, notice in enumerate(
        sorted(notices, key=lambda n: (n.successor_id, n.predecessor_id)), start=1
    ):
        entry = manifest_by_id.get(notice.successor_id)
        sources = (
            (entry.field_sources or {}).get("supersedes", ())
            if entry is not None
            else ()
        )
        source = sources[0] if sources else SourceReference("", "")
        freshness = (
            CitationFreshness.STALE_VERSION
            if notice.successor_id in stale_record_ids
            else CitationFreshness.CURRENT
        )
        citation_id = f"C{start_at + len(citations) + 1}"
        citations.append(
            Citation(
                citation_id=citation_id,
                kind=CitationKind.SUPERSESSION,
                evidence_id=notice.metadata_evidence_id,
                record_id=notice.successor_id,
                chunk_id=None,
                value_path="supersedes",
                relative_path=source.path,
                section=source.section,
                resolution=(
                    resolve_source(source.path)
                    if source.path
                    else ResolutionState.HINT_UNAVAILABLE
                ),
                freshness=freshness,
            )
        )
        sentences.append(
            AnswerSentence(
                sentence_id=f"D{index}",
                text=(
                    f"This decision was later changed by {notice.successor_title} "
                    f"({notice.successor_id})."
                ),
                citation_ids=(citation_id,),
            )
        )
    return tuple(sentences), tuple(citations)


def _retrieval_settings() -> RetrievalSettings:
    """The fixed retrieval settings recorded in every trace (AC-10)."""
    return RetrievalSettings(
        tokenizer_version=LEXICAL_TOKENIZER_VERSION,
        stopword_set=STOPWORD_SET,
        stopword_digest=STOPWORD_DIGEST,
        bm25_variant=BM25_VARIANT,
        bm25_parameters=BM25_PARAMETERS,
        lexical_limit=CANDIDATE_LIMIT,
        semantic_limit=CANDIDATE_LIMIT,
        rrf_constant=RRF_CONSTANT,
        accepted_limit=ACCEPTED_LIMIT,
        diversity_cap=DIVERSITY_CAP,
        collection_metric=COLLECTION_METRIC,
        relevance_floor=None,
    )


def _retrieval_with_filter(filter_trace: FilterTrace) -> RetrievalTrace:
    """A retrieval trace with only the filter section completed (AC-4)."""
    return RetrievalTrace(
        filters=filter_trace,
        lexical=LexicalTrace(rows=()),
        semantic=SemanticTrace(rows=()),
        fusion=FusionTrace(candidates=()),
        diversity=DiversityTrace(
            accepted_chunk_ids=(),
            accepted_limit=ACCEPTED_LIMIT,
            record_cap=DIVERSITY_CAP,
        ),
        settings=_retrieval_settings(),
    )


def _empty_retrieval() -> RetrievalTrace:
    return _retrieval_with_filter(FilterTrace(rows=()))


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
        decomposed=(),
        empty_decompositions=(),
        rejected_decompositions=(),
        dropped_sentences=(),
        missing_chunk_refs=(),
    )


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
    ledger = deps.store.ledger_entry_digests()
    manifest_ids = {entry.id for entry in manifest.entries}
    for entry in manifest.entries:
        if entry.id not in ledger:
            reasons.append(StaleReason.RECORD_ADDED)
        elif ledger[entry.id] != entry.entry_digest:
            reasons.append(StaleReason.RECORD_CHANGED)
    for record_id in ledger:
        if record_id not in manifest_ids:
            reasons.append(StaleReason.RECORD_REMOVED)
    if deps.store.has_failed_records():
        reasons.append(StaleReason.FAILED_INGEST)
    unique = sorted(set(reasons), key=lambda reason: reason.value)
    return FreshnessState.DRIFT, tuple(unique)


def _with_stale_reason(trace: FreshnessTrace, reason: StaleReason) -> FreshnessTrace:
    return FreshnessTrace(
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
    attempts: list[ProviderAttempt] | None = None,
) -> QueryResult:
    trace = QueryTrace(
        freshness=freshness,
        retrieval=retrieval,
        generation=generation or _empty_generation(),
        verification=verification or _empty_verification(),
        providers=tuple(attempts) if attempts else (),
        result=ResultTrace(
            state=QueryState.ABSTAINED,
            abstention_stage=stage,
            citations=(),
            stale_markers=(),
        ),
    )
    return QueryResult(
        schema_version=2,
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
    attempts: list[ProviderAttempt] | None = None,
) -> QueryResult:
    trace = QueryTrace(
        freshness=freshness,
        retrieval=_empty_retrieval(),
        generation=_empty_generation(),
        verification=_empty_verification(),
        providers=tuple(attempts) if attempts else (),
        result=ResultTrace(
            state=QueryState.FAILED,
            abstention_stage=None,
            citations=(),
            stale_markers=(),
        ),
    )
    return QueryResult(
        schema_version=2,
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
