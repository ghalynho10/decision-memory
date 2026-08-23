# decision-memory feature scope audit — 2026-08-16

An independent count of the real feature scope, verified against repo evidence rather than
against `docs/scope/scope.md`'s "At a glance" table or `docs/where-things-stand.md`'s prose.

Every claim below is labelled **VERIFIED** (a command was run or the exact line was read) or
**INFERRED** (judgment, marked as such).

---

## Method note on origin evidence

**VERIFIED.** `scope.md` has been renumbered repeatedly, so searching git history by feature
*number* returns garbage. The history search was re-run by feature *name*
(`git log --reverse -S"<name>" -- docs/scope/scope.md`). The baseline is commit `051823e`
(2026-08-06, "add initial project scope document with feature roadmap and workflow legend"),
which contains **7 feature rows plus a 7-item Deferred list** — that is the "planned before work
began" set. The first code commit under `src/` is `118aa95` (2026-08-07), so the original scope
predates all implementation.

**VERIFIED.** Original 7 rows at `051823e`, with today's numbers: Stack & architecture (1),
Coding standards & tooling (2), Canonical decision record schema & validator (3), jsmastery specs
adapter (4), Core cited query (→9), Reliable multi source retrieval (→10), Proven correctness /
evaluation harness (→11). The original Deferred list at `051823e` includes
`- **MCP server interface**: exposes the query function as an MCP tool inside a coding agent · needs a decision`
— so feature 14 is originally conceived, not later-invented.

---

## 1–3. Per-feature table

Origin key: **ORIG** = present in `051823e`; **PLAN** = later roadmap addition with no
defect/review/experiment origin cited; **EMERG** = origin language cites a review, experiment,
`/debug` finding, or a spec's own follow-up defect list.

| # | Feature | Origin (VERIFIED: first scope.md commit) | Origin class | Shape (INFERRED) | verify.md ticks (VERIFIED) |
|---|---|---|---|---|---|
| 1 | Stack & architecture | `051823e` 08-06 | ORIG | **Not a capability** — scaffold/setup | none exists (spec 0001 is a flat file) |
| 2 | Coding standards & tooling | `051823e` 08-06 | ORIG | **Not a capability** — tooling/process | none exists (no spec) |
| 3 | Canonical record schema & validator | `051823e` 08-06 | ORIG | Capability | none exists (spec 0002 is a flat file) |
| 4 | jsmastery specs adapter | `051823e` 08-06 | ORIG | Capability | **20/20 ticked, 0 unticked** |
| 5 | `doctor` diagnostic | `71c09cc` 08-08 | PLAN | Capability (own CLI command) | **23/23 ticked, 0 unticked** |
| 6 | Runtime adapter loading | `1119df2` 08-08 | PLAN | Capability | **11/11 ticked, 0 unticked** |
| 7 | Adapter conformance + `test-adapter` | `71c09cc` 08-08 | PLAN | Capability (own CLI command) | **23/23 ticked, 0 unticked** |
| 8 | Built-in ADR adapters | `71c09cc` 08-08 | PLAN | Capability | none exists (no spec) |
| 9 | Core cited query | `051823e` 08-06 | ORIG | Capability (the core one) | **92/93 ticked, 1 unticked** |
| 10 | Reliable multi source retrieval | `051823e` 08-06 | ORIG | Capability | exists but **0 checkboxes** — prose ladder |
| 11 | Proven correctness (eval harness) | `051823e` 08-06 | ORIG | Capability (`evaluate`) | **12/14 ticked, 2 unticked** |
| 12 | Flat single file spec support | `4a787be` 08-08 | EMERG (spec 0003 design) | Capability | none exists (no spec) |
| 13 | Declarative adapters | `1119df2` 08-08 | PLAN | Capability | none exists (no spec) |
| 14 | MCP server interface | `051823e` 08-06 (Deferred list) | ORIG | Capability | none exists (no spec) |
| 15 | CLI presentation redesign | `03aaa3e` 08-10 | PLAN | Capability (UX surface) | **0/37 ticked, 37 unticked** |
| 16 | Abstention verification reliability | `00d4425` 08-12 | **EMERG** | **Bug fix / hardening** | **1/48 ticked, 47 unticked** |
| 17 | Retrieval query hardening | `00d4425` 08-12 | **EMERG** | **Review-followup cleanup** | none exists (no spec) |
| 18 | Corpus gap and staleness awareness | `c8d5635` 08-12 | **EMERG** | Capability | none exists (no spec) |
| 19 | Field aware retrieval ranking | `dff4824` 08-14 | **EMERG** | **Bug fix** | **none exists** (spec 0011 has only index.md, rationale.md) |
| 20 | Stable ranking tie break | `5f27628` 08-14 | **EMERG** | **Bug fix** | **0/18 ticked, 18 unticked** |
| 21 | Superseded chunks after reingest | `5f27628` 08-14 | **EMERG** | **Bug fix** | none exists (no spec) |
| 22 | Shipped prebuilt index | `19dc8e4` 08-15 | PLAN | Capability | **none exists** (spec 0014 has only index.md, rationale.md) |
| 23 | Store path key in project config | `19dc8e4` 08-15 | EMERG (spec 0014 design) | Capability (small) | none exists (no spec) |

