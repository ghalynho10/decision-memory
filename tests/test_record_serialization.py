"""Record serialization round trip tests (spec 0003, AC-24).

A written record file must be the exact inverse of the read grammar, so a
record the adapter writes parses back to an equal record, and its filename is
the record id plus .md.
"""

from __future__ import annotations

from pathlib import Path

from spec_factory import make_corpus, write_spec

from decision_memory.infrastructure.file_reader import (
    parse_record_file,
    write_record_file,
)
from decision_memory.infrastructure.jsmastery_adapter import JsmasteryAdapter


def test_written_record_round_trips_and_filename(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0012-portfolio-private-access-gate")
    discovery = JsmasteryAdapter().discover(corpus)
    result = JsmasteryAdapter().parse(discovery.specs[0])
    assert result.record is not None
    target: Path = tmp_path / "DM-0012.md"
    write_record_file(result.record, target)
    assert target.name == "DM-0012.md"
    parsed = parse_record_file(target)
    assert parsed.violations == []
    assert parsed.record == result.record


def test_round_trip_preserves_body_verbatim(tmp_path) -> None:
    corpus = make_corpus(tmp_path)
    write_spec(corpus, "0001-first")
    discovery = JsmasteryAdapter().discover(corpus)
    result = JsmasteryAdapter().parse(discovery.specs[0])
    assert result.record is not None
    target: Path = tmp_path / "DM-0001.md"
    write_record_file(result.record, target)
    parsed = parse_record_file(target)
    assert parsed.record is not None
    assert parsed.record.body == result.record.body
