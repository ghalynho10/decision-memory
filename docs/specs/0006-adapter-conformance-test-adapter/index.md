# 0006. Adapter conformance suite and `test-adapter`

**Date**: 2026-08-09
**Status**: Accepted

## Summary

Adapter authors get one command that checks the real adapter protocol, compares complete records with declared expectations, and exercises deliberate malformed input. Format authors define grammar drift cases because only they know their grammar. The shared suite adds only two closed corruption checks that are safe for required UTF8 text files.

## Requirements

**User stories**:

1. As an adapter author, I want one command that reports every reachable independent protocol and fixture failure, so I can repair my adapter before people trust its records.
2. As a maintainer, I want built in and third party adapters to run through the same conformance engine, so the built in path gets no private exceptions.
3. As a reviewer, I want declarative expectations and exact record comparison, so I can inspect what an adapter claims without executing assertion code.

**Acceptance criteria**:

1. **AC-1**: `decision-memory test-adapter SELECTOR --cases PATH` accepts `jsmastery-specs` or the existing `package.module:attribute` selector and requires `--cases`. One public infrastructure function, `select_adapter`, handles the built in name and delegates third party selectors to `load_adapter`. `adapt`, corpus `validate`, and `test-adapter` all use it.
2. **AC-2**: The manifest requires `schema_version: 1`, rejects unsupported versions, unknown keys, wrong types, duplicate case ids, missing category fields, missing paths, path escape, and prohibited symlinks before loading the adapter. Every manifest failure exits `1` and names the failing field or path.
3. **AC-3**: A manifest contains one or more isolated cases in manifest order. The fixed categories are `valid`, `skip`, `wrong_heading`, `missing_required_field`, and `collision`. Each category enforces its own required and forbidden fields.
4. **AC-4**: Every case declares the complete discovery result and a result for every discovered source. The suite compares the full parsed `CanonicalDecisionRecord` or `null`, attempted fields, unresolved mention count, and each violation severity, rule, and field. Valid expected records are checked against their case corpus with Git unavailable. They may have declared warnings but no errors.
5. **AC-5**: Discovery comparison uses ordered sequence equality for sources, contributing files, skips, collisions, and collision paths. All actual paths normalize relative to the copied corpus root, and duplicate paths are rejected. Every skip reason is nonempty without locking its prose. A nonnull `corpus_error` is forbidden in a conformance case and fails `discovery.corpus_usable`.
6. **AC-6**: Every suite supplies at least one case in each fixed category. `wrong_heading` and `missing_required_field` require an existing `subject_path` plus nonempty canonical `target_fields`. `skip` also requires an existing `subject_path`.
7. **AC-7**: A malformed grammar subject must exist in the original case corpus, but may be absent, skipped, or discovered after the adapter runs. It passes only when it is absent from discovery, is explicitly skipped, produces `record=None`, or produces a record with at least one error severity violation. A valid record or a warning only record fails as confident output. `target_fields` are validated coverage labels printed with the case, not inferred assertions about a skipped result.
8. **AC-8**: Each expected source may name `required_files`, and every manifest names at least one. Every required file must exist, be a regular required UTF8 text file, and appear in that source's `contributing_files`. For each required file, the suite creates separate empty byte and fixed invalid UTF8 variants. Every source listing that path as a contributing file is affected and must become absent or non confident. All other sources retain their expected results.
9. **AC-9**: Any `Exception` from adapter metadata access, signature inspection, discovery, fingerprinting, or parsing is caught and reported as a failed conformance check. It never passes as graceful degradation. `KeyboardInterrupt`, `SystemExit`, and other `BaseException` values escape normally. Checks that depend on a failed operation are omitted, while independent operations and later cases continue.
10. **AC-10**: Each bound protocol method declares a first positional only or positional or keyword parameter that can receive the protocol value. It has no other required positional or keyword only parameter. Extra optional parameters, `*args`, `**kwargs`, defaults, and absent annotations are allowed. Metadata and fingerprints are nonempty strings, and method results use the exact contract result classes.
11. **AC-11**: Every discovered source has a nonempty unique id, `corpus_root` exactly equal to the copied case root, an existing root inside it, and at least one existing contributing file inside it. Wrong result types fail before the suite reads their fields. Results that only resemble the contract objects are rejected.
12. **AC-12**: Repeating `discover`, `fingerprint`, and `parse` with the same adapter instance and inputs returns equal complete structured results. Every normal and corruption workspace is discovered independently from its copied root.
13. **AC-13**: Repeated fingerprints are equal and nonempty. Changing each contributing file in a fresh copy changes the fingerprint, and `AdaptationResult.fingerprint` equals the direct fingerprint for the same source. The probe remaps the baseline `DiscoveredSpec` to the fresh copy without rediscovery and tests inclusion of contributing files, not exclusion of unrelated corpus state.
14. **AC-14**: Every case and generated variant runs in a suite owned copy. A before and after snapshot compares all relative paths, entry kinds, regular file bytes, and permission bits, so additions, changes, and deletions by adapter code fail conformance. The suite makes no claim about writes elsewhere because the adapter remains trusted code.
15. **AC-15**: The human report shows each executed check as pass or fail with a stable rule id, fixed coordinates, concise failure detail, totals, and a final result. A normative emission matrix defines each check and its prerequisite. Order is fixed by phase, manifest case order, then declared source and path order. No JSON report is added.
16. **AC-16**: Exit `0` means every executed check passed. Exit `1` covers adapter loading, manifest reading, fixture preparation, execution, or conformance failure. Exit `2` is reserved for malformed text supplied on the command line, including selector syntax. Exit `3` is not used.
17. **AC-17**: Successful temporary copies are removed. When a workspace fails before cleanup, the suite calls preservation once. Successful preservation attaches the absolute artifact path to the first failed check for that workspace. A preservation failure emits `fixture.preserve`, skips cleanup, and carries the last known root only when it still exists. A cleanup failure emits `fixture.cleanup`, does not call preservation, and carries its last known root only when it still exists. Cleanup may have partially removed that root, so the suite does not claim it is an intact artifact. Preparation, snapshot, preservation, and cleanup failures have fixed rule ids and exit `1`.
18. **AC-18**: The conformance engine is a public typed application function used by the CLI and project tests. It has no Typer, Pydantic, PyYAML, pytest, or concrete filesystem imports. A typed fixture workspace port defines copying, mutation, snapshots, preservation, and cleanup. No pytest plugin is added.
19. **AC-19**: The starter adapter discovers `decisions/**/*.md` while preserving existing flat behavior. It derives ids from filename stems, orders candidate files by corpus relative POSIX path, selects the first path for a duplicate id, and reports every colliding path in that same order. A person copying the starter can read this rule in its code and guide.
20. **AC-20**: `jsmastery-specs` and the starter adapter each ship a strict manifest and pass the same engine. The built in manifest runs in the fast unit suite. The installed starter package runs through the real CLI in an integration test.
21. **AC-21**: The adapter author guide documents the manifest, every category, exact record comparison, corruption behavior, report, exit codes, trusted execution boundary, and how to reproduce a failed preserved case. It explains that this feature expands the two fixture starter shipped by spec 0005 AC-16 into a recursive teaching corpus with all five conformance categories.
22. **AC-22**: The feature adds no dependency, database, environment variable, credential, cache, concurrency, telemetry service, sandbox, subprocess, or internal timeout. Ruff, mypy strict mode, the fast unit suite, and the marked integration suite pass.

