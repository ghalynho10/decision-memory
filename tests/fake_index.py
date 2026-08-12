"""Shared fakes for ingest and query tests (spec 0007 AC-11 deterministic lock).

``FakeIndex`` implements both the application ``IndexWriter`` and ``IndexReader``
protocols in memory, so the full ingest to query path runs without Chroma or
OpenAI. The fake embedder returns deterministic vectors, so distances and
ordering are stable across runs. The fake generation callables produce the
AC-11 structured propositions against the accepted chunk ids, which the
pipeline keeps and cites.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from decision_memory.application.dto import (
    ActiveChunkDescriptor,
    ChunkPlan,
    CoverageRow,
    DraftSentence,
    Facet,
    SemanticMatches,
    SupersessionNotice,
)
from decision_memory.application.pipeline import pipeline_signature
from decision_memory.domain.records import CanonicalDecisionRecord


def fake_embed(
    texts: Sequence[str], attempts: list[object] | None = None
) -> list[list[float]]:
    """A deterministic vector per text, stable across runs and processes.

    Accepts the optional provider-attempts list so it satisfies both
    ``IngestDependencies.embed`` (single arg) and
    ``QueryDependencies.embed`` (texts plus attempts); it has no real
    provider round trip to record, so the list is left untouched.
    """
    vectors: list[list[float]] = []
    for text in texts:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        value = int.from_bytes(digest[:8], "big") / 2**64
        vectors.append([value] * 8)
    return vectors


def _cosine_distance(left: Sequence[float], right: Sequence[float]) -> float:
    dot = sum(a * b for a, b in zip(left, right, strict=False))
    norm_left = sum(a * a for a in left) ** 0.5
    norm_right = sum(b * b for b in right) ** 0.5
    if norm_left == 0 or norm_right == 0:
        return 1.0
    # Clamp at zero so floating point noise never yields a negative distance,
    # which the strict application check would reject as store failure.
    return max(0.0, 1.0 - dot / (norm_left * norm_right))


class FakeIndex:
    """An in memory index satisfying IndexWriter and IndexReader."""

    def __init__(self) -> None:
        self.generation: str | None = None
        self.chunks: dict[str, ActiveChunkDescriptor] = {}
        self.embeddings: dict[str, list[float]] = {}
        self.record_states: dict[str, tuple[str, str | None, str | None]] = {}
        self.manifest_meta: tuple[str | None, str | None, str | None, str | None] = (
            None,
            None,
            None,
            None,
        )
        self.deleted_vectors: set[str] = set()
        self.supersession_notices_map: dict[str, list[SupersessionNotice]] = {}
        self.entry_digests: dict[str, str | None] = {}
        self.signature = pipeline_signature()
        self.parity_problems_list: list[str] = []
        self.semantic_error: Exception | None = None
        self.store_format_value = 2
        self.empty_eligible = False

    # -- IndexWriter -----------------------------------------------------
    def open_generation(self, force_rebuild: bool) -> str:
        if force_rebuild or self.generation is None:
            self.generation = "gen-fake"
            if force_rebuild:
                self.chunks = {}
                self.embeddings = {}
                self.record_states = {}
                self.entry_digests = {}
                self.deleted_vectors = set()
        return self.generation

    def existing_states(self) -> dict[str, tuple[str, str | None, str | None]]:
        return dict(self.record_states)

    def active_pipeline_signature(self) -> str | None:
        return self.signature if self.generation is not None else None

    def write_record(
        self,
        generation_id: str,
        record: CanonicalDecisionRecord,
        chunks: Sequence[ChunkPlan],
        embeddings: Sequence[Sequence[float]],
        entry_digest: str,
    ) -> list[str]:
        record_id = record.id
        old_ids = [
            chunk_id
            for chunk_id, chunk in self.chunks.items()
            if chunk.record_id == record_id
        ]
        for chunk, embedding in zip(chunks, embeddings, strict=False):
            self.chunks[chunk.chunk_id] = ActiveChunkDescriptor(
                chunk_id=chunk.chunk_id,
                record_id=chunk.record_id,
                record_title=record.title or "",
                record_status=record.status.value if record.status else None,
                record_tags=tuple(sorted(record.tags)),
                value_path=chunk.value_path,
                fingerprint=chunk.fingerprint,
                ordinal=chunk.ordinal,
                text=chunk.text,
                provenance=tuple(chunk.sources),
            )
            self.embeddings[chunk.chunk_id] = list(embedding)
        fingerprint = chunks[0].fingerprint if chunks else None
        if record_id is not None:
            self.record_states[record_id] = ("current", fingerprint, fingerprint)
            self.entry_digests[record_id] = entry_digest
        return old_ids

    def mark_pending_removal(self, record_id: str) -> None:
        state, desired, active = self.record_states.get(
            record_id, ("current", None, None)
        )
        self.record_states[record_id] = ("pending_removal", desired, active)

    def mark_failed(
        self,
        record_id: str,
        desired_fingerprint: str,
        active_fingerprint: str | None,
        failure_code: str,
        entry_digest: str | None = None,
    ) -> None:
        self.record_states[record_id] = (
            "failed",
            desired_fingerprint,
            active_fingerprint,
        )
        self.entry_digests[record_id] = entry_digest

    def remove_record(
        self, generation_id: str, record_id: str, prior_fingerprint: str | None
    ) -> None:
        self.record_states[record_id] = ("removed", prior_fingerprint, None)
        for chunk_id in [
            chunk_id
            for chunk_id, chunk in self.chunks.items()
            if chunk.record_id == record_id
        ]:
            del self.chunks[chunk_id]
            self.embeddings.pop(chunk_id, None)

    def delete_vectors(self, chunk_ids: Sequence[str]) -> None:
        """Chroma only; the fake merges stores, so record the call only."""
        self.deleted_vectors.update(chunk_ids)

    def cleanup_orphans(self, generation_id: str) -> None:
        return None

    def set_manifest_metadata(
        self,
        records_manifest_path: str,
        semantic_digest: str,
        raw_digest: str,
        source_root_hint: str,
    ) -> None:
        self.manifest_meta = (
            records_manifest_path,
            semantic_digest,
            raw_digest,
            source_root_hint,
        )

    def derive_supersessions(self) -> list[str]:
        # The fake does not derive links from snapshots; tests seed the map.
        return []

    def activate(self, generation_id: str) -> list[str]:
        return list(self.parity_problems_list)

    # -- IndexReader -----------------------------------------------------
    def pipeline_signature(self) -> str:
        return self.signature

    def generation_id(self) -> str | None:
        return self.generation

    def parity_problems(self) -> list[str]:
        return list(self.parity_problems_list)

    def manifest_metadata(
        self,
    ) -> tuple[str | None, str | None, str | None, str | None]:
        return self.manifest_meta

    def ledger_fingerprints(self) -> dict[str, str | None]:
        return {
            record_id: desired
            for record_id, (state, desired, _active) in self.record_states.items()
            if state != "removed"
        }

    def ledger_entry_digests(self) -> dict[str, str | None]:
        return {
            record_id: digest
            for record_id, (state, _desired, _active) in self.record_states.items()
            if state != "removed"
            for digest in (self.entry_digests.get(record_id),)
        }

    def has_failed_records(self) -> bool:
        return any(
            state == "failed"
            for state, _desired, _active in self.record_states.values()
        )

    def active_fingerprint(self, record_id: str) -> str | None:
        for chunk in self.chunks.values():
            if chunk.record_id == record_id:
                return chunk.fingerprint
        return None

    def supersession_notices(
        self, predecessor_id: str
    ) -> tuple[SupersessionNotice, ...]:
        return tuple(self.supersession_notices_map.get(predecessor_id, ()))

    def active_chunks(self) -> tuple[ActiveChunkDescriptor, ...]:
        return tuple(sorted(self.chunks.values(), key=lambda chunk: chunk.chunk_id))

    def eligible_tuples(self) -> tuple[tuple[str, str, str], ...]:
        if self.empty_eligible:
            return ()
        tuples: list[tuple[str, str, str]] = []
        for chunk in self.chunks.values():
            candidate = (self.generation or "", chunk.record_id, chunk.fingerprint)
            if candidate not in tuples:
                tuples.append(candidate)
        return tuple(tuples)

    def store_format(self) -> int | None:
        return self.store_format_value

    def semantic_search(
        self,
        embedding: Sequence[float],
        accepted_chunk_ids: Sequence[str],
    ) -> SemanticMatches:
        if self.semantic_error is not None:
            raise self.semantic_error
        accepted = set(accepted_chunk_ids)
        scored: list[tuple[str, float]] = []
        for chunk_id, chunk_embedding in self.embeddings.items():
            if chunk_id in accepted and chunk_id in self.chunks:
                scored.append((chunk_id, _cosine_distance(embedding, chunk_embedding)))
        scored.sort(key=lambda pair: (pair[1], pair[0]))
        return SemanticMatches(
            ids=tuple(chunk_id for chunk_id, _distance in scored),
            distances=tuple(distance for _chunk_id, distance in scored),
        )


def fake_extract_facets(question: str, attempts=None) -> tuple[Facet, ...]:
    return (
        Facet("F1", "Why was the private beta access gate added?"),
        Facet("F2", "Which routes does the gate cover?"),
        Facet("F3", "What was the alternative?"),
    )


def fake_generate_answer(
    facets, chunk_texts, chunk_ids, notices, known_ids, attempts=None
) -> tuple[DraftSentence, ...]:
    """The AC-11 structured propositions, cited to real accepted chunks."""
    ids = sorted(known_ids)
    if not ids:
        return ()
    chunk = ids[0]
    return (
        DraftSentence(
            "S1",
            "The private beta access gate was added to protect the portfolio "
            "before it goes public.",
            (chunk,),
        ),
        DraftSentence("S2", "Panel 1 decided which routes the gate covers.", (chunk,)),
        DraftSentence("S3", "Option B covering all four routes was chosen.", (chunk,)),
        DraftSentence(
            "S4",
            "Option A, The two agent routes only (the original proposal), "
            "was rejected.",
            (chunk,),
        ),
    )


def fake_entail(sentence, chunk_texts, attempts=None) -> tuple[bool, str]:
    return (True, "direct support")


def fake_decompose(sentence_text, chunk_texts, attempts=None) -> tuple[str, ...]:
    """An under split: the whole sentence as a single sub claim.

    Combined with ``fake_entail`` returning supported, every non verbatim
    sentence survives as one fragment carrying a sub claim id. The parent
    sentence is never re emitted after decomposition (spec 0010 AC-4).
    """
    return (sentence_text,)


def fake_coverage(
    question, facets, sentences, attempts=None
) -> tuple[CoverageRow, ...]:
    sentence_ids = tuple(sentence.sentence_id for sentence in sentences)
    return tuple(
        CoverageRow(facet.facet_id, True, "covered", sentence_ids) for facet in facets
    )