### The four flagged in the brief — exact origin quotes (VERIFIED)

**Feature 17** — `docs/scope/scope.md:162`: "Fix four unresolved minors from the feature 10 review
(`docs/reviews/2026-08-11-multi-source-retrieval.md`), still present in code…". Done-when,
`scope.md:163`: "all four are fixed and regression locked by tests, **per the review's suggested
fixes**."

*INFERRED:* the clearest case in the set. It is a review triage list — a dead constant, a missing
layering test, a trace that prints invented dispositions — that got a feature row instead of being
folded into feature 10. `scope.md:166` even concedes one of the four is closed by spec 0011
instead ("Do not fix it twice; whichever feature lands first takes it"), which is not how
independent features behave.

**Feature 19** — `scope.md:168` heading: "· from spec 0011". `scope.md:171`: "**Carried from:**
experiment 0007 finding 3, which routed the retrieval side decision to `/architect`."

*INFERRED:* bug fix. The body names three defects in shipped code, and the done-when
(`scope.md:170`) is "DM-0008's `decision.chosen` chunk is in the accepted eight in 6 of 6 fixture
runs" — a regression bar, not a capability a user points at. Nothing new becomes possible;
existing retrieval stops being wrong.

**Feature 20** — `scope.md:183` heading: "· from spec 0012". `scope.md:186`: "**Carried from:**
experiment 0015's first follow up item, which routed the tie break to `/architect`."

*INFERRED:* bug fix, and the weakest row in the table. Its done-when (`scope.md:185`) ends "**No
score, rank, disposition, or accept limit changes**" — it explicitly promises zero behavioural
delta. Its own build result (`scope.md:196`) records the measurement "came back negative: both
builds accepted the same eight chunks in the same order, before the fix as well as after, so the
tie break was real in code and was not changing answers on this corpus."

**Feature 21** — `scope.md:201`: "**Retrieval can serve superseded text.** … **Measured while
designing spec 0012**: ingesting one record, editing its source, and reingesting into the same
store leaves both versions live, 14 chunks where 7 are current".

