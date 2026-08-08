# Review, feature/jsmastery-specs-adapter, 2026-08-08

**Reviewed by**: gpt-5.6-sol (author on gpt-5 Codex)
**Scope**: 3 files, uncommitted
**Verdict**: Changes requested

## Summary
The change fixes the reported double-backtick parity failure by pairing maximal backtick runs only with a later run of the same length, bumps the adapter version, and adds a focused regression test. The target scenario now works and the documented live-corpus result reproduces at 107 unresolved occurrences with seven file evidence targets. One contract-level parsing issue remains: the new helper has no Markdown block context, so ordinary triple-backtick fenced blocks are treated as inline code spans and can still corrupt evidence and warning counts.

## Major
### 🟠 Fenced code blocks are parsed as inline code spans, `src/decision_memory/infrastructure/jsmastery_adapter.py:864`
**Problem**: `_inline_code_spans` scans every maximal backtick run in the raw document and pairs equal-length runs without excluding fenced code blocks. A normal block such as a triple-backtick fence around `missing.py` therefore returns the entire fenced body as one span; reproduced directly, `_inline_code_spans("```text\nmissing.py\n```")` returned `['text\nmissing.py\n']`, and `_extract_code_paths` counted one unresolved mention. That contradicts AC-4, which limits extraction to inline code spans, and the helper's CommonMark-style contract.
**Why it matters**: Specs commonly use fenced snippets for commands and examples. Paths inside those blocks can be silently added as file evidence when they happen to exist or inflate `unresolved_mention_count` when they do not, so the adapter's evidence and the calibration figures remain dependent on content the contract says to ignore. Same-length fences are affected while differently sized closing fences behave differently, making the result especially hard to reason about.
**Suggested fix**: Exclude closed fenced-block ranges before scanning inline delimiters, preferably by reusing the file's existing `_fenced_line_numbers` fence semantics, then run the equal-length delimiter logic only over non-fenced text. Add an adapter-level test containing both existing and missing path-shaped tokens inside a triple-backtick block plus a later real inline path, asserting that only the inline path affects evidence or the unresolved count.

## Strengths
- The equal-length delimiter walk correctly fixes the concrete double-backtick case without losing a later single-backtick path span, and the new test asserts both evidence and warning behavior.
- `ADAPTER_VERSION` is bumped with the mapping change, and the rationale's current 107-count/seven-target measurement reproduces through `JsmasteryAdapter.parse` on the real corpus.

## Test coverage
The new regression test covers the reported nested single-backtick content inside a double-backtick span and confirms parsing resumes for a later inline span. All 119 pytest tests pass; Ruff lint and format checks pass; strict mypy passes for `src` (the broader `mypy src tests` command has 159 pre-existing test-typing errors). Coverage is missing for the fenced-block boundary described above.
