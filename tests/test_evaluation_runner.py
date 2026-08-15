"""Unit tests for the live evaluation runner's re-ingest orchestration.

``run_reingest`` (temp copy, two adapt/ingest cycles, four failure branches,
and the "never mutates the user's corpus" safety property) had no test at
any level: the integration suite only asserts ``check.detail`` is non-empty.
These tests pin the isolation property and every failure branch, and the
false-positive a review round caught (the oracle used to pass when the
record's chunks dropped to zero), entirely through monkeypatched
adapt/ingest/chunk-id seams, so nothing hits OpenAI or a real Chroma store.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path
from types import SimpleNamespace

import pytest
from spec_factory import make_corpus, write_spec

# The engine's own trace builder, reused rather than duplicated: this file
# needs a valid QueryResult only as the writer's input.
from test_evaluation import _empty_trace as make_empty_query_trace

from decision_memory.application.dto import (
    AbstentionStage,
    FreshnessState,
    IngestState,
    QueryResult,
    QueryState,
)
from decision_memory.domain.records import CanonicalDecisionRecord, Status
from decision_memory.infrastructure.evaluation_runner import EvaluationRunner
from decision_memory.infrastructure.file_reader import write_record_file
from decision_memory.infrastructure.index_lock import store_lock


def _corpus_with_one_spec(tmp_path: Path) -> tuple[Path, Path]:
    """A throwaway corpus with one spec dir; returns (corpus, its rationale.md)."""
    corpus = make_corpus(tmp_path)
    spec_dir = write_spec(corpus, "0001-test")
    return corpus, spec_dir / "rationale.md"


def _script(
    monkeypatch: pytest.MonkeyPatch,
    *,
    adapt_exit_codes: Iterable[int] = (0, 0),
    ingest_exit_codes: Iterable[int] = (0, 0),
    chunk_ids: Iterable[frozenset[str]] = (frozenset(), frozenset()),
) -> None:
    """Script the adapt/ingest/chunk-id seams so no network or real store is touched.

    Each iterable supplies one value per call, in call order (first the
    initial adapt/ingest, then the re adapt/ingest after the probe edit).
    """
    adapt_codes = iter(adapt_exit_codes)
    ingest_codes = iter(ingest_exit_codes)
    chunk_responses = iter(chunk_ids)
    monkeypatch.setattr(
        EvaluationRunner,
        "adapt",
        lambda self: SimpleNamespace(exit_code=next(adapt_codes)),
    )
    monkeypatch.setattr(
        EvaluationRunner,
        "ingest",
        lambda self, rebuild: SimpleNamespace(exit_code=next(ingest_codes)),
    )
    monkeypatch.setattr(
        EvaluationRunner,
        "_chunk_ids",
        staticmethod(lambda store_dir, record_id: next(chunk_responses)),
    )


def test_ingest_returns_a_legible_failure_on_a_lock_conflict(
    tmp_path: Path,
) -> None:
    """A concurrent lock holder must not crash ingest with an unhandled LockError.

    ``ingest`` now holds the same exclusive store lock the live ``ingest``
    command holds; a conflict must surface as a normal failed IngestResult,
    the shape every caller (including run_reingest) already checks via
    exit_code, not an escaped exception.
    """
    corpus = make_corpus(tmp_path)
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    store_dir = tmp_path / "store"
    runner = EvaluationRunner(corpus, records_dir, store_dir)

    with store_lock(store_dir, exclusive=True):
        result = runner.ingest(rebuild=True)

    assert result.exit_code != 0
    assert result.state == IngestState.FAILED
    assert result.failure is not None
    assert result.failure.code == "lock.conflict"


def test_run_reingest_never_mutates_the_source_rationale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The source rationale.md must survive byte for byte.

    ``run_reingest`` appends the probe to a copy under an isolated temp
    workspace, never to the real corpus file; this is the safety property
    both review rounds flagged as entirely untested.
    """
    corpus, source = _corpus_with_one_spec(tmp_path)
    original = source.read_bytes()
    _script(
        monkeypatch,
        chunk_ids=(frozenset({"chunk-1"}), frozenset({"chunk-1", "chunk-2"})),
    )
    runner = EvaluationRunner(corpus, tmp_path / "records", tmp_path / "store")

    evidence = runner.run_reingest("DM-0001", "docs/specs/0001-test/rationale.md")

    assert evidence.chunks_changed is True
    assert source.read_bytes() == original


