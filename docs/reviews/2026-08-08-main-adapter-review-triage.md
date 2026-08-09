# Review, main, 2026-08-08

**Reviewed by**: DeepSeek V4 Pro (author on an unknown model)
**Scope**: 15 files, branch-like (commit ceb4c70 vs parent fbefb8c)
**Verdict**: Approve with nits

## Summary
This commit fixes a previously flagged Clean Architecture layering violation by injecting `RecordWriter`, `RecordReader`, and `CitedPathResolver` Callable ports at the composition root (`cli.py`), moving `ParseResult` to the domain, and removing all application-to-infrastructure imports. It also fixes seven mapping bugs: preamble-scoped metadata reading, non-stub sibling mentions, duplicate-H2 concatenation, Neutral consequences preservation, fence-aware option/Cons parsing, N-way collision accumulation, and single-trailing-slash stripping. Every fix has a targeted regression test, and `ADAPTER_VERSION` is bumped to 4. All 129 tests, mypy, ruff, and ruff format pass cleanly. The layering fix is correct and the mapping fixes are accurate against the spec contract.

## Minor
### 🟡 Inter-label prose silently discarded in `_unconsumed_remainder`, `src/decision_memory/infrastructure/jsmastery_adapter.py:655-690`
**Problem**: `_unconsumed_remainder` attributes all text between consecutive bold labels (e.g., `**Positive**:` through the line before `**Negative**:`) to the first label's block, then discards it because Positive/Negative are consumed fields. Any non-bullet prose sitting between two labeled blocks (e.g., a plain sentence after the Positive bullets but before the Negative label) is lost rather than falling through to the body.
**Why it matters**: Against the current corpus this is dormant—every Consequences section is strict bold-label-then-bullets with no inter-label prose. A future corpus that writes a transition sentence between Positive and Negative lists would silently lose that content, violating AC-11 (unconsumed content must survive in the body).
**Suggested fix**: Either collect only lines that are strictly inside non-Positive, non-Negative labeled blocks (rather than attributing everything to the preceding label), or add an explicit inter-label prose passthrough.

### 🟡 "check" prefix may over-match in `_is_pointer` stub detection, `src/decision_memory/infrastructure/jsmastery_adapter.py:1075-1085`
**Problem**: The `_is_pointer` function treats any collapsed body whose non-name remainder starts with "check" as a stub pointer. A section containing "Check `rationale.md` for details." would be classified as a stub and its content discarded, even though the sentence has its own substance ("for details") and is not a pure pointer.
**Why it matters**: Dormant against the current corpus. "check" is semantically broader than "see"/"read"/"refer" and is the only pointer word in the list that can plausibly appear in a non-pointer sentence. The odds are low but the word list is a maintained calibration point.
**Suggested fix**: Remove "check" from the pointer-word tuple, or narrow it to "check the" / "check out" so bare "check" doesn't match. The known real stubs all use "See" or "Refer to", so dropping "check" loses no true positives.

## Nits
- ⚪ `src/decision_memory/infrastructure/jsmastery_adapter.py:655`, the docstring for `_unconsumed_remainder` could note that it attributes all text between consecutive bold labels to the first label, which is a simplification that holds for the current corpus's structured Consequences format but may need revisiting.

## Strengths
- The layering fix is clean and principled: three narrow `Callable` ports (`RecordWriter`, `RecordReader`, `CitedPathResolver`) injected at `cli.py`, with `test_adapt_corpus_writes_through_the_injected_writer` proving the application layer never touches the filesystem. The old layering violation is gone and the architecture is now strictly inward-dependency.
- Every regression fix has a targeted, well-named test. The three-way collision accumulation test and the preamble-scoping test (covering both `**Date**` and `**Supersedes**` leakage from body mentions) are particularly thorough.

## Test coverage
All new logic is covered by new tests. The 129-test suite passes clean. The existing non-cache path resolution assertion was relaxed from an exact count (10) to a robustness check (> 2), which is appropriate since the exact count depends on internal resolution steps. No untested branching logic or error paths.
