#!/usr/bin/env bash
# Measure the AC-18 field label change on a coverage conditional instrument
# (spec 0010 task 17, AC-19). Experiment 0007.
#
# Why this is not the gate: EvaluationOutcome records only checks, passed,
# failed, and an exit code, and the answering half fails both when coverage
# rejects a good sentence and when no sentence survives verification. A gate
# verdict cannot attribute the result to either, so this drives the shipped
# CLI per run and records what the trace already holds.
#
# It runs the two frozen fixture manifest queries, twice three runs, keeps
# every --debug transcript verbatim, and emits one JSON object per run to
# runs.jsonl in the shape spec 0010 Feature design pins. No step re
# implements a pipeline stage: the extractor reads the transcript the CLI
# printed and nothing else.
#
# reader_verdicts comes out with "verdict": null on every row. That half is
# the human one: the rule is in the spec's rationale.md, written before these
# runs, and the verdicts are filled in afterwards from the quoted sentences
# alone.
#
# Build the store first (once; both batches share it, so the evidence is held
# constant the way experiment 0006 held it):
#   decision-memory adapt docs/experiments/data/self-corpus-fixture --output <dir>/records
#   decision-memory ingest <dir>/records --store <dir>/index
#
# Usage: coverage-directness.sh <store-path> [output-dir]
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"

STORE=${1:?usage: coverage-directness.sh <store-path> [output-dir]}
OUT=${2:-"docs/experiments/data/coverage-directness"}
MANIFEST="docs/experiments/data/self-corpus-fixture/manifest.json"
TRANSCRIPTS="$OUT/transcripts"
mkdir -p "$TRANSCRIPTS"

# The query ids and texts come from the fixture manifest, never from this
# script and never from a spec, so the gate's expectations stay in one place
# (AC-14).
QUERY_IDS=$(python3 -c 'import json,sys; print(" ".join(q["id"] for q in json.load(open(sys.argv[1]))["queries"]))' "$MANIFEST")

for batch in 1 2; do
  for run in 1 2 3; do
    run_id="batch${batch}-run${run}"
    for query_id in $QUERY_IDS; do
      text=$(python3 -c 'import json,sys; print(next(q["text"] for q in json.load(open(sys.argv[1]))["queries"] if q["id"]==sys.argv[2]))' "$MANIFEST" "$query_id")
      out_file="$TRANSCRIPTS/${run_id}-${query_id}.txt"
      printf "[%s %s] %s\n" "$run_id" "$query_id" "$text" >&2
      started=$(python3 -c 'import time; print(time.monotonic())')
      uv run --env-file .env decision-memory query "$text" \
        --store "$STORE" --debug > "$out_file" 2>&1
      python3 -c 'import time,sys; print(round(time.monotonic()-float(sys.argv[1]), 3))' "$started" \
        > "$TRANSCRIPTS/${run_id}-${query_id}.seconds"
    done
  done
done

python3 "$(dirname "$0")/coverage-directness-extract.py" "$MANIFEST" "$TRANSCRIPTS" \
  > "$OUT/runs.jsonl"
echo "wrote $(wc -l < "$OUT/runs.jsonl") run records to $OUT/runs.jsonl" >&2