## Decision

**Chosen option**: Option 1: Declarative format cases plus closed universal corruption checks

Use a strict versioned YAML manifest for format specific cases, compare complete canonical records, and add only empty bytes and a fixed invalid UTF8 payload for author marked required files. Expose one typed application engine through the `test-adapter` CLI and project tests. (basis: specs 0002, 0003, and 0005; strict declarative contract validation; golden record comparison)

The manifest loader uses `yaml.safe_load` and Pydantic in infrastructure, then converts validated input into immutable plain application objects. The application engine receives a `SourceAdapter`, a plain manifest, and a narrow fixture workspace port. The runner up was manual dictionary validation, but it would duplicate the strict boundary behavior already used for project configuration and make nested errors less precise. (basis: `AGENTS.md`, Clean Architecture and existing dependencies; spec 0005 strict configuration parsing)

Fixture copying, byte replacement, tree snapshots, preservation, and cleanup live behind an infrastructure workspace adapter built with `tempfile`, `shutil`, and `pathlib`. The runner up was direct filesystem work in the CLI, but that would put business rules in presentation code and make the public engine unusable from tests. (basis: `AGENTS.md`, dependency rule; ports and adapters)

Semantic record comparison uses the existing canonical parser and model, not serialized text equality. Fingerprint mutation appends a fixed probe to one contributing file in a fresh copy and calls only `fingerprint`, so the property check does not pretend to know the source grammar. The runner up was storing expected digest strings, which would prescribe an algorithm instead of checking the promised behavior. (basis: specs 0002 and 0005; property testing of observable invariants)

## Feature design

### Data model

The manifest is a versioned declarative document. Pydantic models exist only in infrastructure. The loader converts them into these plain immutable application fields:

