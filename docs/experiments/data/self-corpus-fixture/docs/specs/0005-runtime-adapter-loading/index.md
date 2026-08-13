# 0005. Runtime adapter loading

**Date**: 2026-08-09
**Status**: Accepted

_Decision history, options, and references: [rationale.md](rationale.md)._

## Summary

Third party Python adapters become usable by naming one imported adapter instance. The built in `jsmastery-specs` adapter remains the default and follows the same protocol. Project settings can live in `.decision-memory.yml`, and adapter authors get a corpus validation loop plus a small working starter package.

## Requirements

**User stories**:

1. As a user, I want to select an installed adapter without forking this project, so I can adapt another decision format.
2. As an adapter author, I want to validate my adapter against a corpus without writing records, so I can separate source violations from adapter failures.
3. As a project maintainer, I want common adapter settings stored in the project, so repeated commands stay short and deterministic.

**Acceptance criteria**:

1. **AC-1**: `SourceAdapter` requires nonempty string properties `adapter_id` and `adapter_version` in addition to `discover`, `parse`, and `fingerprint`. `JsmasteryAdapter` supplies `jsmastery-specs` and its current version through those properties. `adapt_corpus` reads the manifest version from the adapter rather than from a separate argument.
2. **AC-2**: `--adapter` accepts the exact built in name `jsmastery-specs` or an absolute selector shaped as `package.module:attribute`. The module is an absolute dotted Python name and the attribute is one Python identifier. Relative modules, missing colons, empty parts, dotted attribute traversal, direct file paths, classes, and factories are rejected. The built in name contains a hyphen and therefore cannot collide with a valid Python module name.
3. **AC-3**: A third party selector is loaded with `importlib.import_module`, then its named attribute is read as an already created instance. Before any corpus access, the loader checks that both metadata values are nonempty strings and that `discover`, `parse`, and `fingerprint` are present and callable. The check does not claim to validate method signatures or behavior.
4. **AC-4**: With no adapter option or config value, `adapt` uses `jsmastery-specs` and preserves its current results. A selected third party instance runs through the same `adapt_corpus` use case, and the report prints `adapter_id` and `adapter_version` once near the start.
5. **AC-5**: Existing `validate FILE` behavior for canonical records remains intact. `validate [DIRECTORY] [--adapter SELECTOR]` runs corpus validation, and may omit the directory only when config supplies `corpus_root`. Passing `--adapter` with a file is a usage error with exit code `2`.
6. **AC-6**: Corpus validation calls `discover` once, then calls `fingerprint` before `parse` for every discovered source in deterministic order. If `fingerprint` raises, `parse` does not run for that source. It writes no records or manifest and prints no projected write state or output path. Its report includes adapter identity, discovery totals, every skip and collision, every source result, violations with stable rule ids, and a final summary.
7. **AC-7**: A source violation and an unexpected adapter exception are different result kinds in corpus validation. A violation means the adapter completed and found bad source data. An exception means the adapter implementation failed. Either makes the command exit `1`.
8. **AC-8**: If `discover` raises an `Exception`, the corpus run stops with exit code `1`. If `fingerprint` raises an `Exception`, `parse` is skipped for that source. If `parse` raises an `Exception`, that source stops after the parse failure. Either source failure records the failed operation plus exception type and message, then processing continues with later sources. `KeyboardInterrupt`, `SystemExit`, and other `BaseException` subclasses retain normal process behavior. No operation is retried.
9. **AC-9**: A malformed selector exits `2`. Module import, attribute lookup, adapter contract, and adapter execution failures exit `1`. Normal output names the selector, failed phase, original exception type, and message, without a traceback.
10. **AC-10**: Only `adapt` and directory corpus `validate` read `.decision-memory.yml`. They search from the current directory upward, use the nearest file, and stop at the nearest Git repository root when inside one or the filesystem root otherwise.
11. **AC-11**: The configuration is one mapping with optional `adapter`, `corpus_root`, and `output` string fields. An empty YAML document is an empty configuration. PyYAML `safe_load` reads it, then a Pydantic model with `extra="forbid"` rejects unknown keys and wrong types.
12. **AC-12**: Each setting resolves from command input, then configuration, then its default. `adapter` defaults to `jsmastery-specs`. A missing corpus root after precedence resolution is a usage error with exit code `2`. `output` defaults to `<resolved corpus_root>/.decision-memory/records`. Relative configured paths resolve from the configuration file directory. The output default is derived only after corpus root resolution, so a configured corpus root anchors the default output regardless of the current directory.
13. **AC-13**: A missing config file is not an error. An unreadable file, invalid YAML, nonmapping root, unknown key, or invalid field exits `1` and names the config path plus the precise parse or schema error. The command does not continue with partial config or defaults.
14. **AC-14**: The loader does not modify `sys.path`, add the config directory or corpus root, or load direct files. Imported adapters are documented as trusted Python code that executes with the CLI process permissions. No sandbox is provided.
15. **AC-15**: The adapter version written to the manifest is the loaded adapter's `adapter_version`. The starter adapter includes its version in its content based fingerprint, and changing only that version changes the fingerprint.
16. **AC-16**: `examples/starter-adapter/` is an independently installable package with a minimal `pyproject.toml`. It exports one adapter instance at `starter_adapter.adapter:adapter`, reads a tiny neutral Markdown format under `decisions/`, and includes one valid fixture plus one skipped fixture.
17. **AC-17**: The starter implements metadata, discovery, parsing, and content based fingerprinting in one module. It produces a valid canonical record from the valid fixture without copying jsmastery specific parsing rules.
18. **AC-18**: A separate adapter author guide covers package setup, selector syntax, the instance contract, metadata, result types, the no fabrication rule, exception behavior, config use, trusted code, and commands for corpus validation and adaptation. It directs deeper signature and behavior proof to feature 7.
19. **AC-19**: The complete unit suite, integration tests with a fake installed adapter, Ruff, and mypy pass. Tests prove the default built in path, third party import path, configuration precedence, validation mode split, failure containment, and starter instructions.
20. **AC-20**: The application use cases require the corpus root itself to be a directory but make no assumption about its internal format. `DiscoveryResult` gains an optional structured `corpus_error`. `JsmasteryAdapter` uses it when `docs/specs/` is absent, the starter uses it when `decisions/` is absent, and both `adapt` and corpus `validate` map it to exit code `3`. This preserves the built in invalid corpus behavior while allowing other layouts.

