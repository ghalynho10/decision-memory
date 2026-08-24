#!/usr/bin/env bash
# Proof of concept: can the existing core answer definitional "define X"
# questions against this repo's own corpus? The dictionary idea (idea.md)
# depends on this: definitions are the near verbatim case, which the pipeline
# should handle through the containment shortcut instead of the decomposition
# gauntlet.
#
# Reuses the index built by demo-question-probe.sh (adapt + ingest over this
# repo's own specs), so no re embedding pass is needed.
#
# Requires OPENAI_API_KEY in .env at the repo root (query calls the provider).
# `uv run` does not load .env on its own, hence --env-file.
#
# Usage: dictionary-proof.sh [store-dir] [runs-per-term]
#        Defaults to the demo-question-probe index, 1 run per term.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
cd "$ROOT"
UV=$(command -v uv 2>/dev/null || true)
if [ -z "$UV" ] && [ -x "$HOME/.local/bin/uv" ]; then
  UV="$HOME/.local/bin/uv"
fi
if [ -z "$UV" ]; then
  echo "uv not found on PATH or at $HOME/.local/bin/uv" >&2
  exit 1
fi

STORE=${1:-"$(dirname "$0")/demo-question-probe/index"}
RUNS=${2:-1}
OUT="$(dirname "$0")/dictionary-proof"
mkdir -p "$OUT"

# Terms this repo's own specs actually define. The dictionary idea stands or
# falls on these verifying: each is a near verbatim definitional question.
TERMS=(
  "what is a canonical record in this project?"
  "what is an adapter in this project?"
  "what does abstention mean in this project?"
  "what is a facet in this project?"
  "what is a coverage judge in this project?"
  "what is a fingerprint in this project?"
  "what does supersedes mean in this project?"
  "what is the manifest in this project?"
)

echo "store:  $STORE"
echo "terms:  ${#TERMS[@]}"
echo "runs:   $RUNS"
: > "$OUT/meta.txt"
answered=0
abstained=0
failed=0
total=0

for term in "${TERMS[@]}"; do
  for r in $(seq 1 "$RUNS"); do
    total=$((total+1))
    safe=$(echo "$term" | tr ' ' '_' | tr -cd '[:alnum:]_')
    "$UV" run --env-file .env decision-memory query "$term" \
      --store "$STORE" --debug > "$OUT/${safe}_run$r.txt" 2>&1
    state=$(grep -E "^  state: (answered|abstained|failed)$" \
      "$OUT/${safe}_run$r.txt" | awk '{print $2}' | tail -1)
    case "$state" in
      answered) answered=$((answered+1)) ;;
      abstained) abstained=$((abstained+1)) ;;
      failed) failed=$((failed+1)) ;;
      *) failed=$((failed+1)); state="no_state" ;;
    esac
    echo "--- $term [run $r] state=$state" | tee -a "$OUT/meta.txt"
  done
done
echo "RESULT: answered=$answered abstained=$abstained failed=$failed of $total" \
  | tee -a "$OUT/meta.txt"
