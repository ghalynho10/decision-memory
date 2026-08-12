# Session notes

In session residue that has not earned a place in scope, a spec, or AGENTS.md yet. `/checkpoint` owns the sections below; other skills own anything else.

## Open threads

- Date handling gap: `/develop` added a Pydantic field validator to coerce an unquoted YAML date scalar (for example `date: 2026-08-07`) to its ISO string, because PyYAML parses it as a date object. Spec 0002 still does not mention this; a candidate for a follow up line in the spec.
- The `evidence.mentions_unresolved` warning and its AC-6 count never appear in CLI output: the adapt report prints violations only for failed records, and `validate` rebuilds its own context with the count defaulting to zero. The calibration is only visible through the adapter's parse API and the unit tests. A candidate for a later decision on surfacing the warning in the adapt report.
- Commit `abe5f86` is labelled `fix(adapter):` but contains only docs. It is already pushed with PR #1 open, so correcting the subject line needs a force push. Left undecided: leave it, or amend with `--force-with-lease`.
- PR #4 merged to main 2026-08-12 (feature 10, merge commit `4b160ab`). A fresh /check review on opus (2026-08-11) found the semantic top-24 boundary test at tests/test_retrieval_stages.py was tautological against a gate recorded as passing (verdict: Changes requested); fixed pre-merge along with the AC-9 embedding-provider trace gap and the query 1 live oracle regrounding (spec Follow-up 5). The remaining review minors were merged as is, per the user's choice, and are tracked as spec 0008 Follow-up items 10-13 (store-parity masked as abstention, invented diversity dispositions in a partial trace, missing AC-16 import test, dead `QUERY_SCHEMA_VERSION` constant): docs/reviews/2026-08-11-multi-source-retrieval.md has the full findings.

## Ruled out

- Plain single command Typer app (one `@app.command` plus `no_args_is_help`) does not dispatch in Typer 0.27.1: it auto invokes the command and rejects the command name. The CLI uses a callback (`invoke_without_command`) plus commands instead.
- Measuring adapter behaviour with a hand written script that re implements the extraction pipeline. This produced wrong figures that were committed to spec 0003 `rationale.md` and survived a full cross check before review round 3 caught them. Two divergences caused it: the replica concatenated both contributing files into one string while the shipped `_evidence_and_unresolved` extracts per file and sums (which matters because backtick pairing is naive, so the join changes pairing across the seam), and it ignored `spec` kind evidence so it under reported the resolved targets. Call the shipped API.
- Splitting the core cited query milestones 2 and 3 into two separate commits. Impossible: milestone 2 was never committed and milestone 3 rewrote its core files (`ingest.py`, `index_store.py`), so no milestone 2 snapshot exists anywhere. The user chose the combined commit `40cf406` instead.

## Standing instructions

- Commit messages in this project leave out any `Co-Authored-By` trailer, for any author (Claude, DeepSeek, or otherwise). Originally asked for directly against Claude only; broadened 2026-08-11 after a `Co-Authored-By: DeepSeek V4 Flash` trailer went unobjected to in scope but the user then confirmed the ban should be general.
- When a shipped decision turns out to need correcting, amend the existing spec rather than writing a new numbered spec or a supersession, unless the decision itself genuinely changed. This project's own adapter reads these specs, so an extra spec or a supersession chain puts a shape in the corpus that later gets reported as decision history when no second decision was ever made. Record the correction and its evidence in that spec's `rationale.md`.
- Re run `/check review` after a batch of `/debug` fixes on this feature. Across this work two of four fixes introduced new regressions (a deleted record never restored, an unbalanced fence swallowing whole sections) and a later round caught wrong measurements in a spec; none of it was caught by the passing test suite, only by a fresh model review.
- Any mention count recorded against spec 0003 is a reading taken at a moment, not a constant. That spec describes the adapter, so editing it changes the adapter's own input: adding quoted examples while documenting the AC-6 rule moved the pre fix count from 3,611 to 4,748 with no code change. Re measure after any edit rather than trusting a figure already written down.
- Leave the pre-existing uncommitted AGENTS.md change (the circuit breaker section, added outside this session) alone; it is not part of feature 10 or PR #4.

## Review triage: feature 4, 2026-08-08

A `/develop` run worked through the open items from the feature 4 review rounds. This resolves the two stale entries in Open threads above (the layering violation and the unread minors and nits); `/checkpoint` may fold them away.

**Fixed, with regression tests:**
- Layering: the application layer no longer imports infrastructure. `adapt_corpus` takes a `RecordWriter` port, `validate_file` takes `RecordReader` and `CitedPathResolver` ports, and `cli.py` (the composition root) wires the concrete `write_record_file`, `parse_record_file`, and `resolve_cited_paths`. `ParseResult` moved to `domain/records.py`. All three application to infrastructure imports are gone.
- `ADAPTER_VERSION` bumped 3 to 4 so existing fingerprints invalidate for the mapping changes (AC-13).
- Adapter: stub detection now requires a pointer shape (`_is_pointer`) and drops a dead branch; `_residue_body` emits each heading once with rationale precedence (AC-8); `**Neutral**` and any other unconsumed Consequences content survives in the body (AC-11); collisions accumulate per id so N colliders yield one entry naming all paths (AC-19); duplicate H2 bodies concatenate instead of overwriting; a trailing slash is stripped singly per AC-4; `Date`, `Status`, and `Supersedes` read only the preamble so a body mention cannot leak; inline option and Cons parsing are fence aware.
- Infrastructure: `_listdir` caches a miss sentinel so a failing listing is attempted once.
- CLI: the exit 3 message prints before the report; README ends with a newline.

**Deferred, with reasons:**
- Orphaned record files when a spec is deleted: spec 0003 defines no deletion policy, so implementing one would invent behavior. Needs a spec follow up, not a silent code choice.
- Bulleted consequence labels such as `- **Positive**:`: the both empty guard already flags the case as attempted and lets the section fall through to the body, so the miss is visible, not silent.
- Contributing files read three to four times per spec: `DiscoveredSpec` deliberately carries paths, not bytes, so file content stays out of the application layer; the cost is bounded on this corpus.
- Unreadable contributing file silently narrows file evidence: an edge case; `parse` already errors on an unreadable index and flags an absent rationale through `attempted_fields`, and the spec evidence entry still cites the file.
- Emphasis survives in stored fields (for example `**Style drift**:`): deliberate, matching do not truncate; stripping it before embedding is a spec level decision.
- A fence test's first assertion passes pre fix: an informational test note, not a behavior to change.

**Confirmed shipped (the amended AC-6):** `_KNOWN_PATH_EXTENSIONS` holds the spec's 15 extensions beside `ADAPTER_VERSION`; the unresolved mention count is shape gated through `_looks_like_path` on the pre slash strip token, counts occurrences not distinct tokens, and never blocks extraction. Measured 107 unresolved for DM-0003, matching the documented calibration.

**Follow up from `/check review` (2026-08-08, DeepSeek V4 Pro):** verdict Approve with nits, two dormant minors both fixed. `_unconsumed_remainder` no longer attributes inter label prose to the preceding block, so a sentence between Positive and Negative survives in the body; `_is_pointer` dropped `check` from its pointer words so a body like "Check rationale.md for details." is content, not a stub. `ADAPTER_VERSION` bumped to 5. Findings: `docs/reviews/2026-08-08-main-adapter-review-triage.md`.
