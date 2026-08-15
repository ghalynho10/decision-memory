#!/usr/bin/env bash
# Compare two independent builds of the same corpus (experiment 0015).
#
# Experiment 0014 found batch D holding every AC-2 miss, answering query 5 in
# 3 of 3 with a fluent wrong answer, and putting the rationale summary at 0 of
# 3, while batches A, B, and C agreed. A batch is one `evaluate` invocation,
# which is one adapt plus one ingest, so the store is the variable held
# constant within a batch and varied between them. That experiment could not
# check the store, because `evaluate` builds into temporary directories that
# are removed on exit, and its traces record what the pipeline did with a
# store, never how the store was built.
#
# This builds the same corpus twice into persistent directories and compares
# them. `compare-stores.py` does the comparison, keyed by chunk id; the second
# pass below re keys by (record_id, value_path, ordinal), which is what
# separates "the content moved" from "only the identifiers moved".
#
# The fork this decides:
#   content differs   -> adapt or ingest is nondeterministic
#   only ids differ   -> the content is stable and the ids are not, which
#                        matters wherever an id is used as a sort key
#   nothing differs   -> the store is exonerated and experiment 0014's between
#                        batch spread is provider side
#
# Requires DECISION_MEMORY_JOBPILOT_DIR and OPENAI_API_KEY in .env at the repo
# root. `uv run` does not load .env on its own, hence --env-file.
#
# Usage: store-build-determinism.sh [output-dir]
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"

HERE=$(dirname "$0")
OUT=${1:-"$HERE/store-build-determinism"}
mkdir -p "$OUT"

CORPUS=$(grep '^DECISION_MEMORY_JOBPILOT_DIR' .env | cut -d= -f2-)
if [ ! -d "$CORPUS" ]; then
  echo "DECISION_MEMORY_JOBPILOT_DIR is unset or not a directory: $CORPUS" >&2
  exit 1
fi

echo "corpus: $CORPUS" | tee "$OUT/meta.txt"

for build in a b; do
  echo "build $build: adapt..." >&2
  uv run --env-file .env decision-memory adapt "$CORPUS" \
    --output "$OUT/$build/records" > "$OUT/$build-adapt.txt" 2>&1
  echo "build $build adapt exit $?" | tee -a "$OUT/meta.txt"

  echo "build $build: ingest..." >&2
  uv run --env-file .env decision-memory ingest "$OUT/$build/records" \
    --store "$OUT/$build/index" > "$OUT/$build-ingest.txt" 2>&1
  echo "build $build ingest exit $?" | tee -a "$OUT/meta.txt"
done

# Level 1: the adapted records. `adapt` makes no provider call, so a difference
# here is pure code nondeterminism. `manifest.json` carries a `generated_at`
# wall clock stamp that always differs; it is reported separately rather than
# filtered, so the exclusion is visible instead of assumed.
echo "" | tee -a "$OUT/meta.txt"
echo "--- records ---" | tee -a "$OUT/meta.txt"
if diff -r "$OUT/a/records" "$OUT/b/records" > "$OUT/records.diff" 2>&1; then
  echo "records: IDENTICAL" | tee -a "$OUT/meta.txt"
else
  if grep -qv 'generated_at\|manifest.json\|^[0-9-]*c[0-9-]*$\|^[<>-]*$' \
      "$OUT/records.diff"; then
    echo "records: DIFFER beyond the timestamp, see records.diff" \
      | tee -a "$OUT/meta.txt"
  else
    echo "records: identical apart from manifest generated_at" \
      | tee -a "$OUT/meta.txt"
  fi
  head -20 "$OUT/records.diff" | tee -a "$OUT/meta.txt"
fi

# Levels 2 and 3: the chunks, read through the shipped reader so the comparison
# sees what retrieval sees. Keyed by chunk id first, then re keyed by the
# stable triple, because a chunk id carries the generation id and therefore
# moves on every build by construction.
echo "" | tee -a "$OUT/meta.txt"
uv run python "$HERE/compare-stores.py" "$OUT" 2>&1 | tee -a "$OUT/meta.txt"

echo "" | tee -a "$OUT/meta.txt"
uv run python "$HERE/compare-stores.py" "$OUT" --by-position 2>&1 \
  | tee -a "$OUT/meta.txt"

tail -24 "$OUT/meta.txt"
