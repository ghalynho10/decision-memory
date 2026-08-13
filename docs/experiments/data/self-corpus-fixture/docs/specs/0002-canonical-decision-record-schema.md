# 0002. Canonical decision record schema and validator

**Date**: 2026-08-07
**Status**: Accepted

## Summary

This decision fixes the shape of a canonical decision record and the rules that validate it. A canonical record is the single in memory format that adapters produce and later retrieval reads, so every field and every validation rule is pinned down here before anything builds on it. The record is defined with plain Python types in the domain layer, a pure validator checks the rules and returns clear reasons, and a command line command validates record files. All evidence checks use sets the caller supplies, so the domain stays free of filesystem and git access.

Two things this spec pins down beyond the field list, because both are load bearing and easy to leave implicit. First, reading a file and validating a record are separate steps with separate failure modes: a file that is not a parseable record produces no record at all, and those failures are reported in the same violation vocabulary as rule failures rather than as a second unrelated error path. Second, every rule carries a stable identifier, so tests and later consumers match on rule ids instead of on prose.

Feature 4 amended this contract without changing the chosen architecture. `ValidationContext` now also carries a count of unresolved path shaped mentions that an adapter dropped, and the validator reports that count as a warning. The application validation path now builds `existing_paths` by checking each cited target directly, including directories, rather than scanning the entire project root. The validator remains pure: callers still supply the resolved path set.

## Context

The project is a local tool that answers why a project is built the way it is, with cited answers backed by decision records. Its whole value depends on trustworthy records that carry resolvable evidence. A malformed record, a missing decision, or a claim with no backing source would flow straight into the retrieval and answer stages and quietly undermine every citation.

The tool ingests decision shaped files from real projects. Feature 4 will design an adapter that reads a project's spec files and produces canonical records. Feature 5 will parse and embed those records for retrieval. Both features need one agreed record shape and one set of enforced rules to build against. Without that agreement, each feature invents its own shape, and bad records reach the pipeline silently because nothing checks them.

`AGENTS.md` fixes the architecture constraints this decision must respect. The domain layer has zero external imports, and no framework code such as Pydantic or Typer is allowed in domain or application. Pydantic is already a dependency in the stack, so it is available where it is allowed, which is infrastructure. The scope row for feature 4 also carries a degradation policy: when an adapter cannot fully populate a record, the gap must be flagged, never silently dropped, and never fabricated.

One stack gap surfaced while pinning this down. The record format is YAML frontmatter plus a markdown body, but the project has no YAML parser: `pyproject.toml` lists only `pydantic` and `typer`. Pydantic validates already parsed Python objects, it does not read YAML. Reading a record file therefore needs a real YAML library, and this decision adds one (see `## Configuration required`).

The cost of not deciding is deferred rework. Every later slice depends on this shape, and changing it after the adapter and the retrieval pipeline exist means changing all of them at once.

## Requirements

**User stories**:
- As an adapter developer, I want one validated record shape so that the records I produce are checked before they enter the pipeline.
- As a user, I want to validate a record file from the command line so that I get clear reasons when a record is wrong.
- As a maintainer, I want warnings for degraded fields so that gaps stay visible without blocking ingestion.

