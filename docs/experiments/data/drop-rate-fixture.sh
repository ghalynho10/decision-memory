#!/usr/bin/env bash
# Re measure the experiment 0003 drop rates on a clean pipeline (spec 0010
# task 11), against the frozen self corpus fixture rather than a live store.
#
# Same 12 queries as drop-rate.sh, so the figures are comparable. Two things
# changed under them: chunk id markers are now stripped at the generation
# boundary (AC-13), and the corpus is the frozen fixture with spec 0010 held
# out (AC-14). Experiment 0003 measured a starved pipeline; this measures the
# same queries with those two causes removed.
#
# Build the store first:
#   decision-memory adapt docs/experiments/data/self-corpus-fixture --output <dir>/records
#   decision-memory ingest <dir>/records --store <dir>/index
#
# Usage: drop-rate-fixture.sh <store-path> [output-dir]
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"

STORE=${1:?usage: drop-rate-fixture.sh <store-path> [output-dir]}
OUT=${2:-"$(dirname "$0")/drop-rate-fixture"}
mkdir -p "$OUT"

i=0
while IFS= read -r q; do
  [ -z "$q" ] && continue
  i=$((i+1))
  printf "[%02d] %s\n" "$i" "$q" >&2
  {
    echo "### QUERY: $q"
    uv run --env-file .env decision-memory query "$q" --store "$STORE" --debug 2>&1
  } > "$OUT/q$(printf %02d "$i").txt"
done <<'QUERIES'
How does the CLI load a third party adapter?
What does the doctor command report?
Why was sub claim decomposition chosen over a deterministic span floor?
Why does the adapter warn instead of inventing missing fields?
What was decided about hybrid lexical and semantic retrieval?
Why did we choose hybrid lexical and semantic retrieval?
What is the adapter conformance suite for?
How are decision records chunked before indexing?
What was decided about the fingerprint for adapted records?
Why is the query index versioned?
How does the system decide to abstain instead of answering?
What was decided about which model performs entailment?
QUERIES
echo "wrote $i transcripts to $OUT" >&2
