# Review, feature/jsmastery-specs-adapter (re-review of fixes), 2026-08-08

**Reviewed by**: claude-opus-5 (fixes authored on claude-sonnet-4.x; original code on DeepSeek V4 Flash)
**Scope**: 19 files, branch vs main (merge base `cd46dc9`); fix delta is 3 source files + 3 test files, uncommitted
**Verdict**: Changes requested

## Summary

Three of the four flagged problems have real, working fixes, and I re-derived each one rather than taking the claim on trust: I checked out the pre-fix tree into a scratch copy and ran the new tests against it, and all three regression tests fail there and pass here. That is a genuinely good debug loop, and the fence fix and the AC-15 fix are both minimal and correct for the case they target.

The problems are that one of the four was only half fixed, one fix opened a new silent hole, and one fix left the "never lose content silently" guard the original blocker asked for unimplemented. Concretely: `unresolved_mention_count` is still 3611 for a single spec on this repo's own corpus (only the syscall cost was addressed, not the count), an unbalanced code fence now swallows every later section, and a record file deleted from the output directory is never recreated because the manifest alone decides `unchanged`. `ruff`, `mypy src`, and all 106 tests pass.

## Fix verification (re-derived, not taken on trust)

| Prior finding | Status | Evidence |
|---|---|---|
| 🔴 Consequences silently dropped | **Parsing fixed, guard missing** | `adapt .` on this repo now yields `pos: 6 neg: 8` (the section has exactly 8 `Negative / tradeoffs` bullets; the prior review's "nine" was a miscount). Test is red pre-fix. But see Major 1 below. |
| 🟠 AC-15 rewrite | **Fixed** | `adapter.py:216` now gates on `state != "unchanged"`. `test_second_run_rewrites_only_changed` asserts `st_mtime_ns` and is red pre-fix. New regression, see Major 3. |
| 🟠 `unresolved_mention_count` | **Not fixed** | See Major 2. Only the caching half landed. |
| 🟠 Fenced-code awareness | **Half fixed** | `_blocks` fence tracking works for balanced fences and the test is red pre-fix. Unbalanced fences regress (Major 4); `_h2_sections` duplicate-heading loss (the second half of the original finding) is untouched (Minor 1). |
| 🟠 application → infrastructure import | **Still present**, deliberately deferred | `adapter.py:23`. Not re-litigated. |

## Major

### 🟠 The blocker's silent-loss guard was not implemented, so the failure class survives, `src/decision_memory/infrastructure/jsmastery_adapter.py:253`

**Problem**: The original blocker had two halves: fix the parsing, *and* independently flag `consequences.positive`/`consequences.negative` in `attempted_fields` whenever `## Consequences` exists but extraction yields nothing, "so this class of miss can never be silent again". Only the parsing landed. Lines 253-262 still add the attempted flags only when the section is absent, a stub, or blank. A section that is present, non-empty, and simply uses labels the extractor does not know still vanishes completely, because `Consequences` is in `_CONSUMED_SECTIONS` (line 57) so it does not reach the residue body either.

Reproduced with a `## Consequences` section using `**Upsides**` / `**Downsides**`:

```
consequences: None
attempted:    ['decision.alternatives']
'must not vanish' in body? False
```

**Why it matters**: This is the same contract break, one label variant away. The fix hardened the corpus we have rather than the invariant the spec states ("anything it tried to fill and could not is flagged as a warning"). Any second jsmastery-style project, which spec 0003's own Consequences section names as the likely stressor, re-triggers it with no signal at all.

**Suggested fix**: After extraction, if `consequences_body` was non-empty but `positive` and `negative` are both empty, add both to `attempted`. Optionally also append the unconsumed remainder of the section to the residue body, which would close the `**Neutral**` minor from the prior review at the same time.

### 🟠 `unresolved_mention_count` is unchanged at 3611 per spec; only the syscall cost was fixed, `src/decision_memory/infrastructure/jsmastery_adapter.py:816`

**Problem**: The prior Major had two parts, a meaningless count and an uncached `os.listdir` walk. The `listdir_cache` (line 798, threaded into `path_resolves_case_sensitive`) fixes the second. The first is untouched: `_extract_code_paths` still increments `unresolved` for every whitespace-separated token in every inline code span that does not resolve on disk, with no path-shape filter and no dedupe, while the resolved side still dedupes via `seen` (line 812).

Measured now, on this repository, `uv run decision-memory adapt .`:

```
DM-0003 unresolved: 3611
violations: [('warning', 'evidence.mentions_unresolved')]
```

Identical to the pre-fix number in the prior review.

**Why it matters**: unchanged from the prior review. AC-6 exists so that a spec naming a since-renamed file is visible; a warning reading "3611 code path mentions did not resolve" on every record is noise an operator will learn to ignore, and the one real signal it exists to carry is buried. The caching makes the wrong answer cheaper to compute, not right. `verify.md`'s "a code path token whose casing differs ... is counted as a dropped mention → AC-5, AC-6, AC-23" is checked off against a counter that is off by three orders of magnitude.

**Suggested fix**: As before, require a token to look like a path (contain `/`, or end in a known source extension) before it can count as unresolved, and dedupe the unresolved set the way `seen` dedupes the resolved one. Then tighten `test_code_paths_extract_resolve_and_count_unresolved` to assert the exact count on a fixture with a known number of path-shaped misses, not just non-zero, otherwise the same inflation can return.

### 🟠 New: a record deleted from the output directory is never recreated, `src/decision_memory/application/adapter.py:190`

**Problem**: The AC-15 fix makes the manifest the sole authority on whether a record needs writing. `state` is derived only from `previous.get(spec.id) == fingerprint` (lines 190-196); nothing checks that `output_dir / f"{spec.id}.md"` still exists. Before the fix, the unconditional rewrite masked this.

Reproduced:

```
run1: ['written']    exists: True
run2 after deleting the record file: ['unchanged']  exit: 0  record recreated: False
```

The manifest still carries the entry with `record_path: DM-0001.md` pointing at a file that is not there, and the run exits 0.

**Why it matters**: The manifest now lies, and it lies silently and durably; re-running `adapt` does not heal it, because the fingerprint still matches forever. Spec 0003's stated purpose is that feature 5 can trust the output directory and the manifest to decide what to ingest, so a manifest entry with no file behind it is exactly the state it must never reach. Partial output-directory loss (a stray `rm`, a failed sync, a `.gitignore` that excluded records from a clone) is ordinary, and self-healing is the behavior the previous code accidentally had.

**Suggested fix**: Treat a missing record file as a reason to write: classify as `unchanged` only when the fingerprint matches *and* the record file exists, otherwise `rewritten`. Add a test that deletes the record between runs and asserts the file comes back.

### 🟠 New: an unbalanced code fence now swallows every later section, `src/decision_memory/infrastructure/jsmastery_adapter.py:384`

**Problem**: `_blocks` toggles `in_fence` on any line matching `_FENCE_RE` and never resets it. If a file has an odd number of fence lines, or nests fences unevenly, every heading after the last unmatched opener is treated as body text. This is a behavior the pre-fix code did not have.

Reproduced with a single unclosed fence:

```
input:    "## A\n\n```\nunclosed\n\n## B\n\nreal b\n"
sections: ['A']            # '## B' and 'real b' are now inside A's body
```

A related, smaller case: `_FENCE_RE` does not track *which* fence character opened the block, so a `~~~` line inside a ``` ``` ``` fence closes it early. `"## A\n\n```\n~~~\n## fake\n```\n\n## B\n\nreal b\n"` yields `['A', 'fake']`, a phantom section, which is precisely the failure the fix was written to prevent. (Evenly nested four-backtick fences happen to work.)

**Why it matters**: The consequence is worse than the bug it replaces. A missing `## Rationale` heading does not just lose a section, it silently merges that content into the preceding section's body, so `context.problem` or `decision.chosen` can be populated from unrelated prose with no violation raised, and `attempted_fields` stays empty because the field *did* get filled, just wrongly. Documentation that demonstrates markdown, which spec files routinely do, is the natural source of both an uneven fence count and a mixed fence character.

**Suggested fix**: Record the opening fence's character and minimum length, and close only on a line of the same character at least as long, per CommonMark. That fixes the `~~~`-inside-backticks case directly. For the unbalanced case, either treat an unterminated fence as never having opened (re-scan, or track the last heading seen before the opener and fall back to it at EOF) or emit a violation naming the file, since an unclosed fence is itself a fact worth reporting under this feature's no-silent-loss rule.

## Minor

### 🟡 Duplicate H2 headings still silently overwrite, `src/decision_memory/infrastructure/jsmastery_adapter.py:365`

**Problem**: The second half of the original fence finding is untouched. `_h2_sections` is still a dict comprehension over `_blocks`, so `"## Notes\n\nfirst\n\n## Notes\n\nsecond\n"` yields `{'Notes': 'second'}` and the first body is gone with no trace. Now that fenced `##` lines can no longer manufacture duplicates, the remaining trigger is a genuinely duplicated heading in the source, which is rarer, but the loss is still silent.

**Suggested fix**: Keep the first occurrence and route later ones to the residue body, or concatenate the bodies. Either is fine; say which in the docstring.

### 🟡 The fix narrowed `_list_under_label` so a bulleted label is no longer recognized, `src/decision_memory/infrastructure/jsmastery_adapter.py:496`

**Problem**: To stop `- **Term**: ...` bullets terminating the list, the fix requires a label line to satisfy `stripped.startswith("**")`. That also means a label written as a list item, `- **Positive**:` with indented sub-bullets, is now invisible: `_list_under_label("- **Positive**:\n  - a\n  - b\n", "Positive")` returns `[]`, where the pre-fix code returned the items. Combined with Major 1 above, that miss is completely silent.

**Why it matters**: A real trade-off was made here, correctly for this corpus, but it is undocumented in the docstring beyond the bullet case, and it swaps one silent-drop shape for another. With the Major 1 guard in place this becomes a visible warning instead of a loss, which is the main reason to do that fix.

**Suggested fix**: Either accept a bulleted label when its content is *only* the bold label plus an optional colon (no trailing prose), which distinguishes it from `- **Term**: explanation`, or leave it and land the Major 1 guard so the case reports itself.

### 🟡 `_listdir` does not cache misses, `src/decision_memory/infrastructure/path_resolution.py:49`

**Problem**: The `OSError` branch returns `None` without writing to the cache, so a token pointing into a nonexistent directory re-issues the failing `os.listdir` on every occurrence. With 3611 unresolved mentions per spec, most of which resolve nowhere, this is the majority of the remaining syscalls, so the cache delivers much less than the test suggests.

**Suggested fix**: Cache a sentinel (an empty `frozenset` is sufficient, since a missing directory and an empty one both fail the `part not in entries` check identically) so a failed listing is attempted once.

### 🟡 The cache test asserts an exact syscall count, `tests/test_path_resolution.py:59`

**Problem**: `assert calls == 10` in `test_without_a_cache_each_call_lists_again` couples the test to the exact walk implementation rather than to the property under test. Any future short-circuit (for example the miss-caching above, or an early `is_dir` check) breaks it for the right reason. The paired test's `assert calls == 2` is fine, because 2 *is* the property.

Also `# two directories walked ("src" then its parent)` has the order backwards; the walk lists the root first, then `src`.

**Suggested fix**: Assert `calls > 2` (or `calls >= 10`) for the uncached case, so it stays a control on the cached assertion without pinning the implementation.

### 🟡 `verify.md` still claims the dropped-mention criteria are verified, `docs/specs/0003-jsmastery-specs-adapter/verify.md:22`

**Problem**: "a code path token whose casing differs from the entry on disk does not resolve and is counted as a dropped mention → AC-5, AC-6, AC-23" is checked off. The case-sensitivity half is genuinely correct; the counting half is the Major 2 inflation. The AC-15 line above it is now honestly checkable, though what was actually observed was the report, not the filesystem, and the fix's new test is the real evidence.

**Suggested fix**: Uncheck the AC-6/AC-23 half until the counter is filtered, and reword the AC-15 step to say the record file's mtime is unchanged, since that is now what the suite asserts.

## Nits

- ⚪ `src/decision_memory/infrastructure/jsmastery_adapter.py:597`, `_parse_inline_options` and `_cons_for_block` (line 693) call `_HEADING_RE` directly with no fence awareness, so the bug just fixed in `_blocks` still exists inside an option block containing a fenced snippet. Same class, smaller blast radius.
- ⚪ `tests/test_adapter_parse.py:675`, the expected negative item keeps its raw `**Style drift**: ` markdown inside a structured YAML field. Correct as "do not truncate", but worth deciding explicitly whether emphasis should survive into a field that feature 5 embeds.
- ⚪ `tests/test_adapter_parse.py:729`, the fence test's first assertion (`body.count(...) == 1`) passes pre-fix too; only the second assertion carries the regression. Not wrong, just worth knowing which line is the guard.
- ⚪ Every prior review nit remains open (`token.rstrip("/")`, whole-file `**Supersedes**` scan, repeated file reads, exit-3 message ordering, README trailing newline, unreadable-file evidence narrowing). None re-litigated here.

## Strengths

- The debug loop was run properly and it shows. Each of the three regression tests genuinely fails against the pre-fix tree, which I verified by extracting `HEAD`'s source into a scratch copy and running the new tests against it: `test_second_run_rewrites_only_changed`, `test_qualified_negative_label_and_bold_bullet_are_not_dropped`, and `test_heading_like_line_inside_a_fence_is_not_a_section_break` all fail there, and the fourth path-resolution test passes there as the deliberate control. That is the standard the guide asks for and it was met.
- `_matches_label` is the right shape for the label problem, and its docstring names the exact discriminator (`Negative / tradeoffs` matches, `Negatively` does not) rather than restating the code. Verified against the live corpus: 6 positive, 8 negative, all eight tradeoff bullets present including the bold lead-in one.
- The AC-15 fix is one line and exactly the right one. Appending to `writes` only for non-`unchanged` states, while still appending to `entries` unconditionally, keeps the manifest complete, which was the subtle part.
- `listdir_cache` is threaded through as an optional parameter rather than a module-level global, so it stays per-run and cannot leak stale listings between invocations. The docstring explains when to pass one.
- Test fixtures are written as realistic spec prose (`REAL_QUALIFIED_NEGATIVE_INDEX`) rather than minimal synthetic input, which directly addresses the prior review's point that the suite was shaped around clean fixtures.

## Test coverage

**Newly covered and genuinely load-bearing**: the qualified `Negative / tradeoffs` label plus bold-lead-in bullets; AC-15 against the filesystem via `st_mtime_ns`; the fenced-heading section break; the listdir cache in three states (cached, uncached control, and correctness preserved under caching, including the case-mismatch path).

**Gaps, in rough priority**:
- No test for a `## Consequences` section that is present but yields nothing (Major 1). This is the same gap that let the original blocker ship, now one label variant away.
- No test asserts the *value* of `unresolved_mention_count` (Major 2), so the 3611 inflation is still invisible to the suite.
- No test for a missing record file with an intact manifest (Major 3), or for an unbalanced fence (Major 4).
- `_h2_sections` is still never exercised against duplicate headings.
- AC-13's adapter-version half is still unverified (prior review, unaddressed).
- Still no test that adapts this repository's own `docs/specs/` and asserts field-by-field content. Every finding in both reviews that the fixture suite missed, this one included, was found by running the adapter against the real corpus. A marked integration test doing that would be the single highest-value addition.