| Entity | Field | Type | Required | Rule |
|---|---|---|---:|---|
| `ConformanceManifest` | `schema_version` | `Literal[1]` | yes | Exact integer version |
| `ConformanceManifest` | `cases` | `tuple[ConformanceCase, ...]` | yes | Nonempty, case ids unique |
| `ConformanceCase` | `id` | `str` | yes | Nonempty |
| `ConformanceCase` | `category` | fixed enum | yes | One of the five categories |
| `ConformanceCase` | `corpus` | absolute `Path` | yes | Existing contained directory after resolution |
| `ConformanceCase` | `subject_path` | relative `Path` or `None` | by category | Exists in original corpus, may have no discovery match |
| `ConformanceCase` | `target_fields` | `frozenset[str]` | by category | Nonempty canonical paths when present |
| `ConformanceCase` | `expect` | `DiscoveryExpectation` | yes | Complete expected discovery |
| `DiscoveryExpectation` | `sources` | `tuple[SourceExpectation, ...]` | yes | May be empty, ids unique |
| `DiscoveryExpectation` | `skips` | `tuple[SkipExpectation, ...]` | yes | May be empty |
| `DiscoveryExpectation` | `collisions` | `tuple[CollisionExpectation, ...]` | yes | May be empty |
| `SourceExpectation` | `id` | `str` | yes | Nonempty |
| `SourceExpectation` | `root` | relative `Path` | yes | Existing inside corpus |
| `SourceExpectation` | `contributing_files` | `tuple[Path, ...]` | yes | Nonempty, existing inside corpus |
| `SourceExpectation` | `required_files` | `tuple[Path, ...]` | yes | Subset of contributing files |
| `SourceExpectation` | `result` | `ResultExpectation` | yes | Expected parse result |
| `ResultExpectation` | `record` | `CanonicalDecisionRecord` or `None` | yes | Loaded from the YAML path before adapter loading |
| `ResultExpectation` | `attempted_fields` | `frozenset[str]` | yes | Canonical field paths, may be empty |
| `ResultExpectation` | `unresolved_mention_count` | `int` | yes | Zero or greater |
| `ResultExpectation` | `violations` | `tuple[ViolationExpectation, ...]` | yes | Ordered, may be empty |
| `ViolationExpectation` | `severity` | `Severity` | yes | `warning` or `error` |
| `ViolationExpectation` | `rule` | `str` | yes | Nonempty |
| `ViolationExpectation` | `field` | `str` | yes | YAML `null` becomes the contract's empty string |
| `SkipExpectation` | `path` | relative `Path` | yes | Exact skipped path |
| `CollisionExpectation` | `id` | `str` | yes | Nonempty |
| `CollisionExpectation` | `paths` | `tuple[Path, ...]` | yes | At least two entries |
| `CollisionExpectation` | `used` | relative `Path` | yes | Member of `paths` |
| `Workspace` | `root`, `kind`, optional mutation path and kind, baseline snapshot | typed values | yes | One isolated original or generated variant |
| `CorpusSnapshot` | ordered entries | tuple | yes | Relative path, entry kind, permission bits, and file bytes |
| `FixtureFailure` | operation, exception type, message, optional last known path | typed values | yes | Infrastructure failure returned through the port |
| `CheckResult` | `rule` | fixed rule id | yes | Vocabulary in Report contract |
| `CheckResult` | `case_id`, `source_id`, `path`, `operation`, `variant` | value or `None` | yes | Separate report coordinates |
| `CheckResult` | `status` | `pass` or `fail` | yes | Executed checks only |
| `CheckResult` | `detail` | `str` | yes | Empty for a pass, concise for a failure |
| `CheckResult` | `artifact_path` | absolute `Path` or `None` | yes | Present only for a preserved copy |
| `ConformanceOutcome` | identity, version, checks, totals, exit code | typed values | yes | Returned by the public application engine |

Case corpus and expected record paths resolve from the manifest directory and may not escape it. Paths inside discovery expectations resolve from the case corpus. `subject_path` must exist in the original fixture. Each required file must exist and be listed in its source expectation's contributing files. The manifest itself and each expected record must be a regular non symlink file with no symlink path component. Every case corpus is scanned recursively before adapter loading and fails if any entry or path component is a symlink.

`valid` requires at least one expected source with a nonnull record and no error violations. Declared warnings are allowed. `skip` requires an existing subject that appears exactly once in expected skips. `wrong_heading` and `missing_required_field` require an existing subject, nonempty target fields, and no confident record for that subject, but the subject may have zero discovery matches. Their target fields are coverage labels printed in the report. They do not require field specific violations when the subject is absent or skipped. `collision` requires at least one exact collision with two or more paths. All five categories still declare complete discovery, so unexpected output always fails.

There is no database, index, retention policy, or migration.

The YAML nesting is normative:

