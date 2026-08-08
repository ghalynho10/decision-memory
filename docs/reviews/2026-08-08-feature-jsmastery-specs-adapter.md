# Review, feature/jsmastery-specs-adapter, 2026-08-08

**Reviewed by**: claude-opus-5 (author on DeepSeek V4 Flash)
**Scope**: 19 files (14 code/test, 4 docs), branch vs main (merge base `cd46dc9`)
**Verdict**: Blocked

## Summary

This change adds the `adapt` command, a `SourceAdapter` protocol, a jsmastery-format adapter, record serialization, and the spec-0003 validation upgrades (direct target resolution, `unresolved_mention_count`). The structure is good and the hard parts the spec worried about, notably the winner ladder and case-sensitive resolution, are handled correctly. `ruff`, `mypy --strict`, and all 101 tests pass.

The problem is that the suite is shaped around the fixture in `tests/spec_factory.py` rather than around real spec prose, and three of the mapping's silent-failure modes are invisible to it. Running the adapter against this repository's own spec 0003 drops all nine `Negative / tradeoffs` consequences with no warning and no `attempted_fields` entry, which breaks the feature's headline invariant that nothing is ever silently lost. Two more findings, the AC-15 rewrite behaviour and the unresolved-mention counter, are contract breaks that the tests assert around rather than through.

## Blockers

### 🔴 Consequences are silently dropped when the label or bullets carry bold, `src/decision_memory/infrastructure/jsmastery_adapter.py:458`

**Problem**: `_list_under_label` fails in two independent ways on ordinary spec prose.

1. It matches the label by exact equality (`label_match.group(1).strip().lower() == label.lower()`, line 465). The convention used throughout this project's own specs is `**Negative / tradeoffs**:`, which never equals `negative`, so the whole negative list is skipped.
2. `_BOLD_LABEL_RE` (line 61) allows an optional leading list marker, so a bullet written as `- **Fast**: no scan needed.` matches as a *different* bold label and hits the `break` at line 473, truncating the list at its first bolded item.

Then, at the call site (lines 249-261), `attempted` is only populated when the `## Consequences` section is absent, stub, or blank. A section that is present and non-empty but yields nothing produces `consequences=None`, no `field.attempted_unfilled` warning, and, because `Consequences` is in `_CONSUMED_SECTIONS` (line 56), no residue body entry either. The content vanishes with zero signal.

Verified against the live corpus, `uv run decision-memory adapt .`:

```
consequences: Consequences(positive=[...6 items...], negative=[])
attempted: []
violations: [('warning', 'evidence.mentions_unresolved', 'evidence')]
```

Spec 0003's own `## Consequences` has nine `Negative / tradeoffs` bullets. All nine are gone and nothing reports it.

**Why it matters**: This is precisely the failure the spec forbids. `## Summary` of spec 0003: "anything it tried to fill and could not is flagged as a warning." AC-12 requires `attempted_fields` to name a field "which turned out absent or empty". Records reaching feature 5's ingestion will be missing the tradeoffs half of every decision, and no operator inspecting the report will know. The whole point of this slice is that a person can judge the corpus before embedding, and the report actively misleads them here.

**Suggested fix**: Match the consequence label by prefix or normalized stem rather than exact equality, so `Negative / tradeoffs` and `Negative` both hit. Stop treating a bulleted bold lead-in as a section terminator: only break on a bold label that is *not* preceded by a list marker, and keep the item text. Separately, and independently of the parsing fix, flag `consequences.positive` / `consequences.negative` in `attempted_fields` whenever the `## Consequences` section exists but the extracted list is empty, so this class of miss can never be silent again.

## Major

### 🟠 AC-15 is not met: unchanged records are rewritten on every run, `src/decision_memory/application/adapter.py:216`

**Problem**: Every non-failed spec is appended to `writes` (line 216), including those whose fingerprint matched the manifest and were classified `unchanged` (line 192). The write loop at lines 218-221 then writes all of them unconditionally. The `state` string is the only thing that distinguishes them.

Verified:

```
states: ['unchanged']
AC-15 mtime unchanged? False
```

`tests/test_adapt_run.py:53` asserts only `[record.state for record in outcome_two.records] == ["unchanged"]`, which is why this passes. `docs/specs/0003-jsmastery-specs-adapter/verify.md:12` also records "nothing is rewritten" as verified, which is not what was checked.

**Why it matters**: AC-15 states plainly that "a spec whose fingerprint matches the manifest is not rewritten", and the stated purpose (spec 0003 `## Summary`) is that feature 5 can avoid re-embedding a whole corpus on every edit. Any downstream consumer keying off mtime, inode, or a filesystem watcher, which is the normal way an ingestion pipeline detects change, will re-embed the entire corpus on every run. The bug is invisible today only because the rewritten bytes happen to be identical.

