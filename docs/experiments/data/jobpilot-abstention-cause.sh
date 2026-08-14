#!/usr/bin/env bash
# Attribute a JobPilot fixture abstention to its cause (experiment 0009).
#
# Experiment 0008 measured four JobPilot fixtures failing as "expected
# answered, got abstained" and could not say why: `evaluate` reports state, not
# cause. The two candidates point at different fixes, so the distinction decides
# what gets built next.
#
#   no_emitted_sentences  every draft sentence was dropped in verification, so
#                         coverage was never called and the deterministic
#                         uncovered rows applied (spec 0010 AC-12, AC-15)
#   uncovered_facet       sentences survived and coverage refused them
#
# `evaluate` builds its records and store in a temporary directory and removes
# them on exit, so there is no persistent JobPilot store to query. This script
# builds one, then runs the query with --debug the given number of times and
# saves the full trace per run. Read the Sub claims and Verification sections of
# each trace; the cause is in the coverage row reason and the dropped_sentence
# rows.
#
# Requires DECISION_MEMORY_JOBPILOT_DIR and OPENAI_API_KEY in .env at the repo
# root. `uv run` does not load .env on its own, hence --env-file.
#
# Usage: jobpilot-abstention-cause.sh [question] [runs] [output-dir]
#        Defaults to QUERY_TWO from application/evaluation.py, 3 runs.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"

QUESTION=${1:-"What decisions affect resume generation?"}
RUNS=${2:-3}
OUT=${3:-"$(dirname "$0")/jobpilot-abstention-cause"}
mkdir -p "$OUT"

CORPUS=$(grep '^DECISION_MEMORY_JOBPILOT_DIR' .env | cut -d= -f2-)
if [ ! -d "$CORPUS" ]; then
  echo "DECISION_MEMORY_JOBPILOT_DIR is unset or not a directory: $CORPUS" >&2
  exit 1
fi

echo "corpus:   $CORPUS" | tee "$OUT/meta.txt"
echo "question: $QUESTION" | tee -a "$OUT/meta.txt"
echo "runs:     $RUNS" | tee -a "$OUT/meta.txt"

echo "adapt..." >&2
uv run --env-file .env decision-memory adapt "$CORPUS" \
  --output "$OUT/records" > "$OUT/adapt.txt" 2>&1
echo "adapt exit $?" | tee -a "$OUT/meta.txt"

echo "ingest..." >&2
uv run --env-file .env decision-memory ingest "$OUT/records" \
  --store "$OUT/index" > "$OUT/ingest.txt" 2>&1
echo "ingest exit $?" | tee -a "$OUT/meta.txt"

r=1
while [ "$r" -le "$RUNS" ]; do
  printf "run %d/%s\n" "$r" "$RUNS" >&2
  uv run --env-file .env decision-memory query "$QUESTION" \
    --store "$OUT/index" --debug > "$OUT/run$r.txt" 2>&1
  echo "run $r exit $?" | tee -a "$OUT/meta.txt"
  r=$((r+1))
done

# The three lines that carry the answer, per run.
echo "" | tee -a "$OUT/meta.txt"
r=1
while [ "$r" -le "$RUNS" ]; do
  echo "--- run $r ---" | tee -a "$OUT/meta.txt"
  grep -E "reason=no emitted answer sentence|uncovered F|rejected_decomposition|dropped_sentence|state:|abstention_stage:" \
    "$OUT/run$r.txt" | tee -a "$OUT/meta.txt"
  r=$((r+1))
done