```yaml
schema_version: 1
cases:
  - id: valid-example
    category: valid
    corpus: cases/valid-example
    expect:
      sources:
        - id: DM-0001
          root: decisions/0001.md
          contributing_files:
            - decisions/0001.md
          required_files:
            - decisions/0001.md
          result:
            record: expected/DM-0001.md
            attempted_fields: []
            unresolved_mention_count: 0
            violations: []
      skips: []
      collisions: []
```

All fields shown are required, including empty lists and `record` when its value is `null`. Manifest paths use forward slashes. `schema_version` is the integer literal `1`. Case ids are nonempty and unique. Source ids are nonempty and unique inside one discovery result. Duplicate paths in any declared sequence fail schema validation. `unresolved_mention_count` is a nonnegative integer. Violation severity is `warning` or `error`, its rule is nonempty, and its field is a canonical field path or `null`.

`subject_path` is required only for `skip`, `wrong_heading`, and `missing_required_field`. `target_fields` is a nonempty list required only for `wrong_heading` and `missing_required_field`. Every target is a canonical field path. Other categories forbid both fields. The subject of a `skip` case must appear exactly once in `expect.skips`. A malformed subject may be skipped, absent, or present with the non confident result from AC-7. If it is represented, its relative root or skip path matches the subject. Any unexpected source still fails the complete discovery comparison.

`contributing_files` is nonempty. `required_files` may be empty on a source, but each manifest must declare at least one required file so both universal corruption checks execute. A collision has a nonempty id, at least two paths, and a `used` path that appears in that list. Expected record paths are relative to the manifest directory. Discovery, subject, contributing, required, skip, and collision paths are relative to the case corpus.

The YAML boundary value for `result.record` is a relative path or `null`. A nonnull path is parsed into a `CanonicalDecisionRecord` during manifest loading, so the application never reads that file. Unknown canonical fields fail manifest loading. Validation uses the expectation's attempted fields and unresolved mention count, every regular case corpus file as an existing relative path, no known commits, and `git_available=False`. A `valid` expected record passes when validation returns no error. Every expected warning is declared in the result expectation.

Expected record comparison is semantic. Every record field and ordered list is compared. Attempted fields compare as a set. Violation comparison preserves list order, ignores reason prose, and compares severity, rule, and field. YAML `field: null` normalizes to the contract's empty field string. Discovery sources, contributing files, skips, collisions, and collision paths compare as ordered sequences after actual paths become corpus relative POSIX paths.

A result expectation may optionally declare `field_sources`, a map from canonical value path to a list of source references, each with a relative `path` and a `section` (the reserved `preamble` names metadata before the first H2). When declared, the adapter's provenance map is normalized, deduplicated, and sorted by path then section and compared exactly against it, locking the schema version 2 output contract (spec 0007 AC-2). When absent, provenance is not compared.

The empty corruption payload is `b""`. The invalid UTF8 payload is exactly `b"\xff\xfe\xfa"`. Fingerprint coverage appends exactly `b"\nconformance fingerprint probe\n"` to one contributing file in a fresh copy and calls only `fingerprint` on the remapped discovered source.

### Starter adapter expansion

Spec 0005 AC-16 recorded the starter package as it first shipped, with a tiny flat format, one valid fixture, and one skipped fixture. This feature preserves those fixtures and expands discovery to nested Markdown files so the teaching adapter can demonstrate collision handling. The traversal key is each path relative to the corpus root, rendered with POSIX separators. Ascending lexical order controls discovery, the selected collision path, and the collision path list. For duplicate filename stems, the first path is `used` and every path is reported.

This is a later extension, not a correction to spec 0005's original acceptance evidence. Once this spec is confirmed, spec 0005 receives a short later evolution note that links here and states the expanded teaching purpose.

The built in manifest lives at `tests/fixtures/adapter_conformance/jsmastery_specs/adapter-conformance.yml`. The starter manifest lives at `examples/starter-adapter/adapter-conformance.yml`. Each expected record and case corpus stays beneath its manifest directory.

### State transitions

A run moves through `command validation`, `manifest validation`, `adapter loading`, `contract checks`, `case checks`, and `reporting`. Command, manifest, and loading failures stop before cases. Within case checks, a failed prerequisite records one failure and omits only its dependent checks. Later independent cases continue.

Each temporary copy ends as `successful and removed` or `failed and preserved`. This is transient process state, not persisted application state.

### API surface

