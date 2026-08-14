"""Turn experiment 0007's --debug transcripts into the pinned run records.

Spec 0010 AC-19. This reads only what the shipped CLI printed. It re
implements no pipeline stage: every field below is lifted from a trace line,
and the two derived fields (the abstention cause and the co location result)
follow the shipped rules line for line, named here so a reader can check them
against the code rather than trust this file:

- the abstention cause mirrors ``application.evaluation.abstention_cause``: a
  claim verification abstention with a nonempty coverage tuple, then
  ``no_emitted_sentences`` when every coverage row carries the deterministic
  reason constant and ``uncovered_facet`` otherwise. Any other stage is
  neither cause and is recorded as null.
- co location mirrors the AC-15 covering sentence scope: a citation whose
  record is the manifest's ``expected_record`` and whose value path starts
  with an ``expected_value_paths`` prefix, belonging to a sentence that a
  covered coverage row names.
- the decision facet is the first non reason facet, mirroring
  ``application.evaluation._facet_is_reason``.

``reader_verdicts`` carries every sentence that reached coverage, quoted
verbatim, with ``verdict`` left null. That half is judged by a person against
the rule written into the spec's ``rationale.md`` before these runs ran.

Usage: coverage-directness-extract.py <manifest.json> <transcripts-dir>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

# The AC-12 deterministic reason constant, the string
# ``application.query.NO_EMITTED_SENTENCE_REASON`` holds. Repeated here
# because this script reads printed text, not the module.
NO_EMITTED_SENTENCE_REASON = "no emitted answer sentence"

# Published per million token prices for the two fixed models, recorded in the
# experiment so a later reader can re price the same token counts.
PRICES_PER_MILLION = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}
# The model each generation concern is fixed to (``openai_generation.py``).
CONCERN_MODEL = {
    "facets": "gpt-4o",
    "answer": "gpt-4o",
    "coverage": "gpt-4o",
    "entailment": "gpt-4o-mini",
    "decompose": "gpt-4o-mini",
}

_DRAFT_RE = re.compile(r"^  (S\d+): (.*) \[([^\]]*)\]$")
_FACET_RE = re.compile(r"^  (F\d+): (.*)$")
_COVERAGE_RE = re.compile(r"^  (F\d+) covered=(True|False) \[([^\]]*)\] reason=(.*)$")
_DROPPED_RE = re.compile(r"^  dropped_sentence (S\d+) reason=(\S+)$")
_REJECTED_RE = re.compile(
    r"^  rejected_decomposition (S\d+) count=(\d+) disposition=(\S+) "
    r"additive_failure=(\S*)$"
)
_SUBCLAIM_VERDICT_RE = re.compile(r"^    contained=(\S+) entailment=(\S+) \[.*\]$")
_SUBCLAIM_HEAD_RE = re.compile(r"^  (S\d+\.\d+) \(S\d+\): ")
_PROVIDER_RE = re.compile(
    r"^  (\S+) attempt=(\d+) elapsed_ms=(\d+) outcome=(\S+) "
    r"prompt_tokens=(\d+) completion_tokens=(\d+)$"
)
_CITATION_RE = re.compile(r"^  (c\d+) \S+ (\S+) (\S+) (\S+) ")
_ANSWER_RE = re.compile(r"^(.*) \[((?:c\d+)(?:,c\d+)*)\]$")


# The fixed debug section headers, in the order ``_print_query_debug`` prints
# them (spec 0008 AC-10). ``Freshness`` is the first, so everything above it is
# the report the CLI prints before the trace: the answer sentences and their
# citation ids for an answered result, or the abstention line.
_HEADERS = (
    "Freshness",
    "Filter",
    "Lexical",
    "Semantic",
    "Fusion",
    "Diversity",
    "Settings",
    "Facets",
    "Draft",
    "Verification",
    "Sub claims",
    "Providers",
    "Citations",
    "Result",
    "Sources",
)


def _sections(lines: list[str]) -> dict[str, list[str]]:
    """Split the transcript by its fixed top level section headers.

    Only a known header opens a section, because an answer sentence is also
    printed unindented and would otherwise become a section of its own. The
    preamble, keyed by the empty string, is what the CLI printed before the
    trace began.
    """
    sections: dict[str, list[str]] = {"": []}
    current = ""
    for line in lines:
        stripped = line.rstrip()
        if stripped in _HEADERS:
            current = stripped
            sections.setdefault(current, [])
            continue
        sections[current].append(stripped)
    return sections


def _facet_is_reason(text: str) -> bool:
    lowered = text.casefold()
    return "why" in lowered or "reason" in lowered


def extract(
    run_id: str, query: dict[str, Any], transcript: str, wall_seconds: float
) -> dict[str, Any]:
    lines = transcript.splitlines()
    sections = _sections(lines)

    facets: list[tuple[str, str]] = []
    for line in sections.get("Facets", []):
        match = _FACET_RE.match(line)
        if match:
            facets.append((match.group(1), match.group(2)))

    draft: dict[str, str] = {}
    for line in sections.get("Draft", []):
        match = _DRAFT_RE.match(line)
        if match:
            draft[match.group(1)] = match.group(2)

    coverage: list[tuple[str, bool, list[str], str]] = []
    for line in sections.get("Verification", []):
        match = _COVERAGE_RE.match(line)
        if match:
            named = [item for item in match.group(3).split(",") if item]
            coverage.append(
                (match.group(1), match.group(2) == "True", named, match.group(4))
            )

    dropped: list[dict[str, str]] = []
    rejected: list[dict[str, Any]] = []
    entailment: list[dict[str, str]] = []
    sub_claim_id = ""
    for line in sections.get("Sub claims", []):
        head = _SUBCLAIM_HEAD_RE.match(line)
        if head:
            sub_claim_id = head.group(1)
            continue
        verdict = _SUBCLAIM_VERDICT_RE.match(line)
        if verdict and sub_claim_id:
            entailment.append(
                {"sub_claim_id": sub_claim_id, "entailment": verdict.group(2)}
            )
            continue
        drop = _DROPPED_RE.match(line)
        if drop:
            dropped.append({"sentence_id": drop.group(1), "reason": drop.group(2)})
            continue
        reject = _REJECTED_RE.match(line)
        if reject:
            rejected.append(
                {
                    "sentence_id": reject.group(1),
                    "disposition": reject.group(3),
                    "additive_failure": reject.group(4),
                }
            )

    citations: dict[str, tuple[str, str]] = {}
    for line in sections.get("Citations", []):
        match = _CITATION_RE.match(line)
        if match:
            citations[match.group(1)] = (match.group(2), match.group(4))

    state = ""
    stage = ""
    for line in sections.get("Result", []):
        if line.strip().startswith("state:"):
            state = line.split(":", 1)[1].strip()
        if line.strip().startswith("abstention_stage:"):
            stage = line.split(":", 1)[1].strip()

    usd_cost = 0.0
    for line in sections.get("Providers", []):
        match = _PROVIDER_RE.match(line)
        if not match:
            continue
        model = CONCERN_MODEL.get(match.group(1))
        if model is None:
            continue
        input_price, output_price = PRICES_PER_MILLION[model]
        usd_cost += int(match.group(5)) / 1_000_000 * input_price
        usd_cost += int(match.group(6)) / 1_000_000 * output_price

    # The answer sentences, mapped back to their draft ids by text. Draft
    # sentence texts are unique (``validate_draft`` rejects a repeat) and an
    # emitted sentence is its parent verbatim (AC-4), so this is a bijection.
    text_to_id = {text: sentence_id for sentence_id, text in draft.items()}
    sentence_citations: dict[str, list[str]] = {}
    for line in sections.get("", []):
        match = _ANSWER_RE.match(line)
        if match and match.group(1) in text_to_id:
            sentence_citations[text_to_id[match.group(1)]] = match.group(2).split(",")

    emitted = [
        sentence_id
        for sentence_id in draft
        if sentence_id not in {row["sentence_id"] for row in dropped}
    ]

    # The abstention cause, read the way ``abstention_cause`` reads it.
    abstention_cause: str | None = None
    if state == "abstained" and stage == "claim_verification" and coverage:
        if all(row[3] == NO_EMITTED_SENTENCE_REASON for row in coverage):
            abstention_cause = "no_emitted_sentences"
        else:
            abstention_cause = "uncovered_facet"

    decision_facets = [
        facet_id for facet_id, text in facets if not _facet_is_reason(text)
    ]
    covered_by_facet = {row[0]: row for row in coverage}
    facet_covered: bool | None = None
    if decision_facets and decision_facets[0] in covered_by_facet:
        facet_covered = covered_by_facet[decision_facets[0]][1]

    # Co location, in the AC-15 covering sentence scope. Null for an
    # abstained run: there is no answer to check.
    co_location: bool | None = None
    if state == "answered":
        expected_record = query.get("expected_record")
        prefixes = query.get("expected_value_paths") or []
        covering = {sentence_id for row in coverage if row[1] for sentence_id in row[2]}
        co_location = (
            all(
                any(
                    citations.get(citation_id, ("", ""))[0] == expected_record
                    and citations.get(citation_id, ("", ""))[1].startswith(prefix)
                    for sentence_id in covering
                    for citation_id in sentence_citations.get(sentence_id, [])
                )
                for prefix in prefixes
            )
            if prefixes
            else None
        )

    reader_verdicts = [
        {"sentence_id": sentence_id, "text": draft[sentence_id], "verdict": None}
        for sentence_id in emitted
    ]

    return {
        "run_id": run_id,
        "query_id": query["id"],
        "state": state,
        "sentences_emitted": len(emitted),
        "sentences_reaching_coverage": len(emitted),
        "facet_covered": facet_covered,
        "abstention_cause": abstention_cause,
        "co_location_satisfied": co_location,
        "reader_verdicts": reader_verdicts,
        "dropped": dropped,
        "rejected": rejected,
        "entailment": entailment,
        "wall_seconds": wall_seconds,
        "usd_cost": round(usd_cost, 6),
    }


def main() -> int:
    manifest_path, transcripts_dir = Path(sys.argv[1]), Path(sys.argv[2])
    manifest = json.loads(manifest_path.read_text())
    queries = {query["id"]: query for query in manifest["queries"]}
    for path in sorted(transcripts_dir.glob("*.txt")):
        run_id, _, query_id = path.stem.rpartition("-")
        seconds_path = path.with_suffix(".seconds")
        wall_seconds = (
            float(seconds_path.read_text().strip()) if seconds_path.exists() else 0.0
        )
        record = extract(run_id, queries[query_id], path.read_text(), wall_seconds)
        print(json.dumps(record, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
