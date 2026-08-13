#!/usr/bin/env bash
# Sweep GitHub for ADR/MADR corpora and count records per repo.
# Two-pass: broad (0001) for the distribution, high-numbered for deep corpora.
set -uo pipefail

OUT=$(dirname "$0")/adr-candidates.tsv
: > "$OUT.raw"

search() {  # $1=term $2=filename
  gh search code "$1" --match path --filename "$2" --extension md \
    --limit 40 --json repository,path \
    --jq '.[] | "\(.repository.nameWithOwner)\t\(.path)"' 2>/dev/null
}

echo "== pass 1: broad discovery ==" >&2
for f in 0001 0002 0003; do
  for term in adr decisions; do
    search "$term" "$f"
    sleep 2
  done
done >> "$OUT.raw"

echo "== pass 2: deep corpora (high-numbered files) ==" >&2
for f in 0010 0015 0020 0030 0040; do
  for term in adr decisions; do
    search "$term" "$f"
    sleep 2
  done
done >> "$OUT.raw"

# repo + directory, deduped
awk -F'\t' '{
  n=split($2, p, "/");
  dir=""; for(i=1;i<n;i++) dir = dir (i>1?"/":"") p[i];
  if (dir != "") print $1 "\t" dir
}' "$OUT.raw" | sort -u > "$OUT.pairs"

echo "== counting $(wc -l < "$OUT.pairs" | tr -d ' ') repo/dir pairs ==" >&2

: > "$OUT"
while IFS=$'\t' read -r repo dir; do
  [ -z "$repo" ] && continue
  n=$(gh api "repos/$repo/contents/$dir" \
        --jq '[.[] | select(.type=="file" and (.name|endswith(".md")))] | length' 2>/dev/null)
  case "$n" in ''|*[!0-9]*) n=0 ;; esac
  [ "$n" -gt 0 ] && printf "%s\t%s\t%s\n" "$n" "$repo" "$dir" >> "$OUT"
done < "$OUT.pairs"

sort -rn "$OUT" -o "$OUT"
echo "== done: $(wc -l < "$OUT" | tr -d ' ') corpora ==" >&2