**Acceptance criteria** (the contract, each criterion is IDed and independently checkable):
- **AC-1**: A well formed record passes validation with no violations.
- **AC-2**: A record missing any of `id`, `title`, `status`, `decision.chosen`, or `evidence` is rejected with a `required.missing` error naming the missing field.
- **AC-3**: Evidence is checked per kind. A `spec` or `file` target that is not in the supplied existing paths produces an `evidence.path_unresolved` error naming the entry; a `commit` target not in the supplied known commits produces `evidence.commit_unresolved`.
- **AC-4**: A record with neither `why` nor `rationale_summary` populated is rejected with a `rationale.missing` error.
- **AC-5**: A field the adapter attempted and failed to populate produces a warning, and the record is not rejected for it.
- **AC-6**: An alternative without a rejection reason produces a warning, not an error.
- **AC-7**: A field outside the schema produces a warning naming the field.
- **AC-8**: The `validate` command reads a record file, prints each violation with its severity, rule id, field, and reason, and exits with the code fixed in `## Feature design` for that outcome.
- **AC-9**: An empty markdown body produces no violation.
- **AC-10**: A file that is not a parseable record (no frontmatter fence, invalid YAML, or frontmatter that is not a mapping) yields no record, reports the matching `file.*` error, and exits `3`. No rule violations are reported alongside it, because there is no record to check.
- **AC-11**: A required string field present but empty or whitespace only is treated as missing and produces the same `required.missing` error as an absent field. A required list present but empty is likewise missing.
- **AC-12**: An evidence target that is empty produces `evidence.empty_target`; one that is absolute, contains a `..` segment, or ends in a slash produces `evidence.target_not_normalized`. Neither is reported as unresolved, because the target is rejected before resolution is attempted.
- **AC-13**: When git history is unavailable (the project root is not a repository, or git cannot be run), a single `context.git_unavailable` warning is reported, `commit` evidence resolution is skipped, and no `evidence.commit_unresolved` errors are produced.
- **AC-14**: A `commit` target of 7 to 40 hexadecimal characters resolves when it is a unique prefix of exactly one known commit. A prefix matching more than one produces `evidence.commit_ambiguous`.
- **AC-15**: A record whose `supersedes` equals its own `id` produces a `supersedes.self_reference` error.
- **AC-16**: A record with warnings but no errors exits `0`. A malformed `id` or `date` produces an error naming the field.
- **AC-17**: A validation context whose `unresolved_mention_count` is greater than zero produces an `evidence.mentions_unresolved` warning on `evidence`. The warning never changes the exit code by itself.

## Options considered

### Option 1: Plain domain types with a hand written validator, Pydantic only in infrastructure

The canonical record is a plain dataclass in the domain layer with no imports beyond the standard library. A pure validator function checks the rules and returns a list of violations. In infrastructure, a YAML library reads the frontmatter into a mapping and a Pydantic model validates that mapping, converts it into the domain record, and collects any unknown fields it sees.

**Pros**:
- Honors the zero external imports rule in `AGENTS.md` exactly
- The domain stays testable without any framework
- Pydantic still does the shape checking work where it is allowed, and gives type errors for free

**Cons**:
- More hand written code than letting Pydantic own the whole model
- No automatic serialization from the domain objects
- Two representations of the same shape, the dataclass and the Pydantic model, that must stay aligned

### Option 2: Pydantic models as the canonical record in the domain layer

The canonical record is a Pydantic v2 model used directly as the domain type, with its validators enforcing the rules.

**Pros**:
- Less code, schema and validation in one place
- Automatic parsing, serialization, and typed fields

**Cons**:
- Violates the zero external imports rule in `AGENTS.md`, so that rule must be relaxed
- Couples the core domain type to a framework

### Option 3: Fully hand written, no Pydantic and no YAML library

The parser that reads YAML frontmatter and markdown body is also hand written, using the standard library only, which avoids adding a YAML dependency.

**Pros**:
- Zero framework dependence anywhere, one mental model
- No new dependency

**Cons**:
- Hand rolling YAML is error prone well before it is useful; even the subset real records need covers nested mappings, lists, quoting, and multiline strings
- More code to maintain, and the bugs land in the one place the whole pipeline trusts

## Decision

**Chosen option**: Option 1: Plain domain types with a hand written validator, Pydantic only in infrastructure

The canonical record lives in the domain layer as a plain dataclass, the validator is a pure function that returns a list of violations with severities and clear reasons, and a Pydantic model in infrastructure handles parsing and reports unknown fields.

## Rationale

`AGENTS.md` is explicit that the domain layer carries zero external imports and that Pydantic is not allowed there. Option 1 is the only choice that honors that rule while still using the Pydantic the stack already depends on for the shape checking work, which is exactly the layer where it belongs. Option 2 would mean rewriting a curated project rule for a small amount of convenience. Option 3 avoids one dependency by hand rolling YAML, which is the wrong trade in the one component the entire pipeline's trustworthiness rests on.

