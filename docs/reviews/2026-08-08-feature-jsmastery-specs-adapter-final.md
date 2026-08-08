# Review, feature/jsmastery-specs-adapter (final pass, AC-6 focus), 2026-08-08

**Reviewed by**: claude-sonnet-5 (AC-6 gating authored on a different session; original code on DeepSeek V4 Flash; round-1/round-2 fixes on claude-sonnet-4.x)
**Scope**: full branch vs `main` (merge base `cd46dc9`), effort concentrated on `git diff abe5f86..HEAD` (commits `33c7d9b`, `c67e8b9`), the never-before-reviewed AC-6 path-shape gate
**Verdict**: Approve with nits

## Summary

The AC-6 shape gate (`_looks_like_path`, `_KNOWN_PATH_EXTENSIONS`, the `shape_token` capture in `_extract_code_paths`) is a correct, faithful implementation of the spec's five contract points: the shape test gates the warning only and never blocks extraction, it runs on the pre-slash-strip token, all three shape conditions are present and case-insensitive on extension, the extension set matches the spec's list verbatim and sits beside `ADAPTER_VERSION`, and the count is of occurrences not distinct tokens. The six new tests genuinely pin the contract rather than passing incidentally — I traced each one against the actual code and against what would happen if the gate moved upstream, tested the post-strip token, or lost case-insensitivity, and each scenario is caught by a specific new test. `ruff`, `mypy --strict`, and all 118 tests pass, unchanged from the stated baseline.

The one thing this pass surfaced that neither prior round caught is unrelated to the new commits but does contradict the shipped spec: running the adapter against this repository's own spec 0003 today measures `unresolved_mention_count = 48` and 5 file-evidence targets, not the `34` / 4 targets that `rationale.md:99` and `index.md` claim as the calibration result the whole AC-6 design rests on. I traced the cause to a pre-existing bug in `_INLINE_CODE_RE`, not something the two new commits touched (confirmed by reproducing the same evidence set, minus the count, on the pre-AC-6 code at `abe5f86`). It is real, and it undermines confidence in the very numbers the spec cites to justify the design, so it is reported as a Major below despite being out of scope of the two commits under primary review.

## Major

### 🟠 The markdown double-backtick escape breaks `_INLINE_CODE_RE`, corrupting the exact numbers the spec's calibration claim rests on, `src/decision_memory/infrastructure/jsmastery_adapter.py:86`