*INFERRED:* bug fix. The row is titled as a defect, opens with a bolded defect statement, and
names the two lines of code at fault ("`write_record` never deletes the record's prior chunk rows,
and `active_chunks()` joins on `record_id` alone").

### The other 19 — what the sweep found

**VERIFIED.** Grepping all origin language (`Carried from:`, `· from spec`, `Measured while`,
`/debug finding`, review citations) turns up **four more** rows with debugging/side-discovery
origin beyond the four flagged:

- **Feature 16** — `scope.md:224`: "**Carried from:** spec 0008 Follow-up items 1, 6, 7, 8, 9;
  spec 0009 `verify.md` known state; **the 2026-08-12 `/debug` finding**; the spec 0010 cross
  check."
  *INFERRED:* the largest row in the file (~50 lines of measurement notes, 24 ACs) and still a
  **bug fix**. Done-when (`scope.md:223`) is "query 4 and query 5 abstain in both repeated live
  batches" — a defect bar. It is enormous engineering, but calling it a "feature" claims a
  capability that already existed and was being repaired.
- **Feature 18** — `scope.md:271` heading "· from spec 0010"; `scope.md:275`: "**Carried from:**
  spec 0010 Follow-up, experiments 0001 (finding F4) and 0002."
  *INFERRED:* emerged origin but **genuine capability** — done-when (`scope.md:273`) is "a query
  answered from a corpus with known skipped records **says so**", which is new user-visible
  behaviour, not a repair.
- **Feature 12** — first appears at `4a787be` (2026-08-08) not as a row but as a Deferred bullet
  reading "**Flat single file spec support** (from spec 0003): the adapter reads directory specs
  only; five of the twenty sources… are flat `NNNN-title.md` files."
  *INFERRED:* spec-design side-discovery, but a genuine capability (new corpus shape supported).
- **Feature 23** — `scope.md:324` heading: "· needs a decision · **from spec 0014**".
  *INFERRED:* emerged from spec 0014's design; `scope.md:303` records the discovery that prompted
  it. Genuine capability, but very small — one config key.

**VERIFIED.** Features 1–11, 13, 14, 15, 22 carry **no** debugging-origin language. Features 5, 6,
7, 8 were added in the two 2026-08-08 planning commits ("renumber plan with adapter accessibility
sequence" / "…with runtime adapter loading and declarative adapters") as a forward roadmap — the
diff contains no review, experiment, or defect citation, and the same commit added the Deferred
bullet "**Adapter accessibility sequencing**: `doctor`, then real corpus survey using `doctor`,
then the importlib part of runtime loading, then `test-adapter`, then built-in adapters…"
(`scope.md:361`).

### Two documentation errors found along the way

- **VERIFIED.** `scope.md:282` says "Features 14 and 22 joined it on 2026 08 15, **moved out of
  V2** on a deliberate call." True for 14 (`git show 19dc8e4~1:docs/scope/scope.md` shows
  `| 14 | MCP server interface | V2 | planned |`) but **false for 22** — feature 22 does not exist
  anywhere in `scope.md` before `19dc8e4`; it was created directly into Slice 4. It was never in V2.
- **VERIFIED.** The table marks 10 rows `| done |` but only **7** section headings carry `· done`
  (features 3, 4, 5, 6, 7, 9, 11). Features 1, 2, and **10** are `done` in the table with no
  `· done` on their heading.

---

## 4. Recommended feature count

**INFERRED throughout this section.**

Raw tallies from the table above:

| Class | Count | Features |
|---|---|---|
| Originally scoped (in `051823e`) | **8** | 1, 2, 3, 4, 9, 10, 11, 14 |
| Later planned expansion (no defect origin) | **7** | 5, 6, 7, 8, 13, 15, 22 |
| Emerged, genuine capability | **3** | 12, 18, 23 |
| Emerged, bug-fix / cleanup shape | **5** | 16, 17, 19, 20, 21 |

The over-count suspicion is correct, and it is **8 rows** with byproduct origin, not 4 — features
12, 16, 17, 18, 19, 20, 21, 23. But origin and shape come apart: three of those eight (12, 18, 23)
deliver something a user can point at, and two originally-scoped rows (1 and 2) do not.

**Three defensible lines — the range, rather than one number:**

- **8** — strictly "planned before any code was written." Clean and unarguable, but it understates
  the work badly: it excludes `doctor`, `test-adapter`, runtime adapter loading, and the shipped
  prebuilt index, all real user-facing capabilities that simply were not foreseen on day one.
- **16** — every row that is a genuine independent capability regardless of when it was conceived:
  23 minus features 1 and 2 (scaffold and tooling, not capabilities) minus the 5 bug-fix rows.
  **This is the recommended number for a resume claim.**
- **18** — 16 plus features 1 and 2, if "chose and scaffolded the stack" and "established the
  standards and CI gates" count as scoped deliverables. Defensible on a resume that talks about
  engineering practice rather than product surface.

**So: "18 planned features, 16 of them distinct capabilities, 8 scoped up front" is the honest
framing.** The claim not to make is "23 features" — five of those rows are repairs to code that
already shipped, and one of the five (feature 20) measured its own defect as never having fired.

A separate caution: of the 16 capabilities, **10 are marked done and only 4 have a fully-ticked
verify.md** (see §5). "Built 16 features" and "shipped 16 features" are different claims.

---

## 5. The 10-vs-11 "done" discrepancy

**`scope.md`'s 10 is correct. `where-things-stand.md`'s "Eleven" is a prose miscount.**

**VERIFIED.** `docs/where-things-stand.md:25` reads: "Eleven features done: stack, standards, the
canonical record schema and validator, the jsmastery specs adapter, `doctor`, runtime adapter
loading, the adapter conformance suite with `test-adapter`, core cited query, reliable multi
source retrieval, and the evaluation harness." Counting that list: stack (1), standards (2),
schema+validator (3), adapter (4), doctor (5), runtime loading (6), conformance (7), core cited
query (8), multi source retrieval (9), evaluation harness (10). **The list names 10.** It matches
`scope.md`'s table exactly. The word "Eleven" has no eleventh member — a typo, not a disagreement
about a feature.

**VERIFIED.** Independent of the prose, `where-things-stand.md` is stale: line 137 states "Current
branch is `feature/abstention-verification`" while the actual branch is `prebuilt-index`, and its
dateline is 2026-08-14. It is not a usable source.

**On test/verify evidence rather than either document's prose**, the 10 "done" rows are *not*
uniformly evidenced. **VERIFIED counts:**

- Fully ticked: features 4 (20/20), 5 (23/23), 6 (11/11), 7 (23/23) — **4 features**.
- Partially ticked: feature 9 (**92/93**, unticked item at
  `docs/specs/0007-core-cited-query/verify.md:9`); feature 11 (**12/14**, unticked at
  `docs/specs/0009-proven-correctness-evaluation-harness/verify.md:24-25`, both reading
  "currently FAIL").
- No verify.md at all: features 1, 2, 3 (specs 0001 and 0002 are flat files; feature 2 has no spec).
- Feature 10: `docs/specs/0008-reliable-multi-source-retrieval/verify.md` exists but is a **prose
  ladder with zero checkboxes** (`grep -cE '\[x\]|\[ \]|PASS|FAIL|✓|✗'` returns **0** over 146
  lines). Its scope row records the outcome instead — `scope.md:154`: "gates 1-6 pass with cited
  evidence; **live smoke gates 7-8 fail** on the Feature 11 verification gap", and `scope.md:157`:
  "This feature does not declare AC-15 passed."

*INFERRED:* **10** is the right answer to "what does the project call done," and the Legend backs
that (`scope.md:387`: "`done`: you, when you decide it is"). But **4** is the number with a
fully-ticked verification checklist behind it, and feature 10 is `done` in the table while carrying
two recorded live-gate failures. "10 features complete" is supportable as a status claim;
"10 features verified" is not.

---

## 6. Test counts — run live 2026-08-16

**VERIFIED.** `uv run pytest -q`:

```
713 passed, 13 skipped, 27 deselected in 28.90s
```

**VERIFIED.** `uv run pytest -m integration -q`:

```
FAILED tests/test_self_corpus_fixture.py::TestFixtureIsolation::test_discovery_at_the_repository_root_cannot_see_the_fixture
FAILED tests/test_self_corpus_fixture.py::TestFixtureDrift::test_regenerating_matches_the_committed_manifest_hashes
2 failed, 19 passed, 6 skipped, 726 deselected in 2.55s
```

The integration failure is fixture drift, not a code regression — the assertion message reads "the
fixture has drifted from the committed manifest; regenerate it deliberately with
build-self-corpus-fixture.sh and review the diff", with "Left contains 10 more items, first extra
item: `{'path': 'docs/specs/0011-field-aware-retrieval-ranking/index.md', ...}`"
(`tests/test_self_corpus_fixture.py:125`).

*INFERRED:* this is the situation `scope.md:369` predicted — "the frozen self corpus fixture goes
stale by design and only a deliberate regeneration surfaces the drift through its manifest hashes."

**Every unit-test figure in the markdown is stale.** VERIFIED examples: `scope.md:196`
"656 unit tests", `scope.md:269` "646 unit tests", `where-things-stand.md:27` "**596 unit tests
pass**". Actual is **713**. None of those numbers should be carried forward.

---

## 7. Current git state

**VERIFIED**, all from live commands:

| Item | Value |
|---|---|
| Commit count (`git rev-list --count HEAD`) | **197** |
| Working tree clean? | **No** — `M docs/session-notes.md` (`git diff --stat`: 1 file changed, 3 insertions(+), 4 deletions(-)) |
| Current branch | **`prebuilt-index`** |
| Commits ahead of `main` | **5** |
| Most recent commit | **`c337d60`**, **2026-08-16 00:03:11 -0400**, "docs(notes): record the trailer rule recurrence and the staged set gate" |

---

## Bottom line

The over-count suspicion holds and is larger than estimated: **8 of 23 rows have byproduct
origin**, not 4 — features 12, 16, 17, 18, 19, 20, 21, and 23. But the line worth drawing is shape,
not origin: **5 rows are repairs to shipped code** (16, 17, 19, 20, 21) and **2 rows are not
capabilities at all** (1, 2). Feature 16 is the one that will feel wrong to drop — by far the
biggest engineering effort in the repo — but its own done-when is a defect bar, and feature 20
shipped a fix whose measurement came back negative.

Recommended resume claim: **16 distinct capabilities across 18 planned features, 8 scoped before
implementation began, 10 currently marked complete** — with the caveat that only 4 of those 10
have a fully-ticked verification checklist.