| Surface | Layer | Key inputs | Key outputs | Key errors |
|---|---|---|---|---|
| `load_conformance_manifest(path)` | infrastructure | manifest path | plain `ConformanceManifest` | read, safe YAML, schema, path, symlink, or expected record failure |
| `select_adapter(selector)` | infrastructure | built in id or third party selector | `SourceAdapter` or `LoadFailure` | selector, import, attribute, metadata, or method presence failure |
| `run_adapter_conformance(adapter, manifest, fixtures)` | application | `SourceAdapter`, plain manifest, fixture workspace port | `ConformanceOutcome` | failures are typed check results, not raised adapter exceptions |
| `ConformanceFixturePort` | application port | case, mutation request, preservation decision | isolated workspace, snapshots, optional artifact path | copy, mutation, snapshot, preserve, or cleanup failure |
| `test-adapter SELECTOR --cases PATH` | CLI | adapter selector and manifest path | deterministic human report | exits `1` and `2` as defined in AC-16 |

No authentication applies. This is a local developer command that executes already trusted adapter code.

`select_adapter` returns a new `JsmasteryAdapter` for the exact built in id. Every other value delegates unchanged to `load_adapter`. The existing private CLI selector helper is removed, and all three adapter commands call this public infrastructure function. Metadata property access inside loading catches `Exception` and returns a contract `LoadFailure`. CLI code alone maps a selector phase failure to exit `2`; every other load phase maps to exit `1`.

The fixture port has five operations:

| Operation | Input | Output | Rule on failure |
|---|---|---|---|
| `open_case` | case id and original corpus path | copied `Workspace` with baseline snapshot | `fixture.prepare` |
| `open_variant` | case id, original corpus, relative target, mutation kind | freshly copied and mutated `Workspace` with post mutation baseline | `fixture.prepare` |
| `snapshot` | workspace root | `CorpusSnapshot` | `fixture.snapshot` |
| `preserve` | failed workspace | absolute artifact path | `fixture.preserve` |
| `cleanup` | successful workspace | success | `fixture.cleanup` |

`open_variant` always starts from the original case corpus and applies exactly one suite mutation before taking its baseline. A snapshot sorts every entry by relative POSIX path and records its kind, permission bits, and full bytes for regular files. Modification time and access time are excluded. Comparing snapshots detects added, removed, replaced, permission changed, and content changed entries.

Normal and corruption workspaces call `discover` with the copied root. Every returned `DiscoveredSpec.corpus_root` must equal that root. Repeated operation checks use the same workspace and adapter instance. Fingerprint coverage is different by design: it remaps the baseline discovered source's root, corpus root, and contributing paths into a fresh probe workspace, then calls only `fingerprint`. It does not rediscover or parse the probe.

An adapter operation returning a wrong result type emits `contract.result_type` before any field access. An adapter operation raising `Exception` emits `adapter.exception` with its operation coordinate. A failed discovery omits discovery comparison and every source check for that case, then later cases run. A failed fingerprint omits only its consistency, coverage, and parse fingerprint comparison; parse still runs. A failed parse omits result comparison and parse determinism; fingerprint checks still run. Any failed contract signature check omits all case execution because the three method calls are a shared prerequisite.

A valid `DiscoveryResult` with nonnull `corpus_error` emits a failed `discovery.corpus_usable` check, then omits its source checks and continues to the next case. Conformance fixtures are declared usable corpora, so `corpus_error` is never an expected passing result.

Signature checking uses `inspect.signature` on each bound method. The first declared parameter must be positional only or positional or keyword and must accept the protocol value. A default on it is allowed. Every later positional or keyword only parameter must have a default, while `*args` and `**kwargs` are allowed. A required keyword only parameter fails. An `Exception`, including `TypeError` or `ValueError` from inspection, fails `contract.signature`. Annotations are ignored.

### Report contract

Rule ids are fixed vocabulary. Case, source, and path are separate coordinates and never become part of the rule id.

Coordinate names are `case`, `source`, `path`, `operation`, and `variant`, printed in that order when present. Adapter operations are `discover`, `fingerprint`, and `parse`. Fixture operations are `prepare`, `snapshot`, `preserve`, and `cleanup`. Variants are `original`, `fingerprint_probe`, `empty`, and `invalid_utf8`. Path coordinates are corpus relative POSIX paths.

