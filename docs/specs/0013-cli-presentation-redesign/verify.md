# 0013. CLI presentation redesign, verification

Run against a real build, not a fixture, unless a step says otherwise. Each step
names the acceptance criteria it covers.

## Frozen surfaces (run these first, and again last)

- [ ] Before any rendering change lands: capture
      `decision-memory query "<a real question>" --debug > baseline-query-debug.txt`
      and `decision-memory evaluate <corpus> > baseline-evaluate.txt` from the
      current build, and commit both under
      `docs/experiments/data/cli-baseline/` → **AC-5**, **AC-6**
- [ ] After the change: re run both redirected and `diff` against the committed
      baselines. Zero differences, whole file, not a grep → **AC-5**, **AC-6**
- [ ] `bash docs/experiments/data/jobpilot-abstention-cause.sh "<question>" 1`
      against a real corpus: the per run grep block in `meta.txt` is non empty
      and matches the pre change run → **AC-5**
- [ ] `python3 docs/experiments/data/coverage-directness-extract.py` over a post
      change transcript parses without an empty result → **AC-5**
- [ ] Same command on a terminal shows colour, and `| cat` shows none, with the
      plain bytes identical to the baseline → **AC-4**, **AC-5**
- [ ] `query --debug` piped through a **failure**: against a missing store, a
      stale index with no `--allow-stale`, and a held lock. Each keeps today's
      failure line and gains no `hint` line, proving AC-5 wins over AC-9 →
      **AC-5**, **AC-9**
- [ ] `evaluate` piped through a failing fixture and through a missing corpus:
      same, byte identical to the baseline → **AC-6**, **AC-9**

## The visual language

- [ ] Every one of the eight commands run on a terminal: header reads
      `command — subject`, one rule under it and one above the summary, sections
      labelled and indented 2 cells, one final `summary … · exit n` line →
      **AC-1**
- [ ] Pipe every command's output through `awk 'length > 80'`: no output, on the
      widest real inputs (an absolute store path, a long H2 heading, a long
      question) → **AC-2**
- [ ] `NO_COLOR=1 decision-memory doctor docs/specs`: no escape sequences, and
      every status still readable as a shape plus a word → **AC-3**, **AC-4**
- [ ] `TERM=dumb`, output redirected to a file, and a stream whose `encoding` is
      `None` (unit level): each produces the ASCII marker set and no escape
      sequences, and none raises → **AC-4**
- [ ] Colour and glyphs never disagree: no configuration produces colour without
      the Unicode glyph set or the reverse, because one predicate decides both →
      **AC-4**

## Markers and overflow

- [ ] A corpus that produces an adapt run with `written`, `rewritten`,
      `unchanged`, and `failed` records: markers are `+`, `+`, `~`, `x`, and each
      row still prints its real state word → **AC-3**
- [ ] An ingest run producing `added`, `updated`, `unchanged`, and `removed`:
      markers are `+`, `+`, `~`, `+` → **AC-3**
- [ ] A record whose path is wider than its column: the path shortens at the
      tail with `…` on a terminal and `...` when piped, the identifying prefix
      survives, and the line stays inside 80 → **AC-2**, **AC-4**
- [ ] A citation whose relative path is very long: it wraps on its own
      continuation line with the earlier columns blank padded, and no earlier
      column wraps → **AC-2**
- [ ] `decision-memory version` prints a header with the command word and no
      subject; `ingest` and `adapt` print their two sided subjects; a corpus
      resolved from `.decision-memory.yml` prints the resolved path → **AC-1**

## Content is never mode dependent

- [ ] `decision-memory doctor <a corpus with more than 25 distinct H2 headings>`
      on a terminal and piped: the same number of heading rows in both, with no
      elision line → **AC-7**
- [ ] `decision-memory adapt <a corpus of 15 or more specs> --dry-run` on a
      terminal and piped: every record row present in both → **AC-7**

## Values are real

- [ ] `decision-memory query "<answerable question>"`: the grounded count equals
      the number of distinct records across the printed sources, and grounded
      plus "no supporting evidence" equals the consulted count → **AC-8**
- [ ] `decision-memory query "<unanswerable question>"`: prints `not enough
      evidence here` verbatim, exit 0, with refs rows carrying a record id and a
      real path and no record title → **AC-8**
- [ ] `decision-memory validate <one record file>`: the identity row shows the
      file path, not an invented record title → **AC-8**
- [ ] No screen prints a model name, a provider name, an index build timestamp,
      an ingest stage word, or a `dropped (low)` disposition → **AC-8**
- [ ] `git diff` over `src/decision_memory/application/dto.py` and every other
      DTO module: empty → **AC-8**

## Failures

- [ ] `decision-memory doctor` with no argument: `error`, then an indented
      `hint` naming a real command, then `exit 2`, on the same stream Click uses
      today → **AC-9**
- [ ] `decision-memory doctor docs/specs --bogus`: the same three part grammar →
      **AC-9**
- [ ] `decision-memory query "..."` against a stale index without
      `--allow-stale`: the same grammar, hint names `ingest --rebuild` or
      `--allow-stale`, exit 1 → **AC-9**
- [ ] `decision-memory validate --adapter jsmastery-specs <a record file>`: the
      same grammar, exit 2 → **AC-9**
- [ ] `decision-memory doctor /does/not/exist`: the same grammar, exit 3 →
      **AC-9**
- [ ] The byte pinning tests for a missing required argument and an unknown flag
      fail loudly when Click's rendering is stubbed out, proving they actually
      pin the override → **AC-9**
- [ ] Every hint printed matches the failure kind table in the spec, wording for
      wording, and every hint names a command or flag that really exists →
      **AC-9**

## Help

- [ ] `decision-memory --help` lists all eight commands, `evaluate` included →
      **AC-10**
- [ ] `decision-memory query --help` lists all seven flags, the four filters
      included → **AC-10**
- [ ] Each command's exit code table matches what the command can really return;
      `doctor --samples -1` really exits 2 and `doctor --help` says so →
      **AC-10**

## Layering

- [ ] The layering test passes with exactly one exemption, and its comment names
      the follow up → **AC-11**
- [ ] Delete the exemption locally: the test fails on
      `application/settings.py`, proving it checks the real rule → **AC-11**
- [ ] Add a throwaway `from decision_memory.infrastructure...` import to
      `presentation/render.py`: the test fails → **AC-11**

## Coverage map

AC-1 covered by the eight command walk and the header subject step · AC-2 by the
width sweep and the two overflow steps · AC-3 by the `NO_COLOR` step and the two
marker mapping steps · AC-4 by the degradation steps and the single predicate
step · AC-5 and AC-6 by the baseline diffs, the failure path diffs, and the three
instrument runs · AC-7 by the two large corpus steps · AC-8 by the value steps
and the empty DTO diff · AC-9 by the five failure paths, the precedence steps,
the hint table check, and the pinning test · AC-10 by the three help steps ·
AC-11 by the three layering steps