## Decision

**Chosen option**: Option 1, extend the existing adapter boundary with one explicit runtime loader

Keep the accepted `SourceAdapter` boundary and add one standard library import path around it. A selector resolves either the built in registry entry or one explicit module attribute holding an adapter instance. Configuration and reporting feed the same loaded instance into the existing use cases.

The loader uses manual shallow contract validation. It checks metadata values and callable presence but does not use `inspect.signature` or claim behavioral conformance. The runner up was `@runtime_checkable`, but it still needs separate metadata checks and provides the same presence only guarantee.

Configuration parsing stays in infrastructure. It reuses PyYAML and Pydantic, then crosses inward as a plain immutable `ProjectConfig`. A pure application resolver applies precedence and derived defaults. The runner up was resolving settings directly in the CLI, but that would hide rules inside presentation code and make them harder to test.

## Feature design

### Data model

`ProjectConfig` is a plain immutable boundary object. There is one object per discovered file and no persistence beyond that file.

| Field | Type | Required | Meaning |
|---|---|---:|---|
| `adapter` | `str` | no | Built in name or runtime selector |
| `corpus_root` | `Path` | no | Corpus used when command input omits it |
| `output` | `Path` | no | Record output directory |

There are no relationships, indexes, retention rules, or schema migrations. Unknown keys fail. Relative path strings become absolute paths against the config file directory before precedence is applied.

### State transitions

There is no persisted state machine. One command moves through `config resolution`, `adapter loading`, `contract check`, `corpus work`, and `reporting`. A failure stops at the boundary named in the acceptance criteria.

### Interface surface

| Surface | Layer | Key inputs | Key outputs | Key errors |
|---|---|---|---|---|
| `SourceAdapter` | application | corpus and discovered source objects | discovery, adaptation, fingerprint, identity, version | implementation returns structured source and corpus failures |
| `load_adapter(selector)` | infrastructure | resolved selector string | validated `SourceAdapter` instance | selector, import, attribute, metadata, or method presence failure |
| `load_project_config(start)` | infrastructure | current directory | config path and plain `ProjectConfig`, or absence | read, YAML, root shape, or schema failure |
| `resolve_runtime_settings(...)` | application | CLI values, optional config, config directory | adapter selector, corpus root, output | corpus root absent after precedence |
| `validate_corpus(root, adapter)` | application | resolved corpus root and loaded adapter | `CorpusValidationOutcome` | invalid root, discovery exception, per source adapter exception or violation |
| `adapt [CORPUS_PATH] [--adapter SELECTOR] [--output PATH] [--dry-run]` | CLI | optional corpus and runtime settings | existing adapt report with adapter identity | codes `1`, `2`, and `3` per this spec and spec 0003 |
| `validate FILE` | CLI | canonical record path and existing options | existing record violations | unchanged from spec 0002 |
| `validate [DIRECTORY] [--adapter SELECTOR]` | CLI | optional configured adapter and corpus directory | corpus validation report | codes `1`, `2`, and `3` |