**Suggested fix**: Skip the write for outcomes in the `unchanged` state, appending to `writes` only for `written` and `rewritten`. Keep the manifest entry for unchanged records so the manifest stays complete. Then strengthen the test to assert the record file's mtime, or its bytes plus mtime, is untouched across the second run, not just the reported state.

### 🟠 `unresolved_mention_count` counts every non-path token, making AC-6 and AC-23 warnings useless, `src/decision_memory/infrastructure/jsmastery_adapter.py:754`

**Problem**: `_extract_code_paths` increments `unresolved` for every whitespace-separated token in every inline code span that does not resolve on disk (line 782). Inline code in a spec is overwhelmingly rule ids, field names, type names, and prose identifiers, not paths. Against this repo's spec 0003 the count is **3611** for a single spec, producing the warning `3611 code path mentions did not resolve`.

Mentions are also not deduplicated, so one identifier repeated forty times counts forty times, unlike the resolved side which dedupes via `seen`.

**Why it matters**: AC-6 wants the warning to surface "a spec naming a since renamed file", a real, actionable signal. As built, the true signal is buried under thousands of false ones on every record, so the warning will be ignored or suppressed, and the renamed-file case it exists to catch will go unnoticed. The spec's design note that "existence is the disambiguator" is correct for deciding what becomes *evidence*, but it does not carry over to what should be *counted as a loss*.

There is a performance consequence too: `path_resolves_case_sensitive` does an uncached `os.listdir` per path component per call, with 3627 calls measured for one spec. That is tens of thousands of syscalls for a 15-spec corpus, on directories listed over and over.

**Suggested fix**: Count only tokens that actually look like a path before attempting resolution, for instance requiring a `/` or a known file extension, and dedupe the unresolved set the same way the resolved set is deduped. Add an LRU cache or a per-run directory-listing cache in `path_resolution.py` so a directory is listed once per run.

### 🟠 Section parsing is not fenced-code aware, so `##` inside a code block creates phantom sections, `src/decision_memory/infrastructure/jsmastery_adapter.py:367`

**Problem**: `_blocks` scans line by line with `_HEADING_RE` and has no notion of a fenced code block. Any line starting with `#`, `##`, or `###` inside a ``` fence is treated as a real heading. Compounding it, `_h2_sections` (line 362) builds a plain dict, so a duplicate heading silently overwrites the earlier one, last occurrence wins.

Reproduced with a spec whose `## Summary` contains a fenced markdown example:

```
sections: ['Summary', 'Decision']
Decision body: '**Chosen option**: Option 1: X'
```

The `## Summary` body is truncated at the fence, the fenced content leaks into a phantom `Decision` section, and only the ordering of the real `## Decision` later in the file saves the mapping. Had the fence come last, the fake section would have won.

**Why it matters**: Spec documents routinely embed markdown, YAML, and shell examples in fences. When this fires, the corruption is silent: content is dropped from the body, or a field is populated from example text, with no violation raised. This repo's four specs happen to contain no fences, so nothing is broken today, but the JobPilot validation corpus is unverified in this respect, and the failure mode is exactly the "fabricated value" the spec's key invariants forbid.

