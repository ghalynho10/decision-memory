# Verify: jsmastery specs adapter · spec 0003 · updated 2026-08-08

_Steps derived from spec 0003 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## Commands

Run from the decision-memory repo, with a corpus holding real specs. The real validation corpus is `github.com/ghalynho10/job_pilot`; a fresh clone is a good target.

- [x] `uv run decision-memory adapt <corpus> --dry-run` → prints the full report, writes no record file and no manifest, and the output directory is not created on a first run → AC-1, AC-17
- [x] `uv run decision-memory adapt <corpus>` → writes one record per adaptable spec directory plus `manifest.json`, and exits 0 → AC-1, AC-14, AC-21, AC-25
- [x] run `adapt` again with no source changes → every record reports `unchanged` and nothing is rewritten → AC-15
- [x] edit one spec's `rationale.md`, run `adapt` again → exactly that record reports `rewritten`, the rest stay `unchanged` → AC-13, AC-15
- [x] `uv run decision-memory adapt /tmp/job_pilot` against the real corpus → 15 records written, every record validates, exit 0 → AC-1 through AC-25 on real data
- [x] `uv run decision-memory validate <record> --project-root <corpus>` → prints `valid record, no violations` and exits 0 → AC-22
- [x] `uv run pytest`, `uv run mypy src`, `uv run ruff check src tests` → all pass → build plan task 8

## Manual

- [x] a spec directory with no leading digits in its name is skipped with that reason, and the run continues → AC-2, AC-20
- [x] a directory with no `index.md` is reported as not a spec and does not fail the run → AC-1, AC-20
- [x] a spec whose `index.md` has no `## Decision` section is skipped with that reason → AC-20
- [x] a spec whose `**Status**` value is unmapped (for example `Draft`) is skipped with that reason → AC-7
- [x] a panel spec such as 0012 carries the panel question prefix on every alternative, and Panel 3, whose decision names Option B first, resolves to Option B with Option A listed as the alternative → AC-9, AC-10
- [x] a non panel spec whose chosen line drops the ordinal resolves its winner by title match → AC-9
- [x] a code path token whose casing differs from the entry on disk does not resolve and is counted as a dropped mention → AC-5, AC-6, AC-23
- [x] a spec whose `rationale.md` has no `## Rationale` section produces a record that fails validation, is not written, and is reported with its violations → AC-16, AC-21
- [x] a record the adapter writes parses back to an equal record, and its filename is the record id plus `.md` → AC-24
- [x] a corpus path with no `docs/specs/` directory exits 3 → AC-21
- [x] `--output <dir>` writes elsewhere, and the records still validate with the corpus as project root → AC-18
- [x] two sources deriving the same id are reported as a collision naming every path and the one used, and the run continues → AC-19
- [x] a spec whose inline code holds a shell command (`` `uv run decision-memory` ``), quoted prose (`` `read only` ``), or a dotted field name (`` `decision.chosen` ``) adds nothing to the mention count, while a renamed single segment directory (`` `oldlib/` ``), a wrong case path (`` `App/Dashboard/Page.Tsx` ``), and a missing file with a known extension (`` `missing.MD` ``) each count → AC-6, AC-23

## Acceptance-criteria coverage

- AC-1 covered by the dry run and real corpus steps · AC-2 covered by the skip and id steps · AC-3 covered by the real corpus records (spec evidence cites both contributing files) · AC-4 covered by the real corpus records (code path file evidence) · AC-5 covered by the case token step · AC-6 covered by the case token step and the path shape step · AC-7 covered by the status mapping step · AC-8 covered by the real corpus records (rationale wins, stubs discarded) · AC-9 covered by the panel and title match steps · AC-10 covered by the panel prefix step · AC-11 covered by the real corpus record bodies · AC-12 covered by the `context.problem` attempted fields on specs with no Context section · AC-13 covered by the fingerprint edit step · AC-14 covered by the manifest step · AC-15 covered by the second run steps · AC-16 covered by the failing record step · AC-17 covered by the dry run step · AC-18 covered by the output override step · AC-19 covered by the collision step · AC-20 covered by the skip steps · AC-21 covered by the exit code steps · AC-22 covered by the validate step · AC-23 covered by the dropped mention step · AC-24 covered by the round trip step · AC-25 covered by the manifest step
