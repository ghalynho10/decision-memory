#!/usr/bin/env bash
# Build the frozen self corpus gate fixture (spec 0010 AC-14).
#
# The gate measures code behaviour, so its input is held constant: this script
# copies every direct child of docs/specs/ except spec 0010 into the fixture,
# then writes manifest.json beside it with a sha256 over the raw bytes of each
# copied file. Raw bytes rather than the adapter's own fingerprint(), because
# this hash exists to detect drift of the fixture input; fingerprint() also
# moves on an ADAPTER_VERSION bump, which would report adapter churn as corpus
# drift.
#
# The fixture's own corpus root is the fixture directory, so its records live
# at <fixture>/docs/specs/. That is outside docs/specs/, and discovery reads
# corpus_root/docs/specs and iterates its direct children only, so the nested
# tree is structurally invisible to an adapt run at the repository root.
#
# The gate's queries and their expected records live in the manifest, outside
# the corpus entirely, so no spec can become a source for its own gate answer.
#
# The membership rule for this corpus (spec 0012 AC-8), stated because the one
# entry in EXCLUDED below was a bare assignment with no recorded reason, and a
# second undocumented entry either way would have made the list a habit rather
# than a rule:
#
#   A spec is excluded when its own prose contains the gate's queries, its
#   expected records, or its expected states. Everything else goes in.
#
# That is what holds the line above. The manifest is the home for those values,
# but a spec that quotes them in prose becomes a source for them anyway, and
# then the gate is reading its own answer back. Spec 0010 is excluded under
# exactly that rule and under no other: it carries the gate's literal query
# text (index.md and rationale.md) and its expected record and state
# (index.md, rationale.md), because that spec is where the gate was designed.
# Its own Follow-up already names holding it out as the fixture level fix.
#
# The rule is not "exclude whatever is under active build". That reading was
# considered and rejected: it would make fixture membership change as specs
# finish, which is drift in a fixture whose whole purpose is being frozen.
#
# Spec 0012 contains none of that material and is deliberately included.
#
# Usage: build-self-corpus-fixture.sh [destination]
# The destination defaults to the pinned fixture path; the tests pass a
# temporary directory so a check never rewrites the committed fixture.
set -uo pipefail

ROOT=$(cd "$(dirname "$0")/../../.." && pwd)
SPECS="$ROOT/docs/specs"
FIXTURE=${1:-"$ROOT/docs/experiments/data/self-corpus-fixture"}
# Excluded under the membership rule above: this spec's prose carries the
# gate's own queries, expected record, and expected state. Add an entry only
# for a spec that does the same, never for one that is merely churning.
EXCLUDED="0010-abstention-verification-reliability"

if [ ! -d "$SPECS" ]; then
  echo "no docs/specs/ at $ROOT" >&2
  exit 1
fi

COMMIT=$(git -C "$ROOT" rev-parse --short HEAD 2>/dev/null || echo "unknown")
GENERATED=$(date +%Y-%m-%d)

rm -rf "$FIXTURE"
mkdir -p "$FIXTURE/docs/specs"

for child in "$SPECS"/*; do
  [ -e "$child" ] || continue
  name=$(basename "$child")
  [ "$name" = "$EXCLUDED" ] && continue
  cp -R "$child" "$FIXTURE/docs/specs/$name"
done

# files is sorted by path so two regenerations of the same tree produce a
# byte identical manifest and a real diff is the only thing review sees.
LIST=$(cd "$FIXTURE" && find docs -type f | LC_ALL=C sort)

{
  printf '{\n'
  printf '  "source_commit": "%s",\n' "$COMMIT"
  printf '  "generated": "%s",\n' "$GENERATED"
  printf '  "excluded_specs": ["%s"],\n' "$EXCLUDED"
  printf '  "files": [\n'
  first=1
  while IFS= read -r rel; do
    [ -z "$rel" ] && continue
    hash=$(shasum -a 256 "$FIXTURE/$rel" | awk '{print $1}')
    [ "$first" -eq 0 ] && printf ',\n'
    first=0
    printf '    { "path": "%s",\n      "sha256": "%s" }' "$rel" "$hash"
  done <<< "$LIST"
  printf '\n  ],\n'
  # Every key is present on every query, including the ones that do not apply,
  # written as null or []. That is what lets the loader require the full key
  # set and refuse a manifest it does not fully recognize, rather than reading
  # an absent key as no constraint (spec 0010 AC-15). expected_value_paths
  # names the value path the answer's covering sentence must cite, so citing
  # any chunk of the right record no longer passes; expected_abstention names
  # why the abstaining query is expected to abstain, so an abstention caused
  # by every sentence being dropped stops counting as the gated behaviour.
  printf '  "queries": [\n'
  printf '    { "id": "decision",\n'
  printf '      "text": "What was decided about hybrid lexical and semantic retrieval?",\n'
  printf '      "expected_record": "DM-0008",\n'
  printf '      "expected_state": "answered",\n'
  printf '      "expected_value_paths": ["decision.chosen"],\n'
  printf '      "expected_abstention": null },\n'
  printf '    { "id": "reason",\n'
  printf '      "text": "Why did we choose hybrid lexical and semantic retrieval?",\n'
  printf '      "expected_record": null,\n'
  printf '      "expected_state": "abstained",\n'
  printf '      "expected_value_paths": [],\n'
  printf '      "expected_abstention": "uncovered_facet" }\n'
  printf '  ]\n'
  printf '}\n'
} > "$FIXTURE/manifest.json"

echo "wrote $(printf '%s\n' "$LIST" | wc -l | tr -d ' ') files to $FIXTURE" >&2