The record shape is the contract every later feature builds on, so keeping it plain and pure makes it testable without infrastructure and stable as a target. The degradation policy from the scope row drives the warning rules: attempted fields, a missing rejection reason on an alternative, and unknown fields all warn rather than reject, so gaps stay visible without blocking a record that is otherwise usable.

Three of the rules here exist specifically to stop a wrong reason from being reported, which matters more than usual for a tool whose output is citations. `context.git_unavailable` exists so a missing repository does not present as a list of missing commits. `evidence.empty_target` exists so an empty target does not present as an unresolved path. Splitting parse failures from rule failures exists so an unparseable file does not present as a record that happens to be missing every required field. Each is a case where the naive implementation produces an answer that is technically a failure report and practically a misdirection.

## Feature design

**Data model sketch**:

`CanonicalDecisionRecord` (plain domain dataclass, no external imports)

| Field | Type | Rule |
|---|---|---|
| `id` | str | required, matches `^[A-Za-z0-9][A-Za-z0-9._-]*$` |
| `title` | str | required |
| `status` | str | required, one of `proposed`, `accepted`, `superseded`, `rejected` |
| `date` | str | optional, `YYYY-MM-DD`, must be a real calendar date |
| `body` | str | optional, markdown body, empty allowed |
| `context.problem` | str | optional |
| `context.triggering_change` | str | optional |
| `decision.chosen` | str | required |
| `decision.alternatives` | list of `Alternative` | optional, each has a required `title` and a recommended `rejection_reason` |
| `why` | list of str | optional, at least one of `why` or `rationale_summary` |
| `rationale_summary` | str | optional, at least one of `why` or `rationale_summary` |
| `consequences.positive` | list of str | optional |
| `consequences.negative` | list of str | optional |
| `evidence` | list of `Evidence` | required, non empty |
| `tags` | list of str | optional |
| `supersedes` | str | optional, one record id, must not equal this record's `id` |

`Evidence`: `kind` (enum `spec` | `file` | `commit`, required), `target` (str, required), `note` (str, optional).

`Alternative`: `title` (str, required), `rejection_reason` (str, recommended).

`ValidationContext` (passed in, keeps the validator pure):
- `attempted_fields`: set of str, fields the adapter tried but could not fill
- `unknown_fields`: set of str, fields the parser saw that are not in the schema
- `existing_paths`: set of str, normalized project relative paths that resolved, used for `spec` and `file` evidence. The caller may produce it by scanning the project root or by checking cited targets directly.
- `known_commits`: set of str, full 40 character commit hashes in git history, used for `commit` evidence
- `git_available`: bool, false when the project root is not a repository or git could not be run
- `unresolved_mention_count`: int, the number of path shaped code mentions an adapter saw and dropped because they did not resolve

`Violation`: `field` (str), `severity` (error or warning), `rule` (str, a rule id from the table below), `reason` (str).

`superseded_by` is deliberately **not** a field on the record. It is derived by scanning `supersedes` across a whole corpus, which needs the corpus, so it belongs to the retrieval slices (see `## Follow-up`). Nothing in this slice stores or computes it.

**What counts as missing**: one rule, applied everywhere, so `required` needs no per field elaboration. A required string field is missing when it is absent, empty, or whitespace only. A required list field is missing when it is absent or empty. Optional fields follow the same test to decide whether they are populated, which is what `## Key invariants` means by "populated" for the `why` and `rationale_summary` pair.

**Field naming in violations**: `Violation.field` uses dotted paths with zero based indices for list members, for example `decision.alternatives[1].rejection_reason` or `evidence[2].target`. `unknown_fields` uses the same convention, so a stray key inside the second evidence entry arrives as `evidence[1].foo`. The whole record is named by the empty string, used by rules that are not about one field.

**Uniqueness of `id`** is not checked here and is not checkable here: the validator sees one record and `ValidationContext` carries no corpus of ids. Collision detection belongs to ingestion, in feature 5, where the whole corpus is in hand. This slice only enforces the id format.

**Record file grammar**:

A record file is UTF-8 text, with or without a byte order mark, and with either line ending. It opens with a frontmatter fence, a line containing exactly `---`, followed by YAML, followed by a closing line containing exactly `---`. Everything after the closing fence is the markdown body, verbatim, with one leading blank line stripped if present. The frontmatter must parse to a YAML mapping. Duplicate keys resolve last wins, matching the YAML library's behavior, and are not detected in this slice (see `## Follow-up`).

**Evidence target normalization**:

Targets for `spec` and `file` kinds are project root relative POSIX paths. A target is rejected before any resolution attempt when it is empty or whitespace only (`evidence.empty_target`), or when it is absolute, contains a `..` segment, or ends in a slash (`evidence.target_not_normalized`). Otherwise it is normalized by stripping a leading `./` and collapsing repeated slashes, then compared against `existing_paths` by exact, case sensitive string match. The producer of `existing_paths` normalizes the same way. Case sensitivity is deliberate even though macOS filesystems are usually case insensitive: a record whose target casing differs from the file on disk is a record that will break on a case sensitive machine, and this catches it at validation time rather than in CI.

The shipped application path checks each cited target directly and puts only the resolving targets into `existing_paths`, rather than scanning the whole project root. Files and directories both resolve. This preserves the domain contract while keeping path discovery bounded to what the record actually cites.

A `spec` target must additionally resolve under `docs/specs/`; one that resolves elsewhere produces `evidence.spec_outside_specs_dir`. This is the only thing distinguishing `spec` from `file`, and it exists so the kind carries validation weight rather than being decorative metadata.

`commit` targets are 7 to 40 hexadecimal characters. Resolution is unique prefix match against `known_commits`: no match is `evidence.commit_unresolved`, more than one match is `evidence.commit_ambiguous`. When `git_available` is false, commit resolution is skipped entirely and a single `context.git_unavailable` warning stands in for it, so a missing repository never masquerades as a set of missing commits.

**Rule ids** (stable, matched on by tests and later consumers; the `file.*` and `field.*` rules fire during parsing and produce no record, the rest fire during validation):

| Rule id | Severity | Fires when |
|---|---|---|
| `file.unreadable` | error | the path does not exist, is not a file, or cannot be read as UTF-8 |
| `file.no_frontmatter` | error | no opening or closing `---` fence |
| `file.frontmatter_unparseable` | error | the frontmatter is not valid YAML |
| `file.frontmatter_not_mapping` | error | the frontmatter parses to something other than a mapping |
| `field.wrong_type` | error | a value's type does not match the schema, for example `evidence` given as a string |
| `field.bad_enum` | error | a value outside an enumerated set, for `status` or `evidence[].kind` |
| `required.missing` | error | a required field is missing, per **What counts as missing** |
| `id.malformed` | error | `id` does not match the required pattern |
| `date.malformed` | error | `date` is not a real `YYYY-MM-DD` calendar date |
| `rationale.missing` | error | neither `why` nor `rationale_summary` is populated |
| `evidence.empty_target` | error | an evidence `target` is empty or whitespace only |
| `evidence.target_not_normalized` | error | a path target is absolute, has a `..` segment, or ends in a slash |
| `evidence.path_unresolved` | error | a `spec` or `file` target is not in `existing_paths` |
| `evidence.spec_outside_specs_dir` | error | a `spec` target does not resolve under `docs/specs/` |
| `evidence.commit_unresolved` | error | a `commit` target prefix matches no known commit |
| `evidence.commit_ambiguous` | error | a `commit` target prefix matches more than one known commit |
| `supersedes.self_reference` | error | `supersedes` equals this record's `id` |
| `field.attempted_unfilled` | warning | a field is in `attempted_fields` |
| `alternative.missing_rejection_reason` | warning | an alternative has no `rejection_reason` |
| `field.unknown` | warning | a field is in `unknown_fields` |
| `evidence.mentions_unresolved` | warning | `unresolved_mention_count` is greater than zero |
| `context.git_unavailable` | warning | `git_available` is false and the record has `commit` evidence |

**Parse result**:

Reading a file and validating a record are separate steps, because a file can fail before a record exists. `parse_record_file(path)` returns a `ParseResult`: `record` (`CanonicalDecisionRecord` or `None`), `violations` (list of `Violation`, the `file.*` and `field.*` rules), and `unknown_fields` (set of str). When `record` is `None`, no rule validation runs, because there is nothing to validate; the CLI reports the parse violations and stops. When `record` is present, `unknown_fields` is carried into `ValidationContext` and the validator runs. This keeps parse failures and rule failures in one reporting vocabulary while keeping them distinct outcomes with distinct exit codes.

**State transitions**: none enforced in this slice. `status` is an enumerated value checked against the allowed set; no transition rules between states.

**API surface**:

| Surface | Kind | Key inputs | Key outputs | Auth | Key errors |
|---|---|---|---|---|---|
| `validate(record, context)` | pure function | `record`: CanonicalDecisionRecord, `context`: ValidationContext | list of `Violation` | none | none, it reports violations rather than raising |
| `parse_record_file(path)` | infrastructure function | record file path | `ParseResult` | none | none, parse failures come back as violations with no record |
| `decision-memory validate <file> [--project-root PATH]` | CLI command | record file path, optional project root | printed violations, exit code | none | see the exit code table |

**Exit codes** (fixed here so scripts can rely on them, and chosen not to collide with Click's own):

| Code | Meaning |
|---|---|
| `0` | no error violations; warnings may be present and are still printed |
| `1` | the file parsed into a record and validation found at least one error |
| `2` | usage error, reserved by Click, not produced by this command directly |
| `3` | the file could not be read or parsed, so no record exists to validate |

Warnings never affect the exit code in this slice. A `--strict` flag that promotes warnings to errors is a plausible later addition and is listed in `## Follow-up`, not built here.

**Project root resolution**: `--project-root` when given. Otherwise the nearest ancestor of the record file that contains a `.git` directory. Otherwise the record file's parent directory, with `git_available` false. The root anchors both `existing_paths` and the `docs/specs/` prefix check, so a wrong root would invalidate every path check at once; resolving it from the record file rather than the current working directory keeps the result the same wherever the command is run from.

**Value sourcing** (every value each action produces, computes, or displays names where it comes from):

| Action | Value produced / displayed | Source |
|---|---|---|
| `validate` | violation list | the record fields, `attempted_fields`, `unknown_fields`, `existing_paths`, `known_commits`, `git_available` |
| `validate` | violation field | the record field path, or the attempted or unknown set entry |
| `validate` | violation rule | the rule id from the rule table that fired |
| `validate` | violation severity | fixed per rule id in the rule table |
| `validate` | violation reason | derived from the rule and the field |
| `parse_record_file` | record or none | the file's frontmatter mapping, converted by the Pydantic model |
| `parse_record_file` | parse violations | the file grammar and Pydantic type checks |
| `parse_record_file` | `unknown_fields` | frontmatter keys the Pydantic model does not declare |
| CLI `validate` | printed lines | the parse violations, then the validation violations |
| CLI `validate` | exit code | the exit code table: `3` when no record, else `1` when any error, else `0` |
| CLI `validate` | project root | `--project-root`, else nearest `.git` ancestor, else the record file's parent |
| CLI `validate` | `existing_paths` | each `spec` or `file` target the record cites, normalized and checked directly under the project root |
| CLI `validate` | `known_commits` | application queries git history for full hashes, empty when git is unavailable |
| CLI `validate` | `git_available` | whether the project root is a repository and git ran successfully |
| CLI `validate` | `attempted_fields` | empty in this slice; nothing in the CLI path knows what a source offered, feature 4's adapter fills it |
| adapter validation | `unresolved_mention_count` | the adapter's count of dropped path shaped mentions, defaulting to zero when no adapter supplied one |

**Key invariants**:
- The validator is pure: it performs no filesystem or git access, all existence checks use the supplied sets.
- A record missing any of `id`, `title`, `status`, `decision.chosen`, or `evidence` is invalid, where missing follows the single rule in **What counts as missing**.
- At least one of `why` or `rationale_summary` is populated.
- Evidence targets are normalized and rejected for shape before any resolution is attempted.
- Evidence targets resolve per kind against the supplied sets; commit resolution is skipped entirely when git is unavailable.
- `attempted_fields` and `unknown_fields` never reject, they only warn.
- `unresolved_mention_count` never rejects, it only warns.
- An empty markdown body is allowed.
- `supersedes` holds at most one record id and never this record's own id.
- Every violation carries a rule id from the rule table, and each rule id has one fixed severity.
- A file that does not parse yields no record and no rule violations, only the parse violation that explains why.
- Warnings never change the exit code.

**Security model**: none. This is a local command line tool with no users, no tenants, and no regulated data. Validation reads local files only. Two notes on reading untrusted input anyway, since records come from other people's repositories: YAML is loaded with the safe loader, never the full one, so a record file cannot construct arbitrary Python objects; and evidence path targets are rejected when absolute or containing `..`, so a record cannot direct a path check outside the project root.

**Configuration required**: one new runtime dependency, `pyyaml`, plus `types-PyYAML` in the dev group so mypy stays strict and clean. Pydantic validates the parsed mapping but cannot read YAML itself, and the project had no YAML parser before this decision. `pyyaml` is chosen over `ruamel.yaml` for being the ecosystem default and sufficient here; the one thing it gives up is duplicate key detection, which is why duplicate keys are last wins and unvalidated in this slice. No environment variables and no configuration files are added.

**Critical test scenarios** (each maps to an acceptance criterion in `## Requirements`):
- Happy path: a well formed record file passes the CLI `validate` with no violations and exit code `0`, verifies **AC-1**, **AC-8**
- Failure case: a record missing `decision.chosen` is rejected with `required.missing` naming the field, verifies **AC-2**
- Failure case: an evidence entry with a `file` target that is not an existing path produces `evidence.path_unresolved` naming the entry as `evidence[n].target`, verifies **AC-3**
- Failure case: a record with neither `why` nor `rationale_summary` is rejected, verifies **AC-4**
- Edge case: a field named in `attempted_fields` warns but does not reject, verifies **AC-5**
- Edge case: an alternative without a rejection reason warns, verifies **AC-6**
- Edge case: an unknown field warns, including one nested inside an evidence entry, verifies **AC-7**
- Edge case: an empty markdown body produces no violation, verifies **AC-9**
- Failure case: a file with no frontmatter fence, a file with invalid YAML, and a file whose frontmatter is a list rather than a mapping each produce their `file.*` error, no record, no rule violations, and exit `3`, verifies **AC-10**
- Edge case: `title: ""`, `title: "   "`, and an absent `title` all produce the same `required.missing` error; `evidence: []` likewise, verifies **AC-11**
- Failure case: evidence targets `""`, `/etc/passwd`, `../outside.md`, and `docs/` produce `evidence.empty_target` or `evidence.target_not_normalized`, and never `evidence.path_unresolved`, verifies **AC-12**
- Edge case: validating a record under a project root with no repository yields exactly one `context.git_unavailable` warning and no commit errors, even with several `commit` entries, verifies **AC-13**
- Edge case: a 7 character commit prefix matching one known commit resolves; a prefix matching two produces `evidence.commit_ambiguous`, verifies **AC-14**
- Failure case: a record whose `supersedes` equals its own `id` produces `supersedes.self_reference`, verifies **AC-15**
- Edge case: a record with only warnings exits `0`; `id` of `"-bad id"` and `date` of `2026-02-30` each error naming the field, verifies **AC-16**
- Edge case: `unresolved_mention_count` of `4` produces `evidence.mentions_unresolved` as a warning and does not change the exit code, verifies **AC-17**
- Edge case: `validate` on a record citing a directory target resolves it by checking the cited target directly, and completes without scanning the whole project root
- Edge case: `evidence` given as a string rather than a list produces `field.wrong_type` at parse time with no record, and `status: draft` produces `field.bad_enum`
- Edge case: a record file with a byte order mark and CRLF line endings parses identically to the plain UTF-8 LF version

## Build plan

Ordered for the Skateboard approach: the thinnest usable whole first, a person validating a real record file end to end, then each slice thickens the rule set.

1. Add `pyyaml` and `types-PyYAML`, then build the file reader: the frontmatter grammar, the Pydantic model over the parsed mapping, `ParseResult`, and the `file.*` and `field.*` rules, satisfies **AC-10**
2. Build the domain model, the `Violation` and `ValidationContext` types, the missing field rule, the why or rationale pair, the `id` and `date` format rules, self supersession, and the CLI `validate` command that prints violations and sets the exit code, satisfies **AC-1**, **AC-2**, **AC-4**, **AC-8**, **AC-9**, **AC-11**, **AC-15**, **AC-16**
3. Add the warning rules: attempted fields, alternatives missing a rejection reason, unknown fields, and unresolved mention counts, satisfies **AC-5**, **AC-6**, **AC-7**, **AC-17**
4. Add evidence target normalization and shape rejection, then resolution per kind against the supplied sets, satisfies **AC-3**, **AC-12**, **AC-14**
5. Add the application glue: project root resolution, direct cited path checks, the git history query, and the git unavailable path, satisfies **AC-13**
6. Complete the test suite covering every rule id and the happy path, and run ruff and mypy clean, satisfies **AC-1** through **AC-17**

Step 1 comes first because nothing else can be exercised end to end until a file can be read, and because it is where the new dependency lands. Steps 2 through 5 each keep the CLI working, so the thin whole is usable from step 2 onward and thickens from there.

## Consequences

**Positive**:
- Adapting and later retrieval get one agreed, validated record shape to build against
- Malformed records fail loudly with clear reasons instead of flowing silently into the pipeline
- Degraded fields stay visible as warnings without blocking ingestion
- A pure validator is easy to unit test without infrastructure
- Stable rule ids and fixed exit codes make the command scriptable and the tests resistant to wording changes

**Negative / tradeoffs**:
- More hand written code than letting Pydantic own the whole model, and two representations of the shape to keep aligned
- Callers must gather resolved paths, known commits, and git availability before validating, so validation is not a one argument call
- The schema and feature 4's adapter must stay in lockstep, since the adapter produces these records
- Adds a runtime dependency, `pyyaml`, that the stack did not have
- Case sensitive path comparison will reject targets that resolve fine on a developer's macOS filesystem; that is the intent, but it will read as a false positive the first time it happens
- The rule id table is now part of the contract, so adding or renaming a rule is a spec change, not just a code change

**Neutral**:
- Introduces the first domain model and establishes the pattern later slices build on
- The derived `superseded_by` link is deferred to the retrieval slices
- Direct cited path checks keep the application path bounded to what the record cites; a caller may still provide a precomputed path set when it already has one

## Follow-up

- [ ] Implement `superseded_by` derivation, scanning `supersedes` across records, in the retrieval slices (features 5 and 6), not here
- [ ] Enforce `id` uniqueness and `supersedes` target existence at ingestion in feature 5, where the whole corpus is in hand; neither is checkable against a single record
- [ ] Keep future adapters aligned to this schema; their degradation policy fills `attempted_fields` and may fill `unresolved_mention_count`
- [ ] Consider whether the `validate` command should accept multiple files or a directory in a later slice
- [ ] Consider a `--strict` flag that promotes warnings to errors, once there is a real corpus to know whether it would be usable
- [ ] Duplicate frontmatter keys resolve last wins and go undetected; revisit if real records hit it, which would mean moving to `ruamel.yaml`
- [ ] Update `AGENTS.md` and spec 0001's dependency list to include `pyyaml` when this is implemented

## References

**Project sources** (verifiable, in this repo):
- `AGENTS.md`: Clean Architecture rules, zero external imports in the domain layer
- `docs/specs/0001-stack-and-architecture.md`: the stack decision, Pydantic as a dependency
- `docs/specs/0003-jsmastery-specs-adapter/index.md`: the shipped validation path amendment, direct cited path checks, and `evidence.mentions_unresolved`
- `docs/scope/scope.md`: feature 3 row and feature 4 degradation policy

**Practices & standards**:
- Pure functions with injected dependencies for testability