def test_run_reingest_probe_reaches_the_isolation_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The probe must actually land on the copy, not silently miss its target.

    Proving the source survives untouched is only half the isolation
    guarantee; a wrong copy path (``open("a")`` creates a missing file
    without complaint) would pass that half while the edit went nowhere real
    for the assertion. This inspects the copy's rationale.md at the moment
    each scripted adapt call runs: absent on the first call, present on the
    second.
    """
    corpus, _source = _corpus_with_one_spec(tmp_path)
    rationale_relpath = "docs/specs/0001-test/rationale.md"
    probe_seen_per_call: list[bool] = []

    def _adapt(self: EvaluationRunner) -> SimpleNamespace:
        copy_path = self.corpus_root / rationale_relpath
        probe_seen_per_call.append(
            "Evaluation re-ingest probe" in copy_path.read_text(encoding="utf-8")
        )
        return SimpleNamespace(exit_code=0)

    monkeypatch.setattr(EvaluationRunner, "adapt", _adapt)
    monkeypatch.setattr(
        EvaluationRunner, "ingest", lambda self, rebuild: SimpleNamespace(exit_code=0)
    )
    chunk_responses = iter([frozenset({"chunk-1"}), frozenset({"chunk-1", "chunk-2"})])
    monkeypatch.setattr(
        EvaluationRunner,
        "_chunk_ids",
        staticmethod(lambda store_dir, record_id: next(chunk_responses)),
    )
    runner = EvaluationRunner(corpus, tmp_path / "records", tmp_path / "store")

    evidence = runner.run_reingest("DM-0001", rationale_relpath)

    assert evidence.chunks_changed is True
    assert probe_seen_per_call == [False, True]


def test_run_reingest_missing_source_file_needs_no_isolation_copy(
    tmp_path: Path,
) -> None:
    """A missing rationale.md fails before the copy machinery runs at all."""
    corpus = make_corpus(tmp_path)
    runner = EvaluationRunner(corpus, tmp_path / "records", tmp_path / "store")

    evidence = runner.run_reingest("DM-0001", "docs/specs/does-not-exist/rationale.md")

    assert evidence.chunks_changed is False
    assert "no such corpus file" in evidence.detail


def test_run_reingest_fails_when_adapt_of_the_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, _source = _corpus_with_one_spec(tmp_path)
    _script(monkeypatch, adapt_exit_codes=(1,))
    runner = EvaluationRunner(corpus, tmp_path / "records", tmp_path / "store")

    evidence = runner.run_reingest("DM-0001", "docs/specs/0001-test/rationale.md")

    assert evidence.chunks_changed is False
    assert evidence.detail == "adapt of the copy failed"


def test_run_reingest_fails_when_initial_ingest_of_the_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, _source = _corpus_with_one_spec(tmp_path)
    _script(monkeypatch, adapt_exit_codes=(0,), ingest_exit_codes=(1,))
    runner = EvaluationRunner(corpus, tmp_path / "records", tmp_path / "store")

    evidence = runner.run_reingest("DM-0001", "docs/specs/0001-test/rationale.md")

    assert evidence.chunks_changed is False
    assert evidence.detail == "initial ingest of the copy failed"


def test_run_reingest_fails_when_re_adapt_of_the_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, source = _corpus_with_one_spec(tmp_path)
    original = source.read_bytes()
    _script(
        monkeypatch,
        adapt_exit_codes=(0, 1),
        ingest_exit_codes=(0,),
        chunk_ids=(frozenset({"chunk-1"}),),
    )
    runner = EvaluationRunner(corpus, tmp_path / "records", tmp_path / "store")

    evidence = runner.run_reingest("DM-0001", "docs/specs/0001-test/rationale.md")

    assert evidence.chunks_changed is False
    assert evidence.detail == "re adapt of the copy failed"
    assert source.read_bytes() == original


def test_run_reingest_fails_when_re_ingest_of_the_copy_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, source = _corpus_with_one_spec(tmp_path)
    original = source.read_bytes()
    _script(
        monkeypatch,
        adapt_exit_codes=(0, 0),
        ingest_exit_codes=(0, 1),
        chunk_ids=(frozenset({"chunk-1"}),),
    )
    runner = EvaluationRunner(corpus, tmp_path / "records", tmp_path / "store")

    evidence = runner.run_reingest("DM-0001", "docs/specs/0001-test/rationale.md")

    assert evidence.chunks_changed is False
    assert evidence.detail == "re ingest of the copy failed"
    assert source.read_bytes() == original


def test_run_reingest_fails_when_the_record_drops_to_zero_chunks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The false positive a review round caught: vanishing is not a pass.

    If the second adapt or ingest silently drops the record instead of
    updating it, ``before`` is non-empty and ``after`` is empty. The oracle
    must not read that as "chunks changed" just because the sets differ.
    """
    corpus, source = _corpus_with_one_spec(tmp_path)
    original = source.read_bytes()
    _script(monkeypatch, chunk_ids=(frozenset({"chunk-1"}), frozenset()))
    runner = EvaluationRunner(corpus, tmp_path / "records", tmp_path / "store")

    evidence = runner.run_reingest("DM-0001", "docs/specs/0001-test/rationale.md")

    assert evidence.chunks_changed is False
    assert "dropped out of the index" in evidence.detail
    assert source.read_bytes() == original


