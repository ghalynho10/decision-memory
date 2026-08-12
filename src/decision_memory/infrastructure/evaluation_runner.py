"""Infrastructure: the live evaluation runner (feature 11, Slice 3).

Wires the real pipeline against a corpus and a built store so the pure
evaluation engine can run the fixed battery end to end. ``EvaluationRunner``
implements the application ``EvaluationPort``: it adapts the corpus into
canonical records, ingests them into a store, runs live queries with the real
providers, derives the proposed record ids from the records themselves, and
runs the incremental re ingest assertion on an isolated copy so the user's
corpus is never mutated.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from decision_memory.application.adapter import (
    EXIT_ERROR,
    AdaptOutcome,
    Manifest,
    adapt_corpus,
)
from decision_memory.application.dto import (
    Failure,
    IngestRequest,
    IngestResult,
    IngestState,
    QueryFilters,
    QueryRequest,
    QueryResult,
)
from decision_memory.application.evaluation import ReingestEvidence
from decision_memory.application.ingest import IngestDependencies, ingest_records
from decision_memory.application.query import QueryDependencies, query_index
from decision_memory.domain.records import Status
from decision_memory.infrastructure.bm25 import bm25_lexical_scorer
from decision_memory.infrastructure.file_reader import (
    parse_record_file,
    write_record_file,
)
from decision_memory.infrastructure.index_lock import LockError, store_lock
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

# The distinctive sentence appended to a rationale copy by the incremental
# re ingest assertion. It must change the record's fingerprint and chunks.
_REINGEST_PROBE = (
    "\n\nEvaluation re-ingest probe: this sentence is appended to test "
    "that an edited rationale.md reaches the index on re-ingest.\n"
)


class EvaluationRunner:
    """The live ``EvaluationPort`` over one corpus and one store."""

    def __init__(self, corpus_root: Path, records_dir: Path, store_dir: Path) -> None:
        self.corpus_root = corpus_root
        self.records_dir = records_dir
        self.store_dir = store_dir

    def adapt(self) -> AdaptOutcome:
        """Adapt the corpus into canonical records at ``records_dir``."""
        return adapt_corpus(
            self.corpus_root,
            JsmasteryAdapter(),
            write_record_file,
            output=self.records_dir,
        )

    def ingest(self, rebuild: bool) -> IngestResult:
        """Ingest the records into ``store_dir`` (rebuild or incremental).

        Holds the same exclusive store lock the live ``ingest`` command holds
        (AGENTS.md's clean architecture rule aside, this mirrors cli.py's
        ``ingest_command`` so the harness proves the concurrency protocol
        too). A lock conflict is reported as a failed result rather than an
        escaped exception, so one locked fixture cannot abort the battery.
        """
        writer = SqliteChromaIndexWriter(self.store_dir)
        try:
            with store_lock(self.store_dir, exclusive=True):
                return ingest_records(
                    IngestRequest(
                        records_dir=self.records_dir,
                        store_dir=self.store_dir,
                        rebuild=rebuild,
                        dry_run=False,
                    ),
                    IngestDependencies(
                        load_manifest=lambda: load_manifest(
                            manifest_path(self.records_dir)
                        ),
                        read_record=record_loader(self.records_dir),
                        count_tokens=tiktoken_count,
                        embed=embed_texts,
                        raw_manifest_digest=lambda: raw_manifest_digest(
                            manifest_path(self.records_dir)
                        ),
                        require_api_key=require_api_key,
                        store=writer,
                    ),
                )
        except LockError as exc:
            return IngestResult(
                schema_version=1,
                state=IngestState.FAILED,
                exit_code=EXIT_ERROR,
                store_path=self.store_dir,
                semantic_manifest_digest=None,
                raw_manifest_digest=None,
                records=(),
                provider_attempts=0,
                failure=Failure("lock.conflict", "lock", str(exc)),
            )
        finally:
            writer.close()

    def run_query(self, question: str) -> QueryResult:
        """Run one live query against the built store.

        Holds the same shared store lock the live ``query`` command holds, so
        the harness proves the exact concurrency protocol, not a version of
        the pipeline missing it. Both ``RetrievalFailure`` and ``LockError``
        propagate uncaught, matching ``query_index``'s and ``store_lock``'s
        own contracts. ``RetrievalFailure`` is an application DTO, so the
        application evaluation engine catches it and turns it into a legible
        failed fixture (per Clean Architecture's dependency rule, this
        infrastructure adapter must not import ``LockError`` to do the same);
        ``LockError`` propagates all the way to the CLI command, which is
        where it is caught.
        """
        reader = SqliteChromaIndexReader(self.store_dir)

        def _stored_manifest_path() -> Path | None:
            stored = reader.manifest_metadata()[0]
            return Path(stored) if stored else None

        def _load_stored_manifest() -> Manifest:
            path = _stored_manifest_path()
            if path is None:
                raise FileNotFoundError("no stored manifest path")
            return load_manifest(path)

        def _stored_manifest_raw_digest() -> str:
            path = _stored_manifest_path()
            if path is None:
                raise FileNotFoundError("no stored manifest path")
            return raw_manifest_digest(path)

        def _stored_hint() -> str | None:
            return reader.manifest_metadata()[3]

        with store_lock(self.store_dir, exclusive=False):
            return query_index(
                QueryRequest(
                    question=question,
                    store_dir=self.store_dir,
                    allow_stale=False,
                    filters=QueryFilters(),
                ),
                QueryDependencies(
                    store=reader,
                    count_tokens=tiktoken_count,
                    embed=embed_texts,
                    lexical_scorer=bm25_lexical_scorer,
                    load_manifest=_load_stored_manifest,
                    raw_manifest_digest=_stored_manifest_raw_digest,
                    resolve_source=lambda path: resolve_source_path(
                        path, _stored_hint()
                    ),
                    extract_facets=extract_facets,
                    generate_answer=generate_answer,
                    entail=entail_verdict,
                    coverage=coverage_verdict,
                ),
            )

    def proposed_record_ids(self) -> frozenset[str]:
        """Every record id whose canonical status is proposed.

        Reads the adapted records directory, so the query 3 oracle derives
        from the records themselves instead of a hardcoded id. A record that
        failed to parse, or parsed without an id, is skipped rather than
        raised: this runs once at the start of the whole battery (not inside
        a single fixture), so an exception here would crash every fixture,
        not just query 3. The oracle itself (``_satisfies`` in
        ``application/evaluation.py``) is where an empty proposed set is
        turned into a named, legible failure instead of a vacuous pass.
        """
        ids: set[str] = set()
        for path in self.records_dir.glob("*.md"):
            parsed = parse_record_file(path)
            if (
                parsed.record is not None
                and parsed.record.status == Status.PROPOSED
                and parsed.record.id is not None
            ):
                ids.add(parsed.record.id)
        return frozenset(ids)

    def run_reingest(self, record_id: str, rationale_relpath: str) -> ReingestEvidence:
        """Edit a rationale.md copy, re adapt, re ingest, and compare chunks.

        Operates on an isolated copy of the corpus's ``docs/specs`` tree so
        the user's real corpus is never mutated (see
        ``test_evaluation_runner.py`` for the isolation regression lock). The
        assertion passes only when the target record has active chunks both
        before and after the edit and the two sets differ; a record that
        drops to zero chunks after the edit is a distinct, named failure, not
        a pass, because that would prove the record left the index rather
        than that it updated in place.
        """
        source = self.corpus_root / rationale_relpath
        if not source.is_file():
            return ReingestEvidence(False, f"no such corpus file: {rationale_relpath}")
        with tempfile.TemporaryDirectory(prefix="decision-memory-evaluate-") as tmp:
            workspace = Path(tmp)
            specs_root = workspace / "docs" / "specs"
            specs_root.mkdir(parents=True)
            spec_dir = source.parent
            shutil.copytree(spec_dir, specs_root / spec_dir.name)

            records_dir = workspace / "records"
            store_dir = workspace / "store"
            runner = EvaluationRunner(workspace, records_dir, store_dir)

            adapt_outcome = runner.adapt()
            if adapt_outcome.exit_code != 0:
                return ReingestEvidence(False, "adapt of the copy failed")
            ingest_outcome = runner.ingest(rebuild=True)
            if ingest_outcome.exit_code != 0:
                return ReingestEvidence(False, "initial ingest of the copy failed")

            before = self._chunk_ids(store_dir, record_id)

            rationale = specs_root / spec_dir.name / "rationale.md"
            with rationale.open("a", encoding="utf-8") as handle:
                handle.write(_REINGEST_PROBE)

            adapt_again = runner.adapt()
            if adapt_again.exit_code != 0:
                return ReingestEvidence(False, "re adapt of the copy failed")
            ingest_again = runner.ingest(rebuild=False)
            if ingest_again.exit_code != 0:
                return ReingestEvidence(False, "re ingest of the copy failed")

            after = self._chunk_ids(store_dir, record_id)
            if not before:
                return ReingestEvidence(
                    False, f"record {record_id} had no active chunks"
                )
            if not after:
                return ReingestEvidence(
                    False,
                    f"record {record_id} had {len(before)} active chunks before "
                    "the edit and none after; the record dropped out of the "
                    "index instead of updating",
                )
            if before != after:
                return ReingestEvidence(
                    True,
                    f"record {record_id} chunks changed after the rationale.md edit "
                    f"({len(before)} -> {len(after)} chunk ids)",
                )
            return ReingestEvidence(
                False,
                f"record {record_id} chunks did not change after the rationale.md edit",
            )

    @staticmethod
    def _chunk_ids(store_dir: Path, record_id: str) -> frozenset[str]:
        """The active chunk ids belonging to one record."""
        reader = SqliteChromaIndexReader(store_dir)
        return frozenset(
            descriptor.chunk_id
            for descriptor in reader.active_chunks()
            if descriptor.record_id == record_id
        )