| Rule id | Meaning |
|---|---|
| `manifest.load` | Manifest file reading and safe YAML loading |
| `manifest.schema` | Version, fields, types, categories, and required coverage are valid |
| `manifest.paths` | Every declared path exists, is contained, and is not a symlink |
| `adapter.load` | The existing loader returned one adapter instance |
| `contract.metadata` | Adapter identity and version are nonempty strings |
| `contract.signature` | The three bound methods have compatible call shapes |
| `contract.result_type` | Each method returns its exact contract type |
| `discovery.exact` | Sources, skips, and collisions equal the manifest expectation |
| `discovery.paths` | Discovered roots and contributing files meet containment invariants |
| `discovery.corpus_usable` | Absence of a corpus layout error in a declared usable case |
| `operation.deterministic` | Repeated discovery, parse, and fingerprint results are equal |
| `result.exact` | Record and result metadata equal the expectation |
| `result.confidence` | A malformed subject did not produce confident output |
| `fingerprint.consistency` | Direct, repeated, and parse fingerprints agree |
| `fingerprint.coverage` | Every contributing file changes the fingerprint |
| `fixture.prepare` | An isolated case or variant copy and baseline snapshot were created |
| `fixture.snapshot` | The post operation corpus snapshot was captured |
| `fixture.unchanged` | Adapter operations did not modify the copied corpus |
| `fixture.preserve` | A failed workspace was retained and named |
| `fixture.cleanup` | A successful workspace was removed |
| `corruption.empty` | Emptying one required file produced the required non confident behavior |
| `corruption.invalid_utf8` | Invalid UTF8 in one required file produced the required non confident behavior |
| `adapter.exception` | An adapter operation raised and therefore failed conformance |

The human line grammar is normative. This is an excerpt:

```text
adapter: starter-adapter 1
manifest: adapter-conformance.yml
PASS contract.signature operation=discover
PASS discovery.exact case=valid-example
FAIL result.exact case=valid-example source=DM-0001: unexpected field rationale_summary
artifact: /absolute/temporary/path
result: 2 passed, 1 failed
final: failed
```

Executed checks print one line each. A failure detail follows `: `. An artifact line follows the check that owns the path. After successful preservation, the first failed check owns it. If preservation or cleanup itself fails, that fixture check owns any last known root that still exists. No artifact line prints when no root survives. Fatal manifest and adapter failures print their rule id as the sole failed check. Dependent checks that cannot execute print nothing and do not enter totals. The final result is `passed` when failures are zero and `failed` otherwise. Paths other than artifact paths display relative to the manifest or case corpus as defined by the data model.

Before each case, the report prints `case: ID category=CATEGORY`. It adds `subject=PATH` when present and `target_fields=[FIELD,...]` for grammar drift cases. This makes target fields visible as coverage labels without claiming that an absent or skipped source emitted field specific violations.

### Check emission matrix

Each matrix row emits exactly one check for every scope unit shown when its prerequisite holds. Totals count only emitted pass and fail checks. `adapter.exception` replaces the logical operation check that raised, and dependent rows are omitted.

| Rule | Scope and coordinates | Prerequisite | Artifact behavior |
|---|---|---|---|
| `manifest.load` | once | command input parsed | none |
| `manifest.schema` | once | YAML loaded | none |
| `manifest.paths` | once | schema valid | none |
| `adapter.load` | once | manifest valid | none |
| `contract.metadata` | once | adapter selected | none |
| `contract.signature` | once per method, `operation` set | metadata valid | none |
| `fixture.prepare` | once per original or generated workspace, `case_id`, `variant`, and optional `path` set | signatures valid | preparation failure has no artifact unless a root exists |
| `contract.result_type` | once per workspace discovery, and once per source for fingerprint and parse, `operation` set | operation returned | failure requests preservation |
| `discovery.corpus_usable` | once per workspace that runs discovery | discovery returned the exact type | failure requests preservation |
| `discovery.exact` | once per original case | no corpus error | failure requests preservation |
| `discovery.paths` | once per workspace that returns sources | discovery returned sources | failure requests preservation |
| `operation.deterministic` | once for original discovery and once per original source for fingerprint and parse, `operation` set | both calls returned exact types | failure requests preservation |
| `result.exact` | once per discovered source | parse returned exact type | failure requests preservation |
| `result.confidence` | once per malformed case, `path` is its subject | discovery and any subject parse completed | failure requests preservation |
| `fingerprint.consistency` | once per discovered source | direct and parse fingerprints exist | failure requests preservation |
| `fingerprint.coverage` | once per contributing file probe, `path` set | baseline fingerprint exists and probe prepared | failure requests probe preservation |
| `corruption.empty` | once per required file, `path` and variant set | empty variant prepared and discovered | failure requests variant preservation |
| `corruption.invalid_utf8` | once per required file, `path` and variant set | invalid UTF8 variant prepared and discovered | failure requests variant preservation |
| `fixture.snapshot` | once after adapter operations in every prepared workspace | workspace exists | failure requests preservation |
| `fixture.unchanged` | once per workspace | final snapshot exists | failure requests preservation |
| `fixture.cleanup` | once per workspace with no prior failure | checks complete | failure does not call preservation; this check carries a surviving last known root |
| `fixture.preserve` | once per workspace that failed before cleanup | a workspace root exists | pass attaches the path to the first failed check; failure skips cleanup and this check carries a surviving last known root |
| `adapter.exception` | once for each operation that raises `Exception`, `operation` set | operation invoked | failure requests preservation and dependent checks are omitted |

