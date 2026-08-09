# Verify: doctor diagnostic · spec 0004 · updated 2026-08-08

_Steps derived from spec 0004 acceptance criteria. `/check verify` runs these; `/test` locks the durable ones._

## Commands

Run from the decision-memory repo. A fixture corpus is three Markdown files with the headings used in the spec's first normative fixture; any temp directory works.

- [ ] `uv run decision-memory doctor <fixture-corpus>` → the first normative fixture: coverage 3/2/1, Context and Decision each `files: 2 | percent: 66.7%`, group `["Context", "Decision"]` with `samples: ["adr/0001.md", "adr/0002.md"]`, `[]` group with `["notes.md"]`, `descendant symbolic link | count: 1 | unseen subtrees: 1` with `["linked.md"]`, exit 0 → AC-1, AC-3, AC-5, AC-6, AC-7, AC-8
- [ ] `uv run decision-memory doctor <fixture-corpus> --samples 0` → no `samples:` line appears anywhere → AC-1, AC-8
- [ ] `uv run decision-memory doctor <empty-dir>` → the zero fixture: 0/0/0 coverage, `no heading evidence found`, `no heading sets found`, `none`, exit 0 → AC-5, AC-8, AC-9
- [ ] `uv run decision-memory doctor <missing-path>` → exit 3 → AC-10
- [ ] `uv run decision-memory doctor <a-file>` → exit 3 → AC-10
- [ ] `uv run decision-memory doctor <dir> --samples -1` → exit 2, no survey report printed → AC-1, AC-10
- [ ] `uv run decision-memory doctor <dir> --samples abc` → exit 2 (Typer syntax error) → AC-10
- [ ] `uv run decision-memory doctor <symlink-to-dir>` → surveys the resolved target, sample paths relative to the target → AC-2
- [ ] run `doctor` twice on the same corpus → byte identical output → AC-3

## Manual

- [ ] a corpus with a hidden `.git` directory holding Markdown → the Markdown inside is not counted, and the directory reports as `hidden directory | count: 1 | unseen subtrees: 1` → AC-2, AC-7
- [ ] a hidden Markdown file such as `.hidden.md` in a normal directory → analyzed, sample path `.hidden.md` → AC-2
- [ ] files named `.MD`, `.Markdown`, and `.mdown` → all analyzed; a `.txt` and `.json` file are ignored and counted under non markdown ignored → AC-2, AC-7
- [ ] a symbolic link to a directory inside the corpus → `descendant symbolic link` with `unseen subtrees: 1` and its contents never counted; a broken or cyclic link reports the same reason with `unseen subtrees: 0` → AC-2, AC-7, AC-11
- [ ] a Markdown file with invalid UTF 8 bytes → `unreadable Markdown file` skip, the rest of the survey continues, exit 0 → AC-9
- [ ] a root directory that cannot be read → the survey still completes with exit 0 and reports one `unreadable directory` skip for `.` with `unseen subtrees: 1` → AC-9
- [ ] a Markdown file with `## X` twice → X counts once in the common headings section → AC-5
- [ ] an `##` line inside a closed fence → not counted; an unmatched fence opener followed by an `##` → the heading counts, matching the shipped adapter → AC-4
- [ ] a Markdown file with a leading UTF 8 BOM and CRLF or CR line endings → headings counted correctly → AC-4
- [ ] a heading containing a double quote → rendered escaped as `\"` by JSON serialization → AC-8
- [ ] a file with no H2 → `[]` group with its path under samples → AC-6
- [ ] two files with the same headings in different order → one shared group → AC-6
- [ ] `--samples 2` on a group with more paths → exactly 2 sorted sample paths, the group's file count unchanged → AC-1, AC-3, AC-6, AC-7
- [ ] `git status` before and after a run → no files created or modified by `doctor` → AC-11

## Acceptance-criteria coverage

- AC-1 covered by the samples steps (default, zero, negative, and non integer) · AC-2 covered by the hidden path, suffix, and symlink root steps · AC-3 covered by the repeat run and sample limit ordering · AC-4 covered by the fence and decoding steps · AC-5 covered by the heading count and percentage steps · AC-6 covered by the grouping and empty set steps · AC-7 covered by the coverage and unseen subtree steps · AC-8 covered by the normative fixtures and escaping · AC-9 covered by the unreadable and empty corpus steps · AC-10 covered by the exit code steps · AC-11 covered by the no writes step
