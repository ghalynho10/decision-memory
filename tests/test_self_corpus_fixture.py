"""The frozen self corpus gate fixture (spec 0010 AC-14).

These are `integration` marked because they run the committed generator script
and the real built in adapter over the repository's own specs. CI runs the
unit suite only, so an unmarked test here would silently not run.

Three claims:

- **Isolation**: the fixture's nested ``docs/specs/`` tree is invisible to an
  ``adapt`` run at the repository root, because discovery reads
  ``corpus_root/docs/specs`` and iterates its direct children only. The claim
  is checked on the record **id set**, not merely the count.
- **Drift**: regenerating the fixture against a changed working tree produces
  a visible diff rather than a silent change to the measurement input.
- **Faithfulness**: the fixture is a faithful stand in for the live corpus for
  the chunk text the gate reads. It is not byte faithful for the whole record:
  ``_extract_code_paths`` resolves inline code spans against the corpus root
  and the fixture root holds no ``src/`` or ``tests/`` tree, so each record's
  ``evidence`` set is smaller and its ``mentions_unresolved`` count higher
  than a live adaptation produces. The chunks are what the gate's answers
  read, so identical chunks confine the divergence to fields it never reads.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from decision_memory.application.adapter import DiscoveredSpec
from decision_memory.application.chunking import chunk_record
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter
from decision_memory.infrastructure.tokenization import tiktoken_count

_REPO = Path(__file__).resolve().parent.parent
_SCRIPT = _REPO / "docs" / "experiments" / "data" / "build-self-corpus-fixture.sh"
_FIXTURE = _REPO / "docs" / "experiments" / "data" / "self-corpus-fixture"
_EXCLUDED = "0010-abstention-verification-reliability"
# The gate answers from this record, so it is the one faithfulness reads.
_GATE_RECORD = "DM-0008"


def _discovered_ids(corpus_root: Path) -> set[str]:
    discovery = JsmasteryAdapter().discover(corpus_root)
    assert discovery.corpus_error is None
    return {spec.id for spec in discovery.specs}


def _spec_named(corpus_root: Path, record_id: str) -> DiscoveredSpec:
    discovery = JsmasteryAdapter().discover(corpus_root)
    for spec in discovery.specs:
        if spec.id == record_id:
            return spec
    raise AssertionError(f"{record_id} not discovered under {corpus_root}")


def _chunk_set(corpus_root: Path, record_id: str) -> set[tuple[str, int, str]]:
    result = JsmasteryAdapter().parse(_spec_named(corpus_root, record_id))
    assert result.record is not None
    plans = chunk_record(
        result.record,
        result.field_sources,
        "gen-fixture",
        "fp-fixture",
        tiktoken_count,
    )
    return {(plan.value_path, plan.ordinal, plan.text) for plan in plans}


@pytest.mark.integration
class TestFixtureIsolation:
    def test_the_fixture_is_committed_and_holds_this_spec_out(self) -> None:
        assert (_FIXTURE / "manifest.json").is_file()
        names = {child.name for child in (_FIXTURE / "docs" / "specs").iterdir()}
        assert _EXCLUDED not in names
        assert "0008-reliable-multi-source-retrieval" in names

    def test_discovery_at_the_repository_root_cannot_see_the_fixture(
        self, tmp_path: Path
    ) -> None:
        """The same record **id set** with the fixture present as without it.

        The control root holds only ``docs/specs``, so it has no fixture at
        all. An equal id set proves the nested tree is structurally invisible
        rather than merely filtered out.
        """
        control = tmp_path / "control"
        (control / "docs").mkdir(parents=True)
        (control / "docs" / "specs").symlink_to(_REPO / "docs" / "specs")

        live_ids = _discovered_ids(_REPO)
        control_ids = _discovered_ids(control)
        assert live_ids == control_ids
        # The fixture's own root does see its records, minus the held out one.
        fixture_ids = _discovered_ids(_FIXTURE)
        assert fixture_ids == live_ids - {"DM-0010"}


@pytest.mark.integration
class TestFixtureDrift:
    def test_regenerating_matches_the_committed_manifest_hashes(
        self, tmp_path: Path
    ) -> None:
        """A regenerated fixture whose hashes differ from the committed ones
        is a diff, not a silent pass.

        ``source_commit`` and ``generated`` are excluded: they move with the
        repository and the calendar, not with the measurement input.
        """
        regenerated_root = tmp_path / "fixture"
        run = subprocess.run(
            [str(_SCRIPT), str(regenerated_root)],
            capture_output=True,
            text=True,
        )
        assert run.returncode == 0, run.stderr

        committed = json.loads((_FIXTURE / "manifest.json").read_text())
        regenerated = json.loads((regenerated_root / "manifest.json").read_text())
        assert regenerated["excluded_specs"] == committed["excluded_specs"]
        assert regenerated["queries"] == committed["queries"]
        assert regenerated["files"] == committed["files"], (
            "the fixture has drifted from the committed manifest; regenerate "
            "it deliberately with build-self-corpus-fixture.sh and review the "
            "diff"
        )

    def test_every_manifest_hash_matches_the_committed_bytes(self) -> None:
        """The hash is over the raw bytes of the copied file, not the
        adapter's ``fingerprint()``, which also moves on an
        ``ADAPTER_VERSION`` bump and would report adapter churn as corpus
        drift."""
        manifest = json.loads((_FIXTURE / "manifest.json").read_text())
        assert manifest["files"]
        assert manifest["files"] == sorted(
            manifest["files"], key=lambda row: row["path"]
        )
        for row in manifest["files"]:
            raw = (_FIXTURE / row["path"]).read_bytes()
            assert hashlib.sha256(raw).hexdigest() == row["sha256"], row["path"]

    def test_the_manifest_carries_the_gate_queries_and_expectations(self) -> None:
        """The gate's queries and expectations live in the manifest, outside
        the corpus entirely, so no spec can become a source for the answer its
        own gate checks.

        The oracle is state, a co located citation, and an abstention cause
        (spec 0010 AC-15): the answering query names the value path its
        covering sentence must cite, and the abstaining query names why it is
        expected to abstain. Every key is present on every query, including
        the ones that do not apply, so the loader can require the full key set
        and refuse a manifest it does not fully recognize.
        """
        manifest = json.loads((_FIXTURE / "manifest.json").read_text())
        by_id = {query["id"]: query for query in manifest["queries"]}
        assert set(by_id) == {"decision", "reason"}
        assert by_id["decision"]["expected_record"] == _GATE_RECORD
        assert by_id["decision"]["expected_state"] == "answered"
        assert by_id["decision"]["expected_value_paths"] == ["decision.chosen"]
        assert by_id["decision"]["expected_abstention"] is None
        assert by_id["reason"]["expected_record"] is None
        assert by_id["reason"]["expected_state"] == "abstained"
        assert by_id["reason"]["expected_value_paths"] == []
        assert by_id["reason"]["expected_abstention"] == "uncovered_facet"
        for query in manifest["queries"]:
            assert query["text"].strip()
            assert set(query) == {
                "id",
                "text",
                "expected_record",
                "expected_state",
                "expected_value_paths",
                "expected_abstention",
            }


@pytest.mark.integration
class TestFixtureFaithfulness:
    def test_the_gate_record_chunks_identically_live_and_from_the_fixture(
        self,
    ) -> None:
        """The stated assumption, verified once rather than assumed forever.

        A difference invalidates the fixture and is a finding, not a pass:
        the gate would then be measuring a corpus the live pipeline never
        sees.
        """
        assert _chunk_set(_REPO, _GATE_RECORD) == _chunk_set(_FIXTURE, _GATE_RECORD)