Within a case, sources and paths follow manifest order. Corruption variants run in required file order, with `empty` before `invalid_utf8`. Fingerprint probes run in contributing file order. The first failed check by this order receives the single artifact path for its workspace after preservation succeeds.

### Value sourcing

| Action | Value produced or displayed | Source |
|---|---|---|
| Command parsing | selector | required CLI argument |
| Command parsing | manifest path | required `--cases` option |
| Manifest loading | schema version and case definitions | safe loaded YAML at the manifest path |
| Manifest loading | absolute case and expected record paths | relative manifest values resolved from the manifest directory |
| Adapter loading | adapter instance or load failure | public `select_adapter`, which owns the built in id and delegates third party values to `load_adapter` |
| Adapter reporting | identity and version | loaded adapter properties |
| Contract checking | compatible method shapes and exact result classes | accepted `SourceAdapter`, `DiscoveryResult`, and `AdaptationResult` declarations from spec 0005 |
| Expected record validation | validation context | attempted fields and unresolved count from its result expectation, existing paths from the case corpus, no known commits, Git unavailable |
| Workspace creation | copied corpus root and baseline | fixture port using the original case corpus and requested variant |
| Discovery comparison | expected sources, skips, and collisions | case discovery expectation |
| Discovery comparison | normalized actual paths | returned paths relative to the copied `DiscoveredSpec.corpus_root` |
| Result comparison | expected record | canonical record file parsed through the existing record reader |
| Result comparison | expected metadata | attempted fields, unresolved count, violation triples, and declared field_sources in the manifest |
| Confidence check | confident or non confident | record presence plus actual error severity violations from AC-7 |
| Corruption planning | affected sources | every source whose contributing files contain the required path |
| Corruption execution | empty and invalid UTF8 bytes | fixed suite constants named by AC-8 |
| Fingerprint comparison | remapped probe source | baseline discovered source paths made relative to the original copy, then joined to the fresh probe root |
| Fingerprint comparison | baseline and changed values | direct adapter calls before and after one contributing file probe |
| Fixture comparison | additions, deletions, content, type, and permission changes | baseline and post operation `CorpusSnapshot` values from the fixture port |
| Check reporting | stable rule id | fixed suite rule vocabulary plus case and source coordinates |
| Check reporting | pass or fail | actual value compared with its manifest expectation or protocol invariant |
| Case reporting | category, subject, and target field labels | case manifest fields |
| Artifact reporting | preserved absolute path, or a surviving root after a fixture operation failure | fixture workspace port after a failed case or variant |
| Final report | totals and exit code | ordered check results and AC-16 |

### Key invariants

1. Declarative expectations never execute author supplied assertion code.
2. The suite never guesses an adapter's grammar and never scores whether a mutation should be invalid.
3. The universal corruption list is closed at empty bytes and one fixed invalid UTF8 payload for required UTF8 text files.
4. Exact record comparison includes absent fields, so an invented field fails even when the record otherwise validates.
5. A warning only malformed result is confident output and fails.
6. An adapter exception is a conformance failure even when the suite contains and reports it.
7. All cases use copied corpora. Successful copies are removed. The suite attempts to preserve copies that fail before cleanup and reports fixture operation failures without making an intact artifact guarantee.
8. Built in and third party adapters use the same engine and loader boundary.
9. Execution and reporting are sequential. There is no retry, timeout, cache, or concurrency.
10. Report ordering and content are deterministic except for preserved operating system temporary paths.
11. A wrong return type fails before any result field is read.
12. `Exception` is contained. Process control values under `BaseException` are not contained.
13. Fingerprint coverage proves that every declared contributing file affects the digest. It does not prove that unrelated state is excluded.
14. A hung in process adapter produces no completed report. Process interruption is the only version one escape.

### Security model

Adapters remain trusted executable Python from spec 0005. They run in process with the caller's filesystem, environment, and process permissions. The suite is not a sandbox and cannot prove that an adapter avoided reads or writes outside the copied corpus.

The declarative manifest uses safe YAML loading and contains no Python assertion hooks. Strict path resolution rejects escape and recursively rejects symlinks in case corpora before adapter loading. The manifest and declared expected records must be regular non symlink files. Required corruption targets must also decode as UTF8 before any variant is created. Fixture snapshots detect changes inside the copied corpus. There is no authentication, authorization, regulated data, or secret scope.

### Critical test scenarios

