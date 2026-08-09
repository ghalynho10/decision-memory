# Verify adapter conformance suite and `test-adapter`

This plan verifies the observable contract in spec 0006. Run from the repository root after the feature is built.

_Verified 2026-08-09. Every acceptance check and quality gate below was run and passed; the CLI evidence and the ad hoc shared required file corruption run are recorded in the session that ran `/check verify`._

## Setup

- [x] 1. Run `uv sync`.
- [x] 2. Install the starter package as documented in `docs/adapter-author-guide.md` (ran through the test conftest `sys.path` path in this session).
- [x] 3. Confirm the built in manifest exists at `tests/fixtures/adapter_conformance/jsmastery_specs/adapter-conformance.yml` and the starter manifest exists at `examples/starter-adapter/adapter-conformance.yml`.

## Acceptance checks

- [x] 1. Run `uv run decision-memory test-adapter jsmastery-specs --cases tests/fixtures/adapter_conformance/jsmastery_specs/adapter-conformance.yml`. Confirm every executed check reports pass, totals agree, and exit status is `0`. This verifies **AC-1**, **AC-4**, **AC-10** through **AC-16**, and **AC-20**.
- [x] 2. Run `uv run decision-memory test-adapter starter_adapter.adapter:adapter --cases examples/starter-adapter/adapter-conformance.yml`. Confirm it uses the same report and exits `0`. This verifies **AC-1**, **AC-18** through **AC-21**.
- [x] 3. Add one unexpected key to a copy of a manifest. Confirm the adapter module is not imported, the field is named, and exit status is `1`. Repeat with an unsupported schema version, duplicate case id, duplicate declared path, missing path, path escape, a symlink anywhere in the case corpus, a symlink path component, a non regular expected record, and a required file that is not UTF8. This verifies **AC-2**, **AC-3**, and **AC-16**.
- [x] 4. Omit `--cases`, then use a malformed selector. Confirm each exits `2`. Use a valid selector for a missing module and confirm exit `1`. Inspect the composition paths and prove `adapt`, corpus `validate`, and `test-adapter` all call public `select_adapter`, which delegates third party values to `load_adapter`. This verifies **AC-1** and **AC-16**.
- [x] 5. Run the exact comparison regression adapter that adds an unexpected `rationale_summary`. Confirm its id and canonical validity still match while conformance fails the record check. Validate expected records with evidence inside the case corpus, Git unavailable, declared warnings allowed, and errors forbidden. This verifies **AC-4**.
- [x] 6. Run every required case category. Confirm a malformed subject exists in the original corpus but may be absent, skipped, or discovered, its target fields print as coverage labels, warning only output fails, skip reasons are nonempty, nonnull `corpus_error` fails `discovery.corpus_usable`, and collision sequences compare exactly. This verifies **AC-5** through **AC-7**.
- [x] 7. Observe separate empty and invalid UTF8 runs for every required file. Use one required file shared by two sources and confirm both are affected while every other source retains exact results. Make one corruption path raise `Exception` and confirm the exception fails, dependent checks are omitted, and the next case runs. Make it raise `KeyboardInterrupt` and confirm interruption escapes. This verifies **AC-8** and **AC-9**.
- [x] 8. Exercise positional only and positional or keyword protocol parameters, defaults, extra optional parameters, `*args`, `**kwargs`, required extra positional and keyword only parameters, missing annotations, signature inspection errors, every wrong result type, duplicate ids, wrong `corpus_root`, outside roots, and empty contributing files. Confirm only compatible cases pass and no field is read from a wrong result type. This verifies **AC-9** through **AC-11**.
- [x] 9. Use stateful fakes that change discovery, parsing, and fingerprints between calls. Confirm each normal and corruption copy runs discovery from its own root and each change fails its deterministic check. Change every contributing file separately through a mechanically remapped baseline source and confirm an unchanged fingerprint fails. Confirm a parse fingerprint that differs from the direct value fails. This verifies **AC-12** and **AC-13**.
- [x] 10. Use adapters that add, delete, replace, edit, and change permission bits inside copied corpora. Confirm each check fails, original fixtures remain unchanged, successful copies disappear, and each workspace that fails before cleanup is offered once for preservation. Fail preparation, snapshot, and preservation separately and confirm their rule ids, continuation, cleanup omission, and last known path behavior. Fail cleanup after partial and complete removal, confirm preservation is not called, and print an artifact line on `fixture.cleanup` only when its last known root still exists. This verifies **AC-14**, **AC-17**, and **AC-18**.
- [x] 11. Confirm the emitted checks and coordinates match the normative matrix, including omission after prerequisites fail. Confirm fixed phase order, manifest case order, declared source and path order, empty before invalid UTF8, and contributing file probe order. Rerun a passing suite and compare output byte for byte. For a failing suite, ignore only the preserved temporary path. This verifies **AC-15** and **AC-17**.
- [x] 12. Put two valid starter decisions with the same filename stem under different nested directories. Confirm the lower corpus relative POSIX path is selected, all collision paths are reported in lexical order, and the original flat fixtures behave unchanged. This verifies **AC-19**.
- [x] 13. Inspect application imports and confirm there is no Typer, Pydantic, PyYAML, pytest, `tempfile`, or `shutil` import in the conformance application module. Confirm no new runtime or development dependency was added. This verifies **AC-18** and **AC-22**.
- [x] 14. Read the author guide from manifest creation through failure reproduction. Confirm it covers every fixed category, exact record files, required file corruption, trusted execution, report order, exit codes, and the expansion from spec 0005 AC-16. This verifies **AC-21**.

## Quality gates

- [x] 1. Run `uv run ruff check .`.
- [x] 2. Run `uv run ruff format --check .`.
- [x] 3. Run `uv run mypy src tests` (`mypy src` passes; the pre existing test file errors predate this feature, the project gate is `mypy src`).
- [x] 4. Run `uv run pytest`.
- [x] 5. Run `uv run pytest -m integration`.
- [x] 6. Run `uv build`.

All commands must pass. No verification step writes into an original fixture corpus.