**Problem**: `_INLINE_CODE_RE = re.compile(r"`([^`]+)`")` naively pairs single backticks left to right. Markdown's own escape idiom for showing a literal backtick-quoted phrase, `` `` `read only` `` `` (used repeatedly in this project's own spec 0003, e.g. `index.md:130`, `index.md:132`, `index.md:207-209`, `rationale.md:81,95,99`), contains two adjacent backticks with no content between them. The regex cannot match an empty span, so it silently reinterprets the second backtick of the pair as an *opening* backtick for the next match, which then greedily consumes everything (potentially hundreds of characters, across paragraph breaks) up to the next real single backtick anywhere later in the file. That backtick, which should have opened the next real code span, instead gets consumed as this span's *closing* backtick, flipping the parity of every subsequent pairing for the rest of the document.

Reproduced directly against this repo:

```
_INLINE_CODE_RE.findall(rationale.md) → spans of 124-543 chars starting
right after the first "`` `...` ``" occurrence, e.g. span[89] = ' and quotes
whole sentences in single backticks, so splitting every span on whitespace
turns ordinary words into path candidates... A warning reading "4,999
unresolved mentions"...' (543 chars of prose, not code)
```

Measured end-to-end on this repo, `uv run decision-memory adapt .` for `DM-0003`:

```
unresolved_mention_count: 48        (rationale.md / index.md claim: 34)
file evidence targets: 5, {'.', 'AGENTS.md', 'docs/specs',
  'docs/specs/0002-canonical-decision-record-schema.md', 'tests'}
                                     (rationale.md claims exactly 4: '.',
                                     'AGENTS.md', 'docs/specs', 'tests')
```

I confirmed this is pre-existing, not introduced by the two commits under primary review: checking out `jsmastery_adapter.py` from `abe5f86` (immediately before the AC-6 gate) and re-running gives the identical 5-target evidence set (the corruption already hides `docs/specs/0001-stack-and-architecture.md` and `docs/scope/scope.md`, both of which are quoted verbatim and do resolve, at `rationale.md:107,109`), with only the raw pre-gate count differing (4748, since nothing filtered it yet).

**Why it matters**: This is the identical failure class two prior blockers/majors were raised for — content silently lost or a count silently wrong with no violation raised — except this time it is the feature's own shipped documentation whose claimed measurement doesn't hold up when re-run. `rationale.md:99` states the AC-6 design decision ("the shape test... is therefore the third calibration") is validated by measuring exactly 34/4 against this corpus; that is the evidence basis recorded for the decision, and it is currently false. Beyond the self-referential embarrassment, the underlying bug is general: any spec or rationale file that uses double-backtick markdown escaping to show a literal backtick-quoted example (a very ordinary thing to do in documentation about this exact feature) gets large stretches of unrelated prose misparsed as code spans, which then feed both evidence extraction and the unresolved count with garbage tokens.

**Suggested fix**: Match CommonMark's actual inline-code-span rule: the opening and closing delimiters must be runs of backticks of *equal* length, and a span's content is bounded by the nearest run of the same length (shorter or longer runs inside don't close it). A drop-in fix is to first match the longest backtick run as a candidate opening delimiter and search for a same-length closing run, falling back to shorter runs only when no match exists — or reuse a maintained CommonMark-compliant tokenizer instead of a bespoke regex. Re-verify the 34/4 numbers (or update them) once fixed, and re-check `verify.md`'s AC-6/AC-23 line against the corrected output.

## Minor

### 🟡 `_looks_like_path`/the new tests don't re-assert that a bare directory reference survives extraction inside the same scenario the spec pairs it with, `tests/test_adapter_parse.py:465`

**Problem**: `index.md:207` specifies one combined scenario: "a span holding quoted prose such as `` `read only` `` adds nothing to the count, while a bare directory reference such as `` `tests` `` still resolves as evidence." `test_non_path_tokens_do_not_count_as_unresolved` only exercises the first half (asserts `unresolved_mention_count == 0`); it never asserts a bare directory is still present in evidence in the same test. Contract point (a) — the shape gate must never move upstream into extraction — is still guarded, but only by an older, unrelated test (`test_code_paths_extract_resolve_and_count_unresolved`, which asserts `file_targets == {"app/dashboard/page.tsx", "lib"}`, `lib` being the bare-directory case) that predates this diff and happens to still run.

**Why it matters**: Low risk today since the guard exists elsewhere, but the AC-6 spec explicitly frames "quoted prose adds nothing" and "bare directory still resolves" as one paired scenario precisely because a naive single fix (moving the shape test upstream) satisfies the first half while breaking the second. A future edit to the older test could remove that coverage without anyone noticing this scenario went unguarded.

**Suggested fix**: Add the bare-directory assertion (or an explicit `assert "tests" in file_targets` equivalent) into `test_non_path_tokens_do_not_count_as_unresolved` itself, so the pairing the spec calls out lives in one place.

## Nits

- ⚪ `src/decision_memory/infrastructure/jsmastery_adapter.py:848`, `_looks_like_path`'s docstring says "the caller passes the token as it stood before the trailing slash was stripped" without naming the parameter (`shape_token`) explicitly by name in the docstring; a one-line mapping to the call site would save a reader the round trip.
- ⚪ Every prior review's still-open items remain open and unaddressed by this delta (deliberately, per the task brief): `application/adapter.py` importing infrastructure directly, unbalanced/mixed-fence handling in `_blocks`, duplicate-H2 loss in `_h2_sections`, `_listdir` not caching misses, and AC-13's adapter-version-bump half being untested. None re-litigated here.

## Strengths

- The AC-6 contract is implemented exactly as specified on all five points I was asked to verify, including the one genuinely subtle one (testing shape on the pre-slash-strip token so `oldlib/` counts while `oldlib` wouldn't) — verified both by reading `jsmastery_adapter.py:848-897` and by a dedicated test (`test_renamed_single_segment_dir_counts_via_pre_strip_slash`) that would fail if the ordering were swapped.
- The new tests are real pinning tests, not decorative ones: I checked each of the six against the specific implementation choice it exists to guard (upstream-vs-downstream gating, pre/post-slash-strip ordering, case-insensitive extension matching, occurrence-vs-distinct counting) and each would fail under the corresponding wrong implementation.
- `ADAPTER_VERSION` was correctly bumped (`"1"` → `"2"`) alongside the mapping change, which AC-13 requires and which is easy to forget.
- The docstring on `_extract_code_paths` was updated in the same commit to describe the new behavior, keeping the AC references next to the code they justify, consistent with the rest of the file.

## Test coverage

**Well covered by the new tests**: all three shape conditions individually (slash, extension with case-insensitivity, leading dot), the pre-slash-strip ordering (the subtle case the spec calls out explicitly), occurrence-vs-distinct counting, and non-path tokens (quoted prose, dotted identifiers) contributing nothing. Five of the spec's six listed AC-6 verification cases map directly to a new test; the sixth (bare directory resolves alongside quoted prose adding nothing) is covered, but by an older test rather than the new ones — see the Minor above.

**Gaps**: none new introduced by this delta. The Major above (`_INLINE_CODE_RE` vs. double-backtick escaping) has no test anywhere in the suite, old or new, because the existing fixtures (`CODE_INDEX`, `CODE_RATIONALE`, the new AC-6 fixtures) are all synthetic and none use the double-backtick idiom — the same "fixture suite doesn't reflect real spec prose" gap both prior rounds flagged, still open, and still the way every cross-cutting bug in this feature keeps surfacing. A test that adapts this repository's own `docs/specs/0003-jsmastery-specs-adapter/` and asserts the resulting `unresolved_mention_count` and evidence set against known values (not "non-zero") would have caught this immediately and would catch any future regression in the calibration.