1. Happy path: run `test-adapter` against the built in manifest and see every contract, fixture, and fingerprint check pass, verifies **AC-1**, **AC-4**, **AC-10** through **AC-16**, and **AC-20**.
2. Exact comparison: make an adapter invent `rationale_summary` while preserving the expected id and validity, then see the record comparison fail, verifies **AC-4**.
3. Grammar drift: run explicit wrong heading and missing required field cases, then reject any valid or warning only record, verifies **AC-6** and **AC-7**.
4. Universal corruption: empty and replace each required file with invalid UTF8 in separate copies, then verify every source sharing that file is non confident and all other sources remain exact, verifies **AC-8**.
5. Adapter exception: raise during invalid UTF8 parsing, report one failed operation, omit dependent checks, and continue the next case. Raise `KeyboardInterrupt` separately and confirm it escapes, verifies **AC-9**.
6. Fingerprint coverage: change each contributing file separately and require a changed fingerprint while direct and parse fingerprints agree, verifies **AC-12** and **AC-13**.
7. Fixture protection: make an adapter edit its copied source, fail the write check, preserve that copy, and leave the original fixture unchanged, verifies **AC-14** and **AC-17**.
8. Manifest boundary: exercise every strict schema, missing path, path escape, duplicate declared path, nested corpus symlink, non regular expected record, and invalid required UTF8 failure before adapter import, each exiting `1`, verifies **AC-2**, **AC-3**, and **AC-16**.
9. CLI boundary: exercise a malformed selector and missing CLI input as exit `2`, then an import failure and conformance failure as exit `1`, verifies **AC-1** and **AC-16**.
10. Starter collision: place valid decisions with the same filename stem in two nested directories, then confirm lexical selection and exact collision reporting, verifies **AC-19**.
11. Third party path: install the starter package and run its manifest through the real CLI, verifies **AC-18** through **AC-22**.
12. Corpus error: return a typed discovery result with `corpus_error`, fail its fixed rule, omit source checks, and continue the next case, verifies **AC-5** and **AC-9**.
13. Signature and type boundary: cover positional only, defaults, optional parameters, variadic parameters, required keyword only parameters, inspection failure, and every wrong result type, verifies **AC-9** through **AC-11**.
14. Fixture failures: fail preparation, snapshot, preservation, and cleanup separately, then confirm rule ids, continuation, artifact behavior, and exit `1`, verifies **AC-15** through **AC-18**.

## Build plan

The Skateboard approach starts with the smallest usable proof, one strict valid case through the public engine and CLI, then adds the failure properties that make the proof trustworthy.

1. - [x] Define the plain manifest and outcome objects, the fixture port, strict infrastructure parsing, semantic expected record loading, public `select_adapter`, one valid case comparison, the public application engine, and the `test-adapter` report, satisfies **AC-1** through **AC-5**, **AC-15**, **AC-16**, and **AC-18**.
2. - [x] Add runtime signature and exact result checks, path invariants, repeated operation comparison, and fingerprint property checks, satisfies **AC-9** through **AC-13**.
3. - [x] Add mandatory grammar categories, non confidence rules, isolated copied corpora, the closed corruption variants, write detection, failed copy preservation, and continued independent execution, satisfies **AC-6** through **AC-9**, **AC-14**, and **AC-17**.
4. - [x] Extend the starter adapter with recursive discovery and its lexical collision rule, add strict manifests for `jsmastery-specs` and the starter adapter, wire the fast and integration coverage, update the author guide, and run every quality gate, satisfies **AC-19** through **AC-22**.

## Consequences

**Positive**:

1. An invented canonical field fails even when ids, counts, and validation look correct.
2. Adapter authors get one report covering every reachable independent failure and the exact failed generated corpus needed to debug corruption behavior.
3. Built in adapters must satisfy the same public contract as installed third party adapters.
4. The suite stays inspectable because cases are data, not executable assertions.

**Negative and tradeoffs**:

1. Passing proves behavior only for declared cases and fixed protocol properties. It is not a proof for every possible source document.
2. Exact expected records require maintenance when the canonical schema or a deliberate mapping changes.
3. Required category coverage raises the cost of publishing a small adapter.
4. Failed copies consume operating system temporary space until a person or the operating system removes them.
5. Trusted adapter code can still hang or modify files outside the copied corpus. The suite adds no timeout or sandbox.
6. Version one covers UTF8 text sources only and has no JSON report.
7. Fingerprint coverage proves that declared contributing files are included. It does not detect extra unrelated inputs in the digest.
8. `target_fields` records the author's intended mapping coverage. When a malformed subject is absent or skipped, the suite verifies refusal to emit confident output but does not prove that the named field caused that refusal.

**Neutral**:

1. There is no data migration, feature flag, environment variable, or new package.
2. Existing `adapt` and `validate` behavior does not change.
3. Optional parameters and missing annotations remain compatible when the bound protocol call shape is correct.

## Follow-up

None.

## Rationale

Reasoning and options: see [rationale.md](rationale.md).
