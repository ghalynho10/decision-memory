# Review, feature/test-adapter, 2026-08-09

**Reviewed by**: DeepSeek V4 Pro (author on DeepSeek V4 Flash)
**Scope**: 13 files, branch vs base (main)
**Verdict**: Approve with nits

## Summary

This feature adds a comprehensive adapter conformance suite (`test-adapter SELECTOR --cases PATH`) with a declarative YAML manifest, a 1255-line application engine, and a broad test suite (~1800 lines of tests). The architecture cleanly separates the pure application engine from infrastructure (Pydantic/YAML manifest loading, tempfile-based fixture workspaces). The engine implements every check from the spec's emission matrix, including exact record comparison, corruption variants, fingerprint coverage, write detection, and preservation semantics. Test coverage is thorough across happy path, boundaries, errors, and the five manifest categories.

The code is well-structured and follows the project's Clean Architecture rules strictly. A few nits around formatting and a minor test gap are noted below. No blockers or majors.

## Minor

### 🟡 `target_fields` formatting uses JSON serialization, `src/decision_memory/cli.py:508`

**Problem**: `_json(sorted(case.target_fields))` produces JSON lists like `["decision.chosen"]` rather than the prose-like `[decision.chosen]` suggested by the spec's report grammar (AC-15).

**Why it matters**: Minor inconsistency between the report's human-readable style elsewhere (colon-separated detail, bare rule ids) and JSON-formatted field lists.

**Suggested fix**: Use a simple comma-joined representation (e.g., `[decision.chosen, why]`) unless the JSON encoding was deliberate. If deliberate, document the choice.

### 🟡 `_record_difference` fallback is uninformative, `src/decision_memory/application/conformance.py:302`

**Problem**: When two non-None records have all dataclass fields equal via `!=` but still differ (e.g., a `__eq__` override that ignores some fields), the fallback message is `"records differ"` with no further detail.

**Why it matters**: If this path is ever hit, the failure message won't help the adapter author diagnose the issue. It's currently unreachable with the existing record types but could become reachable if the record model adds fields with custom equality.

**Suggested fix**: Add field-by-field diff detail to the fallback, or assert that this path is unreachable with a comment explaining why.

## Nits

- ⚪ `src/decision_memory/cli.py:31`, unused import `CheckResult` in the diff context: `CheckResult` is imported but only used as a type annotation inside `_print_conformance_check`. While valid for type checking, it's the only one of the four conformance imports used purely as a type hint; the others (`ConformanceManifest`, `ConformanceCase`, `ConformanceOutcome`) are used in function signatures and instance access.
- ⚪ `src/decision_memory/application/conformance.py:303`, `_record_difference` fallback: The docstring for `_record_difference` says it returns a "concise message naming the first record mismatch" but the fallback message `"records differ"` is generic. Consider renaming it or noting it's unreachable.
- ⚪ `tests/test_conformance_engine.py:359`, the `TestResultTypes.test_a_lookalike_discovery_result_is_rejected` test uses `cast(SourceAdapter, WrongAdapter())` which suppresses type errors. A comment noting this is intentional (the test validates runtime rejection of a deliberately wrong type) is present in surrounding tests but slightly less explicit here.
- ⚪ `src/decision_memory/infrastructure/conformance_manifest.py`, the `_LEAF_FIELDS` and `_INDEXED_FIELDS` frozen sets are module-level constants. Consider whether the comment "spec 0002 fields" at line ~120 should link to the spec path for easier future maintenance.

## Strengths

- **Clean Architecture adherence is exemplary**: `conformance.py` imports zero framework code (no Typer, Pydantic, PyYAML, pytest, tempfile, shutil), only the standard library and domain/application types. The fixture port (`ConformanceFixturePort`) is a Protocol that keeps filesystem operations out of the application layer entirely.
- **Test coverage is thorough and well-organized**: The engine tests (`test_conformance_engine.py`, ~1014 lines) exercise every property from the spec: exact comparison, grammar drift confidence, corruption variants, fingerprint coverage, write detection, preservation/cleanup semantics, adapter exceptions, `KeyboardInterrupt` passthrough, signature boundaries, and result type rejection. The manifest tests (`test_conformance_manifest.py`, ~302 lines) cover every schema and path boundary. The CLI tests cover all exit codes and deterministic output.
- **The engine's emission matrix implementation is correct and readable**: `_Engine` maps 1:1 to the spec's emission table. Each check method emits exactly the checks its prerequisite allows, and dependent checks are cleanly omitted after failures. The `_Session` dataclass tracking failures per workspace, combined with `_finish` deciding preserve vs. cleanup, matches AC-17 precisely.
- **Path safety is rigorous**: The manifest loader rejects path escape (`..` components and absolute paths), symlinks in corpus trees, symlink path components, and non-regular files for expected records and required files. The engine's `_path_problems` function validates every discovered path against containment invariants at runtime.

## Test coverage

The test signal is `configured`. Coverage assessment:

- **Engine tests** (`test_conformance_engine.py`): Covers happy path, exact record comparison (including invented field detection), discovery comparison, contract signatures (valid, invalid required params, variadic/optional), result type rejection, adapter exceptions (including `KeyboardInterrupt` passthrough and continued case execution), determinism (discovery, parse, fingerprint changes), grammar drift confidence (confident, skipped, absent, non-confident), fingerprint coverage, write detection, preservation/cleanup lifecycle, corpus errors, fixture operation failures (prepare, snapshot, preserve, cleanup), and shared required file corruption. **Comprehensive.**

- **Manifest tests** (`test_conformance_manifest.py`): Covers happy path, unsupported version, unknown keys, duplicate case ids, empty cases, duplicate declared paths, required-file-must-be-contributing enforcement, skip case subject requirements, valid case nonnull record requirement, collision path count, target field requirements, canonical field vocabulary validation, missing corpus, path escape, missing subject, symlink rejection, non-regular expected records, invalid YAML records, and unparseable YAML. **Comprehensive.**

- **CLI tests** (`test_conformance_cli.py`): Covers built-in manifest pass-through, schema failure exit code, missing manifest, malformed selector (exit 2), missing module (exit 1), missing `--cases` option, and deterministic output. **Adequate.**

- **Built-in tests** (`test_conformance_builtin.py`): Covers engine pass-through for the real built-in manifest and verifies all five categories are present. **Adequate.**

- **Runtime loader tests** (`test_runtime_loader.py`): The diff adds no new tests for `select_adapter` specifically, but the existing suite covers `load_adapter` exhaustively. `select_adapter`'s built-in path is tested via `test_conformance_builtin.py` and `test_conformance_cli.py`. The third-party delegation is tested implicitly via the CLI integration tests. **Minor gap**: no dedicated unit test for `select_adapter` returning a `LoadFailure` on built-in adapter construction failure — this code path exists (try/except around `JsmasteryAdapter()`) but is untested.

- **Starter adapter tests**: Cover recursive discovery, collision behavior, and UnicodeDecodeError handling. **Adequate for the expanded behavior.**