`load_adapter` is a public infrastructure function so feature 7 can reuse the exact import and contract boundary. It does not become a domain or application service because Python module loading is infrastructure work.

Exit code `2` means required command input was absent or malformed, including a missing resolved corpus root. Exit code `3` means the user named a target but it is not usable as a corpus, either because the root is missing, is not a directory, or lacks the selected adapter's required layout. Exit code `1` means valid command input reached a runtime configuration, loading, adapter, or validation failure.

### Value sourcing

| Action | Value produced or displayed | Source |
|---|---|---|
| Config discovery | config path | nearest `.decision-memory.yml` from current directory within the search boundary |
| Settings resolution | adapter selector | CLI option, then config, then `jsmastery-specs` |
| Settings resolution | corpus root | CLI argument, then config, else error |
| Settings resolution | output directory | CLI option, then config, then `.decision-memory/records` beneath the resolved corpus root |
| Adapter loading | module | selector text before `:` |
| Adapter loading | attribute | selector text after `:` |
| Adapter reporting | adapter identity and version | properties on the loaded instance |
| Corpus validation | discovered and skipped sources | `adapter.discover` |
| Corpus validation | corpus format error | `DiscoveryResult.corpus_error` supplied by the selected adapter |
| Corpus validation | fingerprint result or exception | `adapter.fingerprint` for that source |
| Corpus validation | record violations or exception | `adapter.parse` for that source |
| Corpus validation | exit code | invalid root, adapter exceptions, and error severity violations collected by the run |
| Adapt manifest | adapter version | `adapter.adapter_version` |
| Adapt manifest | source root hint | the resolved corpus root at adapt time (spec 0007 AC-19) |
| Starter fingerprint | digest | contributing path and bytes in fixed order plus `adapter_version` |

### Key invariants

1. One selector resolves to one already created instance. The loader never guesses whether to call it.
2. The contract check completes before corpus access and proves presence only, not signatures or behavior.
3. Built in and third party adapters enter the same application use cases through `SourceAdapter`.
4. Record validation and corpus validation answer different questions and never silently switch modes.
5. Corpus validation writes nothing. `adapt --dry-run` remains the projected write report.
6. Source violations and adapter exceptions remain distinguishable through reporting.
7. Configuration never silently accepts an unknown key or falls back after an invalid file.
8. The resolved corpus root is the only base for the default output directory.
9. Traversal and reporting stay sequential and deterministic. No retry, concurrency, cache, or telemetry service is added.
10. An adapter version participates in both the manifest and that adapter's fingerprints.
11. The application validates only that a corpus root is a directory. Each adapter owns its required internal layout and reports a structured corpus error.

### Security model

There is no authentication or regulated data scope. A third party adapter is trusted executable Python code. Importing it runs module code with the same filesystem, environment, and process permissions as `decision-memory`. The CLI does not sandbox it or change the import path. The author guide and load errors state this boundary plainly.

Configuration uses `yaml.safe_load`. Strict validation prevents misspelled settings from silently selecting defaults. Config discovery stops at the project boundary when Git can identify one.

### Configuration required

No environment variable, credential, or new dependency is required. `.decision-memory.yml` may contain:

```yaml
adapter: vendor_adapter.runtime:adapter
corpus_root: ./project
output: ./project/.decision-memory/records
```

Every key is optional. The file shown is illustrative, not a required full shape.

### Critical test scenarios