def test_run_reingest_fails_when_chunks_are_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, _source = _corpus_with_one_spec(tmp_path)
    same = frozenset({"chunk-1"})
    _script(monkeypatch, chunk_ids=(same, same))
    runner = EvaluationRunner(corpus, tmp_path / "records", tmp_path / "store")

    evidence = runner.run_reingest("DM-0001", "docs/specs/0001-test/rationale.md")

    assert evidence.chunks_changed is False
    assert (
        evidence.detail
        == "record DM-0001 chunks did not change after the rationale.md edit"
    )


def test_run_reingest_fails_when_record_had_no_chunks_before_the_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    corpus, _source = _corpus_with_one_spec(tmp_path)
    _script(monkeypatch, chunk_ids=(frozenset(), frozenset({"chunk-1"})))
    runner = EvaluationRunner(corpus, tmp_path / "records", tmp_path / "store")

    evidence = runner.run_reingest("DM-0001", "docs/specs/0001-test/rationale.md")

    assert evidence.chunks_changed is False
    assert evidence.detail == "record DM-0001 had no active chunks"


# ---------------------------------------------------------------------------
# proposed_record_ids: pure filesystem-plus-parse logic, no adapt/ingest/store
# ---------------------------------------------------------------------------


def test_proposed_record_ids_finds_only_proposed_status(tmp_path: Path) -> None:
    records_dir = tmp_path / "records"
    write_record_file(
        CanonicalDecisionRecord(id="DM-0001", title="Proposed", status=Status.PROPOSED),
        records_dir / "DM-0001.md",
    )
    write_record_file(
        CanonicalDecisionRecord(id="DM-0002", title="Accepted", status=Status.ACCEPTED),
        records_dir / "DM-0002.md",
    )
    runner = EvaluationRunner(tmp_path / "corpus", records_dir, tmp_path / "store")

    proposed = runner.proposed_record_ids()

    assert proposed.ids == frozenset({"DM-0001"})
    assert proposed.unparsed_count == 0


def test_proposed_record_ids_counts_unparseable_files(tmp_path: Path) -> None:
    """A file with no frontmatter fence counts as unparsed, not silently skipped."""
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    write_record_file(
        CanonicalDecisionRecord(id="DM-0001", title="Proposed", status=Status.PROPOSED),
        records_dir / "DM-0001.md",
    )
    (records_dir / "garbage.md").write_text(
        "not a record file at all, no frontmatter fence", encoding="utf-8"
    )
    runner = EvaluationRunner(tmp_path / "corpus", records_dir, tmp_path / "store")

    proposed = runner.proposed_record_ids()

    assert proposed.ids == frozenset({"DM-0001"})
    assert proposed.unparsed_count == 1


