#!/usr/bin/env bash
# Measure how often each drop reason fires, and whether enumerated-list
# splitting is behind the unsupported_sub_claim drops.
set -uo pipefail
cd /Users/ghaly/Documents/Work/Personal/decision-memory
OUT=$(dirname "$0")/drop-rate
mkdir -p "$OUT"
STORE=~/Desktop/dm-test/index

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