1. Happy path: install the starter editable, run directory `validate` with `starter_adapter.adapter:adapter`, then run `adapt`; both report the same adapter identity and the valid fixture produces a valid record, verifies **AC-3**, **AC-4**, **AC-6**, **AC-16**, and **AC-17**.
2. Compatibility: run `adapt CORPUS_PATH` with no config or adapter option and compare the report, records, and manifest with the accepted built in behavior, verifies **AC-1** and **AC-4**.
3. Selector failure table: exercise every malformed selector, missing module, import time exception, missing attribute, class, factory, empty metadata, missing method, and noncallable method, verifies **AC-2**, **AC-3**, and **AC-9**.
4. Mode split: validate one canonical record unchanged, validate one corpus without writes, and reject `validate FILE --adapter ...`, verifies **AC-5** and **AC-6**.
5. Failure distinction: one fake source returns an error violation, one raises from `fingerprint`, one raises from `parse`, and a later source still runs; the report distinguishes each result, verifies **AC-7** and **AC-8**.
6. Discovery failure: a fake adapter raises from `discover`; no source operation runs and the report names the phase, verifies **AC-8** and **AC-9**.
7. Config matrix: prove nearest file selection, Git root stopping, empty config, all precedence combinations, unknown key failure, invalid YAML, relative paths, and the composed default output, verifies **AC-10** through **AC-13**.
8. Trust boundary: prove the loader accepts only importable modules on the existing Python path and never inserts the config or corpus directory, verifies **AC-14**.
9. Version change: change only the fake adapter version and prove both manifest version and fingerprint change, verifies **AC-1** and **AC-15**.
10. Documentation: follow the guide from a clean environment through editable install, corpus validation, and adaptation, verifies **AC-18** and **AC-19**.
11. Format boundary: pass an existing directory with no `docs/specs/` to the built in adapter and no `decisions/` to the starter; each names its own missing structure and exits `3`, verifies **AC-20**.

## Build plan

The Skateboard approach starts with one complete third party path through the existing `adapt` command, then adds the author loop, project convenience, and teaching artifact.

- [x] 1. Extend `SourceAdapter` with identity and version, add the structured corpus error to discovery, update `JsmasteryAdapter`, remove the separate `adapter_version` argument and hard coded `docs/specs/` precondition from `adapt_corpus`, reconcile spec 0003 with the shipped protocol and manifest contract, and keep all built in tests green, satisfies **AC-1**, **AC-4**, **AC-15**, and **AC-20**.
- [x] 2. Build the strict selector parser and infrastructure loader, wire `--adapter` into `adapt`, and prove one fake installed instance end to end, satisfies **AC-2**, **AC-3**, **AC-4**, **AC-9**, and **AC-14**.
- [x] 3. Add `validate_corpus` with distinct violation and adapter failure outcomes, then route directory `validate` through it while preserving file validation, satisfies **AC-5** through **AC-9**.
- [x] 4. Add config discovery, strict parsing, precedence resolution, optional corpus arguments, and composed path defaults, satisfies **AC-10** through **AC-13**.
- [x] 5. Add the independently installable starter package, fixtures, and author guide, then exercise the documented commands against the real CLI, satisfies **AC-16** through **AC-18**.
- [x] 6. Complete the failure matrix, integration coverage, Ruff, mypy, and the fast unit suite, satisfies **AC-1** through **AC-20**.

## Consequences

**Positive**:

1. Adapter authors can use the real CLI and protocol without changing this repository.
2. One explicit object path produces precise import and attribute errors.
3. Adapter identity and version now work the same way for built in and third party implementations.
4. Corpus validation gives authors a write free loop that is distinct from projected adaptation output.
5. The default built in experience stays compatible.

**Negative and tradeoffs**:

1. Loading an adapter executes trusted third party code with full CLI permissions.
2. The shallow check cannot detect a wrong method signature or broken behavior before the method runs.
3. Adding metadata properties changes the accepted protocol and touches shipped jsmastery code plus its tests.
4. Overloading `validate` by file versus directory is concise but makes path type part of the command contract.
5. Upward config search adds hidden project context, even though strict reporting and the Git boundary make it visible.
6. Adapter identity is self asserted. A third party adapter can report `jsmastery-specs`, so identity in reports and manifests is useful provenance but not proof that the built in implementation ran.

**Neutral**:

1. There is no database migration, feature flag, or staged rollout. Reverting the loader wiring restores the prior built in only path.
2. Python entry point discovery remains a possible later convenience. It is not required for explicit selectors.
3. `test-adapter` remains responsible for signatures, protocol behavior, anti fabrication checks, and format drift fixtures.

## Later evolution

Spec [0006](../0006-adapter-conformance-test-adapter/index.md) expands the teaching starter from two flat fixtures under `decisions/` to a recursive `decisions/**/*.md` corpus with all five conformance categories. It also gives duplicate filename stems an explicit selection rule: use the first corpus relative POSIX path in lexical order and report every collision path in that order. This later teaching expansion does not change the acceptance evidence for AC-16 through AC-19 as originally shipped.

## Follow-up

1. Spec 0006 defines signature and behavioral conformance checks and a shared `select_adapter` entry point that delegates third party selectors to `load_adapter` rather than creating a second loading path.
2. Consider Python package entry point discovery only after real adapter authors show that explicit selectors are a usability problem.

## Rationale

Reasoning and options: see [rationale.md](rationale.md).