**Suggested fix**: Track fence state in `_blocks`, toggling on lines matching ```` ^\s*(```|~~~) ```` and ignoring heading matches while inside a fence. Separately, make `_h2_sections` not lose duplicate headings silently: either keep the first and skip later ones, or append the bodies, and be explicit about which in the docstring.

### 🟠 The application layer imports infrastructure directly, `src/decision_memory/application/adapter.py:23`

**Problem**: `from decision_memory.infrastructure.file_reader import write_record_file` is a module-level import from application into infrastructure. AGENTS.md is explicit: "outer layers depend inward" and "infrastructure implements interfaces from domain or application". The file's own docstring even claims "YAML record writing lives in infrastructure", which is true of the implementation but not of the dependency direction.

This is doubly odd here because the change goes to real trouble to declare a `SourceAdapter` protocol (line 36) and inject the adapter into `adapt_corpus`, then hard-wires the writer right next to it. The spec's data-model table declares no writer in the application layer at all.

**Why it matters**: `adapt_corpus` is now untestable without touching the filesystem, which contradicts AGENTS.md's "Domain and application unit tested without infrastructure mocks". It also blocks the obvious next need, writing records anywhere other than a local directory.

**Note**: `validation_service.py:17` already imported `parse_record_file` the same way before this branch, so the pattern is pre-existing rather than introduced here. It is still worth fixing now while there are only two call sites.

**Suggested fix**: Declare a narrow `RecordWriter` protocol in the application layer alongside `SourceAdapter`, take it as a parameter to `adapt_corpus`, and wire the concrete `write_record_file` in `cli.py`, which is already the composition root and already imports from infrastructure legitimately.

## Minor

### 🟡 No test covers the consequences mapping at all, `tests/`

**Problem**: `grep -rn "consequences" tests/` returns nothing. A specced canonical field with its own extraction helper (`_list_under_label`) has zero direct coverage, which is how the blocker above shipped. With `TESTS = configured`, untested branching extraction logic is a finding on its own.

**Why it matters**: Every other mapping rule has a named test tied to its AC. This one gap is where the only silent data-loss bug landed.

**Suggested fix**: Add cases for a plain `**Positive**` / `**Negative**` pair, the `**Negative / tradeoffs**` label variant, bulleted items with bold lead-ins, and a present-but-unextractable section asserting the `attempted_fields` flag.

### 🟡 AC-13's adapter-version half is untested, `tests/test_adapt_run.py`

**Problem**: AC-13 requires the fingerprint to change both when a contributing file changes *and* when `ADAPTER_VERSION` changes. `test_second_run_rewrites_only_changed` covers the file edit; nothing covers the version bump, though the spec calls it out as a critical test scenario and the manual verify list claims AC-13 coverage.

**Suggested fix**: Monkeypatch `ADAPTER_VERSION`, or call `fingerprint` with both values, and assert the digests differ with the files untouched.

### 🟡 Dead condition in stub detection, and stub matching is too broad, `src/decision_memory/infrastructure/jsmastery_adapter.py:419`

**Problem**: `_is_stub` collapses whitespace first (`_collapse_whitespace` at line 801 replaces `\s+`, which includes newlines), then checks `if "\n" in collapsed`. That branch can never be true, so the spec's "single line" requirement is not enforced; a multi-line section that collapses under 80 characters is treated as a stub. Confirmed: `_is_stub("See\nrationale.md\nfor more.", ...)` returns `True`.

The membership test is also a bare substring check (`any(name in collapsed ...)`), so any short section merely *mentioning* a sibling filename is discarded from both its field and the body. `_is_stub("This supersedes rationale.md entirely and is authoritative.", ...)` returns `True`.

**Why it matters**: Genuine, if short, content is silently discarded. Narrow in practice given the 80-character bound, but it is a silent drop in a feature whose contract is that nothing is silently dropped.

**Suggested fix**: Either drop the unreachable check and document that collapsed length is the only line test, or test line count on the pre-collapse text. Tighten the sibling match to require the mention to be substantially the whole body, for instance a pointer-shaped body such as `See <sibling>.`, rather than any occurrence.

### 🟡 An unconsumed section present in both files is emitted twice in the body, `src/decision_memory/infrastructure/jsmastery_adapter.py:429`

**Problem**: `_residue_body` iterates `index_sections` then `rationale_sections` and appends every unconsumed section from each. A `## Summary` in both files yields two `## Summary` blocks in the record body. Confirmed by construction.

**Why it matters**: Every other section rule in this feature applies "rationale wins, index is the fallback" (AC-8). The residue body is the one place it does not, so the record contradicts itself, and the duplicated text will be embedded twice in feature 5.

**Suggested fix**: Apply the same precedence: emit a heading once, preferring the `rationale.md` body when both files carry it.

### 🟡 `**Neutral**` consequences are dropped with no trace, `src/decision_memory/infrastructure/jsmastery_adapter.py:249`

**Problem**: `## Consequences` is in `_CONSUMED_SECTIONS`, but only `Positive` and `Negative` are extracted from it. This project's specs, including 0003, carry a `**Neutral**` list which reaches neither a canonical field nor the residue body.

**Why it matters**: AC-11 says the body holds "every section that neither file's mapping consumed". A partially-consumed section is a gap the rule does not anticipate, and the content is lost.

**Suggested fix**: Either append the unextracted remainder of `## Consequences` to the body, or state explicitly in the spec that `Neutral` is intentionally discarded and flag it. Do not leave it undocumented.

### 🟡 Three or more colliding directories produce multiple pairwise collisions, `src/decision_memory/infrastructure/jsmastery_adapter.py:138`

**Problem**: Each subsequent collider appends a fresh `Collision` holding only `[seen[spec_id], child]`. AC-19 asks for "a collision naming every path found and the one used"; with three colliders you get two entries of two paths each.

**Suggested fix**: Accumulate colliding paths per id and emit one `Collision` per id with the full list. `test_collision_reports_every_path_and_uses_first` uses only two directories, so extend it to three.

### 🟡 Records are orphaned when a spec disappears or starts failing, `src/decision_memory/application/adapter.py:197`

**Problem**: `entries` is rebuilt from scratch each run and only includes successful records. A spec deleted from the corpus, or one that begins failing validation, drops out of the manifest while its previously written `.md` file stays in the output directory.

**Why it matters**: The invariant "the output directory holds valid records exclusively" quietly stops holding, and feature 5 ingesting the whole directory would pick up a stale record for a decision that no longer exists.

**Suggested fix**: Compare the previous manifest's ids against the current run's and either delete or report orphaned record files. Worth a spec follow-up entry, since spec 0003 does not cover deletion.

### 🟡 `verify.md` records AC-15 as verified when it is not, `docs/specs/0003-jsmastery-specs-adapter/verify.md:12`

**Problem**: The line "run `adapt` again with no source changes → every record reports `unchanged` and nothing is rewritten → AC-15" is checked off, but only the report was observed. Files are rewritten.

**Suggested fix**: Uncheck it until the Major above is fixed, and change the check to inspect mtimes rather than the report.

## Nits

- ⚪ `src/decision_memory/infrastructure/jsmastery_adapter.py:771`, `token.rstrip("/")` strips *all* trailing slashes; AC-4 specifies "a trailing `/`". Use a single-slash strip so `lib//` behaves as specified.
- ⚪ `src/decision_memory/infrastructure/jsmastery_adapter.py:283`, `_bold_field(index_text, "Supersedes")` scans the entire file, so a prose mention of `**Supersedes**:` anywhere in the body populates the field. Same for `Date` at line 246. Scope both to the preamble before the first H2, which the parsing model already defines.
- ⚪ `src/decision_memory/infrastructure/jsmastery_adapter.py:164`, each contributing file is read three to four times per spec (`discover`, `parse`, `_evidence_and_unresolved`, `fingerprint`). Reading once into the `DiscoveredSpec` would be simpler as well as faster.
- ⚪ `src/decision_memory/cli.py:122`, the exit-3 explanation prints *after* the `result:` summary line, so the most important message is not the first thing an operator sees. Print it before the report, or return early.
- ⚪ `README.md:180`, no trailing newline at end of file.
- ⚪ `src/decision_memory/infrastructure/jsmastery_adapter.py:329`, `_evidence_and_unresolved` skips a contributing file that becomes unreadable between discovery and parse without recording anything, so evidence silently narrows. A warning would fit the feature's own no-silent-loss rule.

## Strengths

- The winner ladder is genuinely well built. It handles both option shapes (`_parse_inline_options` and `_parse_heading_options`), and `_panel_decision_letter` correctly takes the first `Option X` token, which is the trap spec 0003 explicitly warned about for 0012's Panel 3. Verified against the live corpus, alternatives and rejection reasons come out right.
- `path_resolves_case_sensitive` is the correct implementation of a genuinely subtle requirement, walking `os.listdir` per component so macOS case-insensitivity cannot mask a bad target. The docstring explains why, not just what.
- Exporting `normalize_target` from the domain so the adapter and validator share one implementation, rather than letting two copies drift on whether a target resolves, is the right call and is explained at the definition.
- Round-trip serialization is a true inverse: `_record_to_mapping` omits `None` and empty values so a record never asserts a field it lacks, and `test_record_serialization.py` proves the parse-back equality rather than just spot-checking keys.
- Failure containment is consistently right: `discover` and `parse` never raise for a bad source, `_read_text` and `_read_bytes` degrade rather than throw, and one unadaptable spec never stops the run.
- Docstrings tie code back to specific ACs throughout, which made this review far faster than it would otherwise have been.
- Clean `ruff`, clean `mypy` on strict settings, 101 passing tests.

## Test coverage

**Well covered**: discovery and skip reasons (AC-1, AC-2, AC-7, AC-20), the winner ladder across both option shapes and panel units including the unresolvable-unit case (AC-9, AC-10), stub fall-through and residue body (AC-8, AC-11), code path extraction and case sensitivity (AC-4, AC-5), `attempted_fields` including the `triggering_change` non-flag (AC-12), the round trip (AC-24), manifest shape and ordering (AC-14, AC-25), dry run in both first-run and existing-file forms (AC-17), the output override (AC-18), and all three exit codes (AC-21) including the synthetic invalid-record fixture the spec asked for (AC-16).

**Gaps**:
- The consequences mapping has no test whatsoever. This is where the blocker lives.
- AC-15 is asserted through the reported `state` only, never against the filesystem, so the rewrite bug passes.
- AC-13's adapter-version half is unverified.
- AC-6 and AC-23 assert only that the count is non-zero (`test_code_paths_extract_resolve_and_count_unresolved`), never that it is *correct*, so the 3611-per-spec inflation is invisible.
- `_blocks` is never exercised against fenced code, and `_h2_sections` never against duplicate headings.
- Everything runs through `tests/spec_factory.py`, whose fixtures are cleaner than real spec prose. A test that adapts this repository's own `docs/specs/` and asserts the resulting record's field-by-field content would have caught the blocker, the mention-count inflation, and the `Neutral` drop in one go. Worth adding as a marked integration test.