def test_proposed_record_ids_empty_directory_is_a_clean_empty_set(
    tmp_path: Path,
) -> None:
    records_dir = tmp_path / "records"
    records_dir.mkdir()
    runner = EvaluationRunner(tmp_path / "corpus", records_dir, tmp_path / "store")

    proposed = runner.proposed_record_ids()

    assert proposed.ids == frozenset()
    assert proposed.unparsed_count == 0


# ---------------------------------------------------------------------------
# The deviation writer (spec 0010 AC-23)
# ---------------------------------------------------------------------------


def _traced_result() -> QueryResult:
    """A minimal abstained result carrying one readable trace field."""
    return QueryResult(
        schema_version=2,
        state=QueryState.ABSTAINED,
        exit_code=0,
        sentences=(),
        citations=(),
        freshness=FreshnessState.CURRENT,
        abstention_stage=AbstentionStage.CLAIM_VERIFICATION,
        trace=make_empty_query_trace(QueryState.ABSTAINED),
        failure=None,
    )


def test_record_deviation_writes_the_run_named_by_fixture_and_index(
    tmp_path: Path,
) -> None:
    traces_dir = tmp_path / "traces"
    runner = EvaluationRunner(
        tmp_path / "corpus", tmp_path / "records", tmp_path / "store", traces_dir
    )

    runner.record_deviation("query-5-uploaded-files", 2, _traced_result())

    written = sorted(path.name for path in traces_dir.iterdir())
    assert written == ["query-5-uploaded-files-run2.json"]
    payload = json.loads((traces_dir / written[0]).read_text(encoding="utf-8"))
    assert payload["fixture_id"] == "query-5-uploaded-files"
    assert payload["run_index"] == 2
    assert payload["result"]["state"] == "abstained"
    assert payload["result"]["abstention_stage"] == "claim_verification"
    # The whole result, not a projection: the trace is the reason the file
    # exists, and a projection drops the field the next reader wants.
    assert "trace" in payload["result"]
    assert "verification" in payload["result"]["trace"]


def test_record_deviation_creates_the_directory_on_the_first_write(
    tmp_path: Path,
) -> None:
    """A clean batch leaves no empty directory behind."""
    traces_dir = tmp_path / "nested" / "traces"
    runner = EvaluationRunner(
        tmp_path / "corpus", tmp_path / "records", tmp_path / "store", traces_dir
    )
    assert not traces_dir.exists()

    runner.record_deviation("query-4-db-clients", 1, _traced_result())

    assert (traces_dir / "query-4-db-clients-run1.json").is_file()


def test_record_deviation_without_a_traces_directory_is_the_protocol_no_op(
    tmp_path: Path,
) -> None:
    """The re ingest runner builds one this way; it must not write or raise."""
    runner = EvaluationRunner(tmp_path / "corpus", tmp_path / "records", tmp_path)

    runner.record_deviation("query-4-db-clients", 1, _traced_result())

    assert sorted(path.name for path in tmp_path.iterdir()) == []


def test_record_deviation_never_pastes_a_fixture_id_into_a_path(
    tmp_path: Path,
) -> None:
    """A fixture id can come from a battery manifest, so it is filtered."""
    traces_dir = tmp_path / "traces"
    runner = EvaluationRunner(
        tmp_path / "corpus", tmp_path / "records", tmp_path / "store", traces_dir
    )

    runner.record_deviation("../../escape me", 1, _traced_result())

    written = sorted(path.name for path in traces_dir.iterdir())
    # Every separator is replaced, so the write stays inside the traces
    # directory whatever the id was.
    assert written == [".._.._escape_me-run1.json"]
    assert not (tmp_path / "escape me-run1.json").exists()
