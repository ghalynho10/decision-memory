#!/usr/bin/env bash
# Probe a candidate demo question against this repository's own corpus.
#
# Feature 22 (shipped prebuilt index, spec 0014) is blocked on one value:
# which question the bundle pins. The current flagship question,
#   why was the entry point discovery approach rejected for third party
#   adapters?
# abstains 4 of 4 because the question splits into two facets and the coverage
# judge refuses the second one ("for third party adapters") when the answer
# sentence never literally says those words. The cheapest candidate to unblock
# is the same question with the second facet dropped, which is unmeasured.
#
# This script is the cheap gate before the ten run characterisation: build a
# fresh index over this repo's own specs, run the question N times with
# --debug, and report the answered / abstained count with the abstention stage
# per run. If it wobbles at three, stop and report the counts rather than
# reaching for another unmeasured question.
#
# Requires OPENAI_API_KEY in .env at the repo root (adapt needs none, ingest
# and query need the provider). `uv run` does not load .env on its own.
#
# Usage: demo-question-probe.sh [question] [runs] [output-dir]
#        Defaults to the candidate question, 6 runs (the "six queries" probe).
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"
# Resolve uv to a concrete path up front. Some sandboxed shells fail to find
# uv by PATH lookup after the script re-exports PATH, while executing the
# binary by absolute path always works; pin the path either way for portability.
UV=$(command -v uv 2>/dev/null || true)
if [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ]; then
  UV="$HOME/.local/bin/uv"
fi
if [ -z "$UV" ]; then
  echo "uv not found on PATH or at $HOME/.local/bin/uv" >&2
  exit 1
fi

QUESTION=${1:-"why was the entry point discovery approach rejected?"}
RUNS=${2:-6}
OUT=${3:-"$(dirname "$0")/demo-question-probe"}
mkdir -p "$OUT"

echo "corpus:   $ROOT (this repo's own specs)"
echo "question: $QUESTION"
echo "runs:     $RUNS"

echo "adapt..." >&2
"$UV" run --env-file .env decision-memory adapt "$ROOT" \
  --output "$OUT/records" > "$OUT/adapt.txt" 2>&1
echo "adapt exit $?" | tee "$OUT/meta.txt"

echo "ingest..." >&2
"$UV" run --env-file .env decision-memory ingest "$OUT/records" \
  --store "$OUT/index" > "$OUT/ingest.txt" 2>&1
echo "ingest exit $?" | tee -a "$OUT/meta.txt"

r=1
while [ "$r" -le "$RUNS" ]; do
  printf "run %d/%s\n" "$r" "$RUNS" >&2
  "$UV" run --env-file .env decision-memory query "$QUESTION" \
    --store "$OUT/index" --debug > "$OUT/run$r.txt" 2>&1
  echo "run $r exit $?" | tee -a "$OUT/meta.txt"
  r=$((r+1))
done

# The disposition and its stage, per run.
echo "" | tee -a "$OUT/meta.txt"
r=1
answered=0
abstained=0
while [ "$r" -le "$RUNS" ]; do
  state=$(grep -E "^  state: (answered|abstained)$" "$OUT/run$r.txt" \
    | awk '{print $2}' | tail -1)
  stage=$(grep -E "^  abstention_stage:" "$OUT/run$r.txt" \
    | awk '{print $2}' | tail -1)
  if [ "$state" = "answered" ]; then
    answered=$((answered+1))
  else
    abstained=$((abstained+1))
  fi
  echo "--- run $r: state=$state stage=${stage:-n/a} ---" | tee -a "$OUT/meta.txt"
  r=$((r+1))
done
echo "RESULT: answered=$answered abstained=$abstained of $RUNS" \
  | tee -a "$OUT/meta.txt"
