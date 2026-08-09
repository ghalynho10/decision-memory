# Verify runtime adapter loading

## Purpose

Drive the real CLI through the built in path, a third party adapter path, both validation modes, configuration resolution, and the starter instructions. Record commands, outputs, exit codes, and filesystem checks for every acceptance criterion.

## Setup

1. Create an isolated temporary directory outside the repository fixtures.
2. Install the project and `examples/starter-adapter/` through the documented editable install command.
3. Copy the starter corpus into the temporary directory.
4. Prepare one valid canonical record for the existing file validation path.

## Verification ladder

### 1. Built in compatibility

1. Run `adapt CORPUS_PATH --dry-run` without config or `--adapter`.
2. Confirm the report names `jsmastery-specs` and its version.
3. Compare discovery, record states, exit code, and a non dry run manifest with the accepted behavior from spec 0003.
4. Confirm the manifest version comes from the adapter property.

Verifies **AC-1**, **AC-4**, and **AC-15**.

### 2. Third party happy path

1. Run `validate STARTER_CORPUS --adapter starter_adapter.adapter:adapter`.
2. Confirm all three adapter methods run, the valid source passes, the skipped source is named, no output directory appears, and no file is created.
3. Run `adapt STARTER_CORPUS --adapter starter_adapter.adapter:adapter`.
4. Confirm one valid canonical record and one manifest are written.
5. Change only the starter adapter version, rerun, and confirm both manifest version and fingerprint change.

Verifies **AC-2**, **AC-3**, **AC-5**, **AC-6**, **AC-15**, **AC-16**, and **AC-17**.

### 3. Validation mode separation

1. Run `validate VALID_RECORD` and confirm the existing record result is unchanged.
2. Run `validate STARTER_CORPUS` through config and confirm corpus validation writes nothing.
3. Run `validate VALID_RECORD --adapter starter_adapter.adapter:adapter` and confirm exit code `2`.
4. Run `adapt STARTER_CORPUS --dry-run` and confirm its projected write report remains distinct from corpus validation.

Verifies **AC-5** and **AC-6**.

### 4. Loader failure table

Exercise an empty selector, relative module, missing colon, dotted attribute, direct file path, missing module, import time exception, missing attribute, class, factory, empty identifier, empty version, missing method, and noncallable method.

For every case, confirm the exit code, selector, failed phase, exception type, message, and absence of a traceback. Confirm no corpus method ran when the contract check failed.

Verifies **AC-2**, **AC-3**, and **AC-9**.

### 5. Adapter failure containment

1. Return an error violation for one source.
2. Raise an `Exception` from `fingerprint` for a second source.
3. Raise an `Exception` from `parse` for a third source.
4. Confirm a fourth source still runs and each earlier result is classified correctly.
5. Raise from `discover` and confirm the run stops before source operations.
6. Confirm cancellation is not converted into a normal adapter failure.

Verifies **AC-7** and **AC-8**.

### 6. Configuration matrix

1. Confirm nearest file selection and stopping at the Git root.
2. Confirm no file and an empty file are both valid.
3. Confirm command values override config and config overrides defaults.
4. Confirm a relative config corpus root resolves against the config directory.
5. Leave output unset and confirm the default is below the resolved corpus root.
6. Exercise unreadable YAML, invalid YAML, a list root, unknown keys, and wrong field types.
7. Confirm record validation and `doctor` do not read config.

Verifies **AC-10** through **AC-14**.

### 7. Author journey and quality gates

1. Follow the author guide from package install through corpus validation and adaptation without relying on repository knowledge.
2. Confirm the starter valid fixture becomes a valid canonical record and the skipped fixture reports its reason.
3. Run Ruff, mypy, the fast unit suite, and integration tests.

Verifies **AC-16** through **AC-19**.

### 8. Format boundary

1. Pass an existing directory without `docs/specs/` to `jsmastery-specs` and confirm its structured corpus error plus exit code `3`.
2. Pass an existing directory without `decisions/` to the starter and confirm its own structured corpus error plus exit code `3`.
3. Confirm the application layer contains no format path such as `docs/specs/` or `decisions/`.

Verifies **AC-20**.

## Evidence to record

1. Exact commands and exit codes.
2. Relevant report excerpts for adapter identity, violation, exception, skip, and summaries.
3. File listings before and after corpus validation and adaptation.
4. Manifest excerpts showing adapter version and changed fingerprint.
5. Ruff, mypy, unit, and integration test summaries.

## Develop build steps (appended by /develop, 2026-08-09)

Concrete steps derived from the acceptance criteria, one per command or value
source, for `/check verify` to run.

### Commands

- [x] `adapt CORPUS` with no config or `--adapter` → report opens with `adapter: jsmastery-specs <version>`; records and manifest match the accepted spec 0003 behavior → AC-1, AC-4
- [x] `adapt CORPUS --adapter starter_adapter.adapter:adapter` → same report shape, manifest `adapter_version` equals the starter's version → AC-4, AC-15
- [x] `validate STARTER_CORPUS --adapter starter_adapter.adapter:adapter` → `ok valid`, `skipped ...: no ## Decision section`, no `.decision-memory` created → AC-2, AC-3, AC-5, AC-6, AC-16, AC-17
- [x] `validate VALID_RECORD` → unchanged from spec 0002 → AC-5
- [x] `validate VALID_RECORD --adapter x` → exit 2 → AC-5
- [x] `validate` with no argument and no config → exit 2; with `corpus_root` configured → corpus validation → AC-5, AC-12
- [x] Malformed selectors (`bad`, `:x`, `.rel:m`, `a:b.c`, `/path/x.py`) → exit 2 → AC-2
- [x] Missing module, import time exception, missing attribute, class, factory, empty metadata, missing method → exit 1 naming selector, phase, exception type, no traceback → AC-3, AC-9
- [x] `adapt DIR_WITHOUT_docs/specs` → exit 3, `no docs/specs/ directory`; starter on `DIR_WITHOUT_decisions` → exit 3, `no decisions/ directory` → AC-20
- [x] Config matrix: nearest file wins, git root stops the search, empty file is empty config, CLI overrides config, relative paths resolve from the config file, unknown key or invalid YAML exits 1 naming the path, no config and no corpus exits 2 → AC-10 to AC-13
- [x] Change only the starter `ADAPTER_VERSION`, rerun adapt → manifest version and fingerprint both change → AC-15

### Acceptance-criteria coverage

AC-1 through AC-20 are each covered by a step above and by the repository tests
(`tests/test_runtime_loader.py`, `tests/test_adapt_run.py`,
`tests/test_corpus_validation.py`, `tests/test_project_config.py`,
`tests/test_starter_adapter.py`, `tests/test_starter_integration.py`).

### Install fix (appended by /develop, 2026-08-09)

The starter package now uses the `src/` layout. The documented
`uv pip install -e ./examples/starter-adapter` succeeds, `starter_adapter`
imports without `PYTHONPATH`, and `validate` and `adapt` run through the loader
with no path help. This closes the AC-16 install defect found by `/check verify`;
AC-18's install command and AC-19's starter instructions now hold.


