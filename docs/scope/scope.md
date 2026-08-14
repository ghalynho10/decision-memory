# Scope: decision memory

A local, cited RAG system that makes software decision history queryable. Point it at a project's decision records and ask why something is built the way it is, and get an answer with citations back to the source, or an honest "not enough evidence here."

**Build approach:** Skateboard (ship the smallest usable whole first, a real person gets a real cited "why" answer, then grow it release by release).
**Workflow:** Beta (check verify, then test). The project's default rigor tier; a feature's own tier tag overrides it.

_You are in charge. Every box below is a suggestion, not a gate: run any, skip any, and mark a feature done when you decide it is. The workflow records what you actually did (including "skipped"), it never requires a step. The one thing it asks is that a load bearing decision be written down (a spec), not that any check be run._

## At a glance

| # | Feature | Phase | Status |
|---|---------|-------|--------|
| 1 | Stack & architecture | Foundation | done |
| 2 | Coding standards & tooling | Foundation | done |
| 3 | Canonical decision record schema & validator | Foundation | done |
| 4 | jsmastery specs adapter | Foundation | done |
| 5 | `doctor` diagnostic | Foundation | done |
| 6 | Runtime adapter loading | Foundation | done |
| 7 | Adapter conformance suite and `test-adapter` | Foundation | done |
| 8 | Built-in ADR adapters | Foundation | planned |
| 9 | Core cited query | Slice 1 | done |
| 10 | Reliable multi source retrieval | Slice 2 | done |
| 11 | Proven correctness (evaluation harness) | Slice 3 | done |
| 12 | Flat single file spec support | V2 | planned |
| 13 | Declarative adapters | V2 | planned |
| 14 | MCP server interface | V2 | planned |
| 15 | CLI presentation redesign | Slice 4 | planned |
| 16 | Abstention verification reliability | Slice 3 | in-progress |
| 17 | Retrieval query hardening | Slice 2 | planned |
| 18 | Corpus gap and staleness awareness | Slice 3 | planned |
| 19 | Field aware retrieval ranking | Slice 2 | in-progress |

## Foundations

### 1. Stack & architecture
Decide the embedding model, vector store, chunking library, and the `uv` managed CLI package layout, then scaffold a runnable empty project.
**Done when:** the stack is recorded in a spec and the empty scaffold boots locally (`uvx decision-memory`) and passes build.
spec [0001](../specs/0001-stack-and-architecture.md) · code in src/decision_memory/
- [x] Decide the stack (spec): `/architect stack & architecture`
- [x] Scaffold from the decision: `/develop stack & architecture`

### 2. Coding standards & tooling
Capture conventions from the real scaffolded project into root `AGENTS.md`, then install lint, format, and pre commit enforcement.
**Done when:** root `AGENTS.md` reflects the real stack, and lint, format, and pre commit run clean.
- [x] Capture conventions + tooling choices: `/audit`

### 3. Canonical decision record schema & validator · done
The YAML frontmatter plus markdown body schema (id, title, status, context, decision, why, rationale summary, consequences, evidence, tags, supersedes), and a validator that enforces the field rules: evidence must resolve, alternatives need a rejection reason, at least one of why or rationale summary is populated, and any field an adapter attempted and failed to populate is flagged rather than silently absent.
**Done when:** a hand written record that violates each rule above is rejected with a clear reason, and a valid record passes.
spec [0002](../specs/0002-canonical-decision-record-schema.md) · code in src/decision_memory/
- [x] Design it (spec): `/architect canonical decision record schema & validator`
- [x] Build it: `/develop canonical decision record schema & validator`
- [x] Verify it: `/check verify` (all behaviors passed, incl. the AC-16/AC-10 date-crash fix, 2026-08-07)
- [x] Test it: `/test` (59 unit tests passing, incl. regression for the fix, 2026-08-07)

### 4. jsmastery specs adapter · done
Reads `docs/specs/<n> <name>/index.md` (plus `rationale.md` where present) and implements discover, parse, and fingerprint, following the field mapping and degradation policy already defined (rationale as list only, prose only, both, or absent; a missing rejection reason; no Decision section means no record). The fingerprint covers every file that contributes to a record, not only the entry file.
**Done when:** run against JobPilot's real `docs/specs/`, the adapter produces valid canonical records for well formed specs and a clear warning, never a fabricated field, for each degraded case in the policy table.
**Validation corpus:** `github.com/ghalynho10/job_pilot`, specs under its `docs/specs/`. Spec 0019 (resume generation quality) has already been checked against the adapter's two file `index.md` plus `rationale.md` mapping.
spec [0003](../specs/0003-jsmastery-specs-adapter/index.md) · code in src/decision_memory/
- [x] Design it (spec): `/architect jsmastery specs adapter`
- [x] Build it: `/develop jsmastery specs adapter`
  - [x] Discovery, id derivation, skip reporting, and the `adapt` command shell with `--dry-run` (AC-1, AC-2, AC-17, AC-20)
  - [x] Required field mapping, record serialization, and writing only records that validate (AC-3, AC-7, AC-16, AC-18, AC-21, AC-24)
  - [x] Change the shipped validation path: direct target checks, directory resolution, exported normalization, the new rule id (AC-22, AC-23)
  - [x] Full field mapping: code path evidence, section precedence and stubs, residue body, attempted fields, and alternatives across both option shapes (AC-4, AC-5, AC-8, AC-9, AC-10, AC-11, AC-12)
  - [x] Fingerprint, manifest, incremental rewriting, and collision reporting (AC-13, AC-14, AC-15, AC-19, AC-25)
  - [x] Narrow the unresolved mention count to path shaped tokens: the shape test on the pre strip token, the case insensitive known extension constant, occurrences not distinct (AC-6)
- [x] Verify it: `/check verify jsmastery specs adapter`
- [x] Test it: `/test jsmastery specs adapter`

### 5. `doctor` diagnostic · done
A reading aid for unfamiliar decision corpora. Point it at a directory and it reports markdown file count, common H2 headings, and exact H2 heading set groups with samples, using deterministic parsing and no fuzzy matching.
**Done when:** a user can run `decision-memory doctor <path>` on an ADR corpus and see whether a built-in adapter is likely to fit, without producing records or inferring meaning.
spec [0004](../specs/0004-doctor-diagnostic/index.md) · code in src/decision_memory/
- [x] Design it (spec): `/architect doctor diagnostic`
- [x] Build it: `/develop doctor diagnostic`
  - [x] Basic survey and report through every architecture layer (AC-1, AC-5, AC-6, AC-8)
  - [x] Exact Markdown grammar and shared unmatched fence fixture (AC-4)
  - [x] Honest deterministic path accounting (AC-2, AC-3, AC-7, AC-9, AC-11)
  - [x] CLI validation and exit contract (AC-1, AC-9, AC-10)
- [x] Verify it: `/check verify doctor diagnostic`
- [x] Test it: `/test doctor diagnostic`

### 6. Runtime adapter loading · done
Make third party adapters usable without forking: `adapt` and `validate` can load an adapter by Python module path, while `jsmastery-specs` remains the default adapter behind the same protocol. Persist adapter, corpus root, and output directory in `.decision-memory.yml`, and ship a minimal starter adapter template plus a short writing guide.
**Done when:** a minimal fake adapter loads through the CLI flag, the importlib loading mechanism is available for `test-adapter`, project config can persist the common adapter settings, and an adapter author has a small teaching template plus documentation separate from spec 0003.
spec [0005](../specs/0005-runtime-adapter-loading/index.md) · code in src/decision_memory/
- [x] Design it (spec): `/architect runtime adapter loading`
- [x] Build it: `/develop runtime adapter loading`
  - [x] Extend the protocol and add the explicit runtime loader while preserving the built in path (AC-1 to AC-4, AC-9, AC-14, AC-15, AC-20)
  - [x] Add write free corpus validation and failure containment (AC-5 to AC-9, AC-20)
  - [x] Add strict project config discovery and precedence (AC-10 to AC-13)
  - [x] Ship the starter package, author guide, and full quality gates (AC-16 to AC-19)
- [x] Verify it: `/check verify runtime adapter loading`
- [x] Test it: `/test runtime adapter loading`

### 7. Adapter conformance suite and `test-adapter` · done
A battery of checks any adapter author can run against their adapter to prove protocol compliance and anti fabrication behavior, including format drift fixtures with wrong headings and missing fields.
**Done when:** `decision-memory test-adapter SELECTOR --cases PATH` gives a clear pass or fail report, malformed inputs produce no confident records, and every built-in adapter passes the same suite.
spec [0006](../specs/0006-adapter-conformance-test-adapter/index.md) · code in src/decision_memory/
- [x] Design it (spec): `/architect adapter conformance suite and test-adapter`
- [x] Build it: `/develop adapter conformance suite and test-adapter`
  - [x] Strict manifest, shared selector, public engine, and first valid CLI path (AC-1 to AC-5, AC-15, AC-16, AC-18)
  - [x] Runtime contract, deterministic operation, and fingerprint checks (AC-9 to AC-13)
  - [x] Grammar drift, corruption, copied workspace, and failure artifact handling (AC-6 to AC-9, AC-14, AC-17)
  - [x] Starter recursion and collision rule, both adapter manifests, guide, and quality gates (AC-19 to AC-22)
- [x] Verify it: `/check verify adapter conformance suite and test-adapter`
- [x] Test it: `/test adapter conformance suite and test-adapter`
- [x] Review it: `/check review adapter conformance suite and test-adapter`
- [x] Document it: `/document pr adapter conformance suite and test-adapter`

### 8. Built-in ADR adapters · needs a decision
Ship built-in adapters for common ADR formats such as MADR and plain ADR, versioned as adapter ids like `madr@1`, calibrated against real corpora rather than synthetic examples.
**Done when:** `doctor` has surveyed 2 to 3 real MADR or plain ADR repositories, the adapters produce valid records for standard corpora, pass `test-adapter` including format drift tests, and adapt at least 80 percent of documents in each survey corpus or report that the corpus is not a fit.
**Candidate corpora already surveyed (2026-08-12):** `docs/experiments/data/adr-candidates.tsv` lists 257 real ADR and MADR corpora with exact record counts, plus the script that produced it. Median 12 records and 85 corpora with 20 or more, so the 80 percent bar above is supportable without rescoping. Two findings to carry into the spec: discovery cannot assume a directory, because ten conventions appear in the top twenty repos alone (`docs/adr`, `docs/decisions`, `doc/architecture/decisions`, `src/adr`, `ADR`, `decisions`, and more); and the deepest two corpora look agent generated, so prefer a long lived human corpus such as `apache/james-project` (77 records) when calibrating. The survey is discovery only. Running `doctor` across the shortlist, to see whether the heading shapes are consistent enough for one adapter, is still owed and belongs in the design pass.
- [ ] Design it (spec): `/architect built-in ADR adapters`

## Slice 1: Core cited query

### 9. Core cited query · done
Ingest real specs (parse, chunk on canonical field boundaries, embed, index, with metadata kept as structured queryable fields), semantic only retrieval, and a CLI `query` command returning an answer plus citations through a clean function boundary, with an explicit "not enough evidence" path when nothing supports an answer. Include query transparency: a debug view showing retrieved chunks, scores, filters, excluded candidates, and whether abstention happened at retrieval or after claim verification. Incremental re ingestion via the adapter's fingerprint is built in here, not deferred, since retrofitting it later means re embedding everything. This retrieval pipeline can proceed in parallel with adapter accessibility work.
**Done when:** a user runs the CLI against JobPilot's real specs and gets a cited answer, or an honest no evidence response, to query 1 (why was the private beta access gate added, and what was the alternative) end to end, and can inspect enough retrieval detail to distinguish unsupported evidence from retrieval failure.
**Carry into the spec (retrieval must know about superseding):** if a retrieved chunk belongs to a record that carries a `superseded_by` link, the generator must be told, so the answer can say the decision was later changed instead of presenting it as current. An answer that is accurate about a superseded decision and does not say so is confident and wrong at the same time, which is the exact failure this project exists to prevent. Caveat to state plainly in the spec: this is not exercisable against the current corpus, since the jsmastery adapter does not populate supersedes. Build the check, and record it as untested, the same disposition as ladder step 4 in spec 0003.
**Carry into the spec (build plan constraint, not a protocol):** all OpenAI access goes through one module per concern (embedding, generation), so provider calls are not scattered across the pipeline. No `EmbeddingProvider` or `GenerationProvider` abstraction: infrastructure is already the swap point.
spec [0007](../specs/0007-core-cited-query/index.md) · code in src/decision_memory/
- [x] Design it (spec): `/architect core cited query`
- [x] Build it: `/develop core cited query`
  - [x] Extend the adapter result and manifest provenance contract, then establish canonical chunking and the versioned SQLite plus Chroma store (AC-2 to AC-8, AC-19, AC-20)
  - [x] Deliver the first complete JobPilot query with cited sentences, independent facets, verification, and honest abstention (AC-1, AC-10 to AC-16)
  - [x] Add incremental updates, removals, dry run spend preview, rebuild, locking, freshness, and recovery (AC-3, AC-6 to AC-9, AC-16, AC-17, AC-21)
  - [x] Complete traces, supersession disclosure, source resolution, user documentation, and all quality gates (AC-13, AC-14, AC-18 to AC-21)
- [x] Verify it: `/check verify core cited query` (all local + live behaviors pass, incl. live JobPilot query 1 against the real corpus, 2026-08-10)
- [x] Test it: `/test core cited query` (suite already written and committed during build; 401 unit + 13 integration passing, AC-traced, 2026-08-10)

## Slice 2: Reliable multi source retrieval

### 10. Reliable multi source retrieval
Add structured metadata filtering and lexical retrieval alongside semantic retrieval, so a filter can constrain the candidate set before semantic similarity chooses among it, which is what keeps the tool from confidently citing the wrong document. Exact stage ordering and whether scores fuse or run as a pipeline is an `/architect` decision.
**Decision:** metadata filtering remains an explicit retrieval constraint. Structured query types for alternatives, lineage, and supersession traversal stay deferred until Feature 11 supplies evidence. Hybrid retrieval always applies filters first, then runs BM25 and cosine retrieval, fuses ranks, and applies record diversity.
**Done when:** query 2 (what decisions affect resume generation) returns the required directly supported decisions from `DM-0004` and `DM-0019`, while query 4 (what was decided about separating server side and browser side database clients, and why) honestly abstains because its evidence is outside the adapted corpus.
spec [0008](../specs/0008-reliable-multi-source-retrieval/index.md)
- [x] Design it (spec): `/architect reliable multi source retrieval`
- [x] Build it: `/develop reliable multi source retrieval`
  - [x] Typed filters, immutable SQLite snapshot, and complete filter trace (AC-1 to AC-4, AC-10, AC-16)
  - [x] Store format `2`, immutable cosine Chroma, and exact deterministic semantic eligibility (AC-6, AC-9, AC-12)
  - [x] Versioned BM25, reciprocal rank fusion, and two pass diversity producing the multi record answer (AC-5 to AC-13, AC-16)
  - [x] Complete debug trace, documentation, deterministic coverage, and ten live smoke runs (AC-9 to AC-17)
- [x] Verify it: `/check verify reliable multi source retrieval` (gates 1-6 pass with cited evidence; live smoke gates 7-8 fail on the Feature 11 verification gap, 2026-08-11)
- [x] Test it: `/test reliable multi source retrieval` (438 unit + 14 integration passing; durable retrieval behavior locked: closed enums, ordering rules, AC-5 precedence, two pass diversity, tokenizer/digest, failure boundaries; live AC-15 smoke gates excluded and still failing per Feature 11, 2026-08-11)

**Status caveat (2026-08-11):** retrieval work is complete and verified; the two live acceptance gates (query 2 `DM-0004` coverage 0 of 5 in the post fix re run, query 4 abstention 5 of 5 answered) fail on a verification layer gap carried into Feature 11 as three items (query 4 fabrication, query 5 expected abstention, query 2 `DM-0004` coverage omission). This feature does not declare AC-15 passed.

**Correction (2026-08-12):** the feature 11 harness measured query 4 across four `--runs 3` batches (12 runs). Abstention is a coin flip: 6 of 12 abstained, with whole batches flipping between 3/3 abstain and 3/3 answer (citations `DM-0007`/`DM-0008` when it answers). The earlier "5 of 5 answered" was one unlucky sample, not a stable property, so the carry in is better described as "query 4 abstention unreliable (stochastic)" than "query 4 fabricates". Query 5 remains a stable FAIL (`DM-0002` answered 0 of 12) and query 2 `DM-0004` coverage remains intermittent (6 of 12).

### 17. Retrieval query hardening
Fix four unresolved minors from the feature 10 review (`docs/reviews/2026-08-11-multi-source-retrieval.md`), still present in code: a filter matching no chunk can mask a store parity failure or an over limit question as an honest abstention, since the token limit and parity checks run after the empty filter early return; a diversity failure's partial trace carries invented fusion dispositions (`breadth_disposition=RECORD_CAP`, `final_disposition=OUTSIDE_TOP_8`) instead of leaving that section absent; no test enforces the application and domain layers' ban on `rank_bm25`, `chromadb`, `openai`, `typer`, and `pydantic` imports; and `QUERY_SCHEMA_VERSION` is defined and exported but dead, with `schema_version=2` hardcoded at three call sites in `query.py` instead.
**Done when:** all four are fixed and regression locked by tests, per the review's suggested fixes.
- [ ] Build it: `/develop retrieval query hardening`

**Overlap with feature 19:** the fourth minor, the dead `QUERY_SCHEMA_VERSION`, is closed by spec 0011 AC-5, which uses the constant at all three call sites while bumping it to 3. Do not fix it twice; whichever feature lands first takes it.

### 19. Field aware retrieval ranking · from spec 0011
Retrieval never surfaces a `decision.chosen` chunk for a question asking what was decided, so the answer gets built from body prose about the decision and entailment correctly refuses it. Three causes, all verified in code and in the frozen transcripts: the two retrievers do not read the same document, since only the semantic side is told which field a chunk is; reciprocal rank fusion scores a missing contribution as zero behind a top 24 cut, so no chunk found by one retriever can ever beat a chunk found by both; and the tokenizer has no morphology, so a question asking what was `decided` cannot match anything. Fixed by making the field kind visible to keyword search in plain words, letting every ranked chunk contribute at any rank, and adding word ending awareness. Retrieval stays blind to what kind of question it was asked, and nothing stored changes, so no index rebuild.
**Done when:** DM-0008's `decision.chosen` chunk is in the accepted eight in 6 of 6 fixture runs, and the JobPilot `query-2-resume-generation` oracle checks where the answer came from rather than only what it says. The end to end gate result is recorded with its stage attribution but does not block, since what remains failing there belongs to spec 0010's verification stack.
**Carried from:** experiment 0007 finding 3, which routed the retrieval side decision to `/architect`. Spec 0008 Follow-up item 4 (structured query types) stays deferred: this is a ranking problem, not a new query mode.
spec [0011](../specs/0011-field-aware-retrieval-ranking/index.md) · code in src/decision_memory/
- [x] Design it (spec): `/architect field aware retrieval ranking`
- [ ] Build it: `/develop field aware retrieval ranking`
  - [ ] Move the field label mapping into the application layer, reword `decision.chosen` for lexical alignment, and compose the lexical document (AC-1, AC-2, AC-11)
  - [ ] Remove fusion eligibility, retire the top 24 boundary and its two settings fields, and advance the query schema to 3 (AC-3, AC-4, AC-5, AC-11)
  - [ ] Share the morphology rule family across retrieval and verification, and advance to `lexical-tokenizer-v2` with the pinned `morphology-v1` stemmer (AC-6, AC-7, AC-11)
  - [ ] Strengthen the JobPilot `query-2-resume-generation` oracle, then run the blocking bar and write the numbered experiment (AC-8, AC-9, AC-10, AC-12, AC-13)
  - [ ] Complete the deterministic tests, ruff, strict mypy, and the layering check (AC-14)
- [ ] Verify it: `/check verify field aware retrieval ranking`
- [ ] Test it: `/test field aware retrieval ranking`

## Slice 3: Proven correctness (evaluation harness)

### 11. Proven correctness (evaluation harness) · done
The five defining queries as fixtures with known correct sources, plus two further assertions: one whose correct answer requires the rationale summary specifically and cannot be answered from the why list alone, and one that edits a `rationale.md`, re ingests, and confirms the record's chunks updated. The questions and assertions are already fully specified; this feature builds the harness, it does not design one.
**Done when:** query 3 (which decisions are still provisional rather than ratified), query 5 (what changed the original approach to storing uploaded files, expected to return no evidence in v1), and both extra assertions pass or fail legibly against JobPilot's real corpus.
code in src/decision_memory/
- [x] Build it: `/develop proven correctness (evaluation harness)`

**Status (2026-08-12, re-verified after four `/check review` rounds):** the harness is built, verified live, and test locked; the `evaluate` command runs all eight fixtures in fixed order, reports per fixture pass or fail plus the rate across `--runs N`, and exits 0, 1, 2, or 3. It also caught a real `active_chunks` column swap bug, regression locked by an integration marked test (not unit; that test does not run on the push gate, see `verify.md`). The two fixtures still failing live are feature 10 carry-ins, not harness defects: query 5 (`DM-0002` answered instead of abstain) is stable, query 4 abstention is a measured coin flip; the harness measures and reports them, it does not patch them. Query 1 and the rationale summary assertion were re-verified live 3/3 after a review round tightened their oracle to require citation co-location. Verified with `/check verify` and `/test` (486 unit passing).

### 16. Abstention verification reliability
Close the sub sentence verification gap spec 0008 named and feature 11 measured live. A fused sentence must be verified and emitted only as atomic sub claims, so output formatting cannot restore a fabricated parent sentence. Coverage must also distinguish a stated decision from grounded reasons. The relevance floor correlates the symptom away without closing either gap.
**Done when:** query 4 and query 5 abstain in both repeated live batches. Query 4 must extract separate decision and reason facets, drop the fabricated decision, leave the decision facet uncovered, and classify any failure as facet extraction, coverage directness, or query state from the existing trace.
**Carried from:** spec 0008 Follow-up items 1, 6, 7, 8, 9; spec 0009 `verify.md` known state; the 2026-08-12 `/debug` finding; the spec 0010 cross check. Query 2 citation completeness and structured query types stay deferred as separate decisions.
spec [0010](../specs/0010-abstention-verification-reliability/index.md) · code in src/decision_memory/
- [x] Design it (spec): `/architect abstention verification reliability`
- [ ] Build it: `/develop abstention verification reliability`
  - [x] Add the initial decomposition provider, per sub claim verification, and trace path (AC-5 to AC-8, AC-10)
  - [x] Remove parent restoration and enforce the accepted context citation boundary (AC-1, AC-4, AC-5, AC-8)
  - [x] Add exact decomposition outcomes and the lexical guard contract (AC-6, AC-7, AC-10, AC-11)
  - [x] Tighten canonical facet coverage and classify query 4 failures by stage (AC-2, AC-4, AC-12)
  - [x] Replace the whole response lexical guard with the per sub claim guard (AC-6, AC-10, AC-11) — built, and **falsified by its live gate**. Experiments 0001 and 0002 showed the fragment output contract itself was the fault, not the guard granularity. Spec 0010 revised 2026-08-12; the milestones below replace this direction
  - [x] Make decomposition a check, not a rewrite: two directional lexical validity (additive per sub claim, completeness response wide), whole sentence output, and the `dropped_sentences` trace (AC-1, AC-4 to AC-8, AC-10, AC-11)
  - [x] Re-lock the deterministic tests against the new contract, including both AC-1 attacks and the additive scope regression the cross check caught (AC-1, AC-4 to AC-8, AC-10 to AC-12)
  - [x] Settle spec 0010's three open decisions (inline citation markers, the contaminated self corpus gate, the out of sync decomposition prompt) — settled 2026-08-13 as AC-13, AC-14, and the recorded prompt constants
  - [x] Clean the measurement instrument: strip chunk id markers at the generation boundary, and build the frozen self corpus gate fixture with its committed generator script (AC-5, AC-11, AC-13, AC-14)
  - [x] Run the cheap self corpus gate against that fixture and re-measure the drop rates on a clean pipeline (AC-4, AC-12, AC-14) — measured 2026-08-13 in `docs/experiments/0004-clean-pipeline-re-measurement.md`; the gate still fails
  - [x] Settle the two open decisions experiment 0004 raised and ratify the schema description deviation — settled 2026-08-13 as AC-15 (gate oracle), AC-16 (coverage directness and a numbered trigger), and AC-17 (schema descriptions bounded to rules a validator enforces)
  - [x] Make the gate able to see a wrong answer before anything is calibrated by it: state the directness exclusion to the coverage model, then add the co-located citation and abstention cause oracle, the manifest battery loader, and `evaluate --battery` (AC-15, AC-16, AC-17) — built and run 2026-08-13, measured in `docs/experiments/0005-gate-oracle-first-measurement.md`; the gate fails 0 of 6 on both halves, as AC-15 said it would, and now names why
  - [x] Tell generation which field each evidence chunk is, and instrument the additive split, then measure both in one set of runs (AC-12, AC-17, AC-18, AC-19) — built and run 2026-08-13, measured in `docs/experiments/0007-field-labels-and-the-additive-split.md`; generation now states decisions 24 of 24, the gate still fails 0 of 6, and the blocker moved to retrieval
  - [ ] Rewrite `verify.md`, run `/check verify` and `/test`, then calibrate the additive tolerance against the re-measured figure (AC-1 to AC-19)
  - [x] Two live `--runs 3` JobPilot batches; re-measure the rationale summary rather than assume its old bar (AC-2, AC-3, AC-9, AC-12)

**Re-measured on a clean instrument (2026-08-13, spec task 11):** spec tasks 9 to 11 are now shipped and green (540 unit tests). Removing both known contaminants did not move the drop rate: `docs/experiments/0004-clean-pipeline-re-measurement.md` records **19 of 21 draft sentences dropped and 0 queries of 12 answered**, with `not_additive` at **68 percent of drops (13 of 19)**. That is task 13's calibration target, now read from a clean pipeline rather than a starved one. Three things came out of the run. A third drop cause appeared that no calibration reaches: `unsupported_sub_claim` went 0 to 3 of 19 because sentences finally reach entailment, and the mechanism is **over** splitting into fragments too atomic to stay grounded (`The adapter warns.`), the opposite of the under splitting the spec's follow-up already tracks. A coverage defect was found and fixed: the provider returned a correct uncovered verdict while naming the sentence it had judged, which AC-12 rejects, so a correct abstention became a hard `provider.coverage` failure on 4 of 4 attempts; the coverage schema's `sentence_ids` property now carries a description telling the model to leave it empty when `covered` is false, with `validate_coverage` unchanged as the hard gate (0 of 3 rejected after). That was a deviation from spec 0010, **ratified 2026-08-13 as AC-17**, instance and pattern, bounded to a rule a named validator already enforces with `/check review` as the owner of the bound. And the gate's oracle is weaker than its purpose: in the run where the decision query answered, the sentence stating the decision was dropped and coverage accepted a caveat sentence in its place, matching the manifest's expected record and state while answering wrongly. **Settled 2026-08-13 as AC-15 and AC-16**: the oracle now requires a co-located `decision.chosen` citation from the covering sentence plus a named abstention cause, under a 6 of 6 bar over two batches whose answering half is provisional until calibration; the caveat that fooled it is stated to the coverage model, and its miss rate is counted as a fraction with its denominator so a structural zero cannot read as a clean result.

**The gate can now see a wrong answer (2026-08-13, spec tasks 16 and 15):** shipped and green (580 unit tests, ruff, format, strict mypy). The coverage model is told the directness exclusion, the manifest carries `expected_value_paths` and `expected_abstention` on every query, the loader refuses a key it does not recognize or an expectation the corpus cannot satisfy, and `evaluate --battery PATH` runs it with the corpus root taken from the manifest's parent. Measured over two `--runs 3` batches in `docs/experiments/0005-gate-oracle-first-measurement.md`: **both halves fail 0 of 6**, which AC-15 predicted, and both failures are now legible. The abstaining query abstains from `no_emitted_sentences` where its manifest pins `uncovered_facet`, and that run **reads PASS under the old state only oracle**: it is the vacuous abstention every experiment since 0002 had to catch by hand. The **AC-16 miss count is 0 over 0 covered runs**, and the zero denominator is a result rather than a gap: coverage was called in all 6 runs, the caveat sentence experiment 0004 caught reached it every time and was the only survivor in 2 of them, and the decision facet came back uncovered every time. The trigger cannot fire on 0 of 0, so the deterministic guard is not built and the instruction stands. Two limits on that number are recorded in the experiment: it is one query's behaviour rather than a general caveat miss rate, and it comes from 6 dedicated decision query runs against the same fixture store, since the report gives per fixture rates and the fraction needs coverage rows. One new signal for task 13: 11 sentences reached coverage across the 6 runs and none covered the facet, including one that reads as a direct answer, so the provisional answering bar is exposed to coverage directness as well as to sentence survival, and only the second is what calibration moves.

**Coverage refuses a correct answer, and it is not calibration (2026-08-13, experiment 0006):** `docs/experiments/0006-coverage-directness-isolation.md` tested whether AC-16's exclusion had over corrected and rejected that in both directions: removing the exclusion covered once in 6 runs, with the caveat sentence, which is the defect AC-16 closed. It found a fourth cause instead. **Across 6 runs, 11 sentences reached coverage and none covered the decision facet**, including one that reads as a direct, correct, well cited answer. The facet asks what was **decided** and the sentence says what the system **uses**, so coverage was applying the directness rule correctly while the rule was silent on the case. **Settled 2026-08-13 as AC-18 and AC-19.** The answer is no, the rule is pinned rather than relaxed, and the stage that changes is generation: every accepted chunk already knows its `value_path` and generation was the one stage never receiving it, so the model was asked what was decided from prose that never said it was a decision. Each evidence block now carries a plain words field label, never the dotted token, which would echo into a draft sentence as an unmatchable content token and drop it unconditionally. Coverage is untouched, so AC-16's caveat exclusion stays as measured. This blocks the AC-15 answering bar and calibration cannot move it, since survival was not the binding constraint, so it runs **before** the calibration task, which now begins by re-reading its own target: the additive knob reaches only function word overruns, the 68 percent has never been split, and the split is instrumented in the same task because no claim text is recorded and it cannot be recovered afterwards.

**Generation answers with a decision now, and the blocker moved one stage back (2026-08-13, spec task 17):** shipped and green (596 unit tests, ruff, format, strict mypy). Each generation evidence block carries a plain words `Field:` line, the evidence travels as `(chunk_id, value_path, text)` triples, `ANSWER_SYSTEM_PROMPT` asks a decision facet to be answered with the decision, and `sub_claim_is_additive_free` now reports why it stopped into a defaulted `additive_failure` category. Measured over two `--runs 3` batches in `docs/experiments/0007-field-labels-and-the-additive-split.md`, which also records the first cost figure for this gate: **$0.125 and 118 seconds for 12 runs**. Four results. **AC-18 worked on the stage it targeted**: 24 of 24 draft sentences are framed as a decision (`The decision was to use a hybrid retrieval system that combines...`), against the descriptions experiment 0006 recorded, so the mechanism OD-7 named is real. **The gate still fails 0 of 6 on both halves**, and the decision query now fails at entailment rather than coverage: its one sentence is dropped `unsupported_sub_claim` 6 of 6, on the single sub claim that states the decision, with the other three supported every time. **The cause is one stage earlier still**: no `decision.chosen` chunk is retrieved at all, in 8 accepted chunks over 6 runs; `DM-0008`'s ranks lexical 36 (outside top 24), semantic 10, fused 21, and is cut by the record cap and the top 8, so generation asserts a decision from a `body[2]` chunk and entailment correctly refuses. No criterion in spec 0010 reaches that, and it outranks calibration. **The `not_additive` split is 7 of 7 `content_token`, 0 `function_word_overrun`**, so the task 13 tolerance knob reaches 0 of these 18 drops; the spec's own amendment says that outcome reshapes or retires the task rather than failing it. The AC-16 miss count is 0 over 0 for the second time, and for a new reason: coverage judged nothing at all rather than judging and refusing.

**Superseded measurement (2026-08-12, decisions settled 2026-08-13):** spec tasks 5 to 8 are built and green (529 unit tests), and the feature does not yet work: `docs/experiments/0003-whole-sentence-gate-and-a-misdiagnosis.md` records 19 of 20 draft sentences dropped and 1 query of 12 answered. `not_additive` is 74 percent of drops, so the tolerance calibration (spec task 13) is the critical path and is larger than calibration implies. That figure was measured before the marker strip, so spec task 11 re-measures it first rather than calibrating against a starved pipeline. Inline `[ch_...]` markers are 16 percent and are now settled: they are stripped at the generation boundary under AC-13, which also revives AC-5, silently dead for every marker bearing sentence. The gate now reads a frozen fixture that holds spec 0010 out (AC-14), since the spec named its own gate's expected answer inside the corpus it queries.
- [ ] Verify it: `/check verify abstention verification reliability`
- [x] Test it: `/test abstention verification reliability`

**Measured (2026-08-12, spec task 11 run early, before the task 9 calibration):** the self corpus gate fails, and it names two separate causes. Every draft sentence is dropped as `decomposition_invalid` in both samples, so the "why" query abstains for the wrong reason again and the "what was decided" query cannot answer. First cause, `not_additive` on ordinary prose: the additive half is too strict against real decompositions, which is exactly what task 9 exists to calibrate, so this one is expected and scheduled. Second cause, `incomplete`, is **not a tolerance problem and no calibration reaches it**: the generator writes inline `[ch_...]` citation markers into the draft sentence text, `sentence_tokens` reads a chunk id as a parent content token, and no sub claim can ever match it, so any sentence carrying a marker fails the completeness half unconditionally. That needed a decision in spec 0010 (ignore marker tokens in the matcher, or strip markers at the generation boundary) before the tolerance could be calibrated against anything meaningful. Note also that spec 0010's own build plan then contained the gate's expected answer verbatim, so the gate only measures what it claims to when spec 0010 is held out of the corpus. **Both settled 2026-08-13:** the marker is stripped at the generation boundary (AC-13) and the gate reads a frozen fixture with spec 0010 excluded (AC-14). This note stays as the measurement that forced both.

### 18. Corpus gap and staleness awareness · needs a decision · from spec 0010
The tool cannot tell when it is answering from an incomplete or outdated corpus, and says nothing when it is. Two halves of one gap, both measured in `docs/experiments/`. First, `adapt` reports the records it skipped and that signal dies there: nothing carries it to query time, so an answer drawn from a knowingly incomplete corpus looks identical to one drawn from a complete corpus. Second, the adapter never populates `supersedes`, so even a complete corpus cannot mark a decision as later reversed. Experiment 0001 recorded the cost: with spec 0008 skipped for a malformed status line, the tool answered a question about hybrid retrieval fluently and with a correct citation, and inverted a decision that had already shipped. Nothing was fabricated; the pipeline behaved correctly on the evidence it had.
**Done when:** a query answered from a corpus with known skipped records says so, and a query whose evidence is superseded either says so or declines, with the behaviour proven against a deliberately incomplete corpus.
**Needs a decision on:** where the signal lives (the manifest, the store, or the query result), whether it warns or blocks, and whether `supersedes` is populated by the adapter or resolved at query time.
**Carried from:** spec 0010 Follow-up, experiments 0001 (finding F4) and 0002. Not a verification defect, so deliberately kept out of feature 16.
- [ ] Design it (spec): `/architect corpus gap and staleness awareness`

## Slice 4: Presentation

Runs after Slice 2 and Slice 3, and before V2. The number 15 is only the next free ordinal, it is not a claim that this comes after everything else. Ordering against Feature 8 (built-in ADR adapters) is irrelevant, the two do not touch the same surface, and Feature 8 keeps its own sequencing (a `doctor` survey of real corpora first).

### 15. CLI presentation redesign · needs a decision
Restyle the human facing output of the CLI to one defined visual language: a teal accent, aligned reports at 80 columns, status markers that carry both a shape and a word so meaning survives without color, a single line summary paired with the exit code, and a consistent error then hint then exit grammar. The visual target is an external design (opendesign), corrected against what the CLI really prints today.
**Done when:** every one of the 7 commands (`version`, `validate`, `doctor`, `adapt`, `test-adapter`, `ingest`, `query`) prints in the new language, including its failure paths, and the whole surface stays untouched underneath: same commands, same flags, same exit codes, same JSON output, same DTOs, same backends.
**Scope guardrails (carry into the spec):** presentation only. No new command, no new or renamed flag, no changed exit code, no changed DTO field, no retrieval or storage change. The change lives in `src/decision_memory/cli.py` plus one new rendering module; machine readable output (`--json` and friends) stays byte stable, since scripts depend on it.
**Why it waits for Features 10, 11, and now 16:** Feature 10 (reliable multi source retrieval) rewrites what `query --debug` traces, since filtering and lexical stages add candidate sets and scores the current trace has no shape for. Styling today's trace first means styling it twice. Feature 11 (the evaluation harness) is the other output producer whose report shape is not settled yet. Feature 16 (abstention verification reliability) is a fix to the same verification layer the debug trace exposes, so it can reshape that output the same way Feature 10 did; build the visual language once, over output that has stopped moving.
- [ ] Design it (spec): `/architect CLI presentation redesign`

## V2

V2 theme: usable on more corpora, used more often. These are hypotheses formed before v1 has real usage, so they may be reordered or replaced once v1 evidence exists. Nothing in V2 starts before the evaluation harness passes.

### 12. Flat single file spec support · needs a decision
Extend adapter coverage to flat `NNNN-title.md` specs, the shape the existing directory adapter never touched and the current validation corpus still misses.
**Done when:** the adapter reads the flat spec files already present in the corpus, resolves the `DM-0019` duplicate with a deliberate id strategy, and produces valid records or clear skips without weakening the existing directory spec behavior.
- [ ] Design it (spec): `/architect flat single file spec support`

### 13. Declarative adapters · needs a decision
Let common decision formats implement the `SourceAdapter` protocol from a YAML mapping file instead of Python, while keeping stub detection, warn never invent behavior, evidence resolution, and attempted fields as engine owned guarantees. Flat single file support derisks this by giving the config schema a second real adapter to compare against, but it is not a hard unlock if a different useful second adapter appears first.
**Done when:** after at least two hand written adapters exist, a config driven adapter can map a simple real corpus into valid canonical records, malformed configs fail clearly, and formats needing branching logic are pointed back to a Python adapter rather than guessed.
- [ ] Design it (spec): `/architect declarative adapters`

### 14. MCP server interface · needs a decision
Expose the query function as an MCP tool inside a coding agent, where day to day decision memory is most likely to be used.
**Done when:** an agent can ask the project why a decision was made and receive the same cited answer or honest no evidence response as the CLI, through a small MCP surface.
- [ ] Design it (spec): `/architect MCP server interface`

## Deferred
Out of scope for the current build pass, kept so the plan stays honest.
- **Coverage direction (query 2 citation completeness)**: query 2's `DM-0004` citation is intermittent because generation is not required to cite every accepted chunk that directly answers a facet, while `DM-0019` is. Deliberately kept out of spec 0010 so the fabrication direction ships as one measurable change. Needs a decision on a stricter generation contract or a citation completeness verification stage · needs a decision
- **Capture**: interview based record creation for projects with no existing decision shaped artifacts · needs a decision
- **Capture revisit trigger**: revisit capture after the tool has been used on three projects that lack decision shaped artifacts and the need is demonstrated.
- **Web UI**: a frontend over a thin HTTP layer on the core · needs a decision
- **History reconstruction**: recovering decisions from a codebase that never recorded them
- **Multi project or cross repo querying**
- **Auto generating records without human review**
- **Adapter accessibility sequencing**: `doctor`, then real corpus survey using `doctor`, then the importlib part of runtime loading, then `test-adapter`, then built-in adapters, then the `.decision-memory.yml` config and starter template remainder of runtime loading. Core retrieval can proceed in parallel.
- **Retrieval quality at scale**: the 15 record validation corpus proves the pipeline runs end to end, it does not prove that hybrid retrieval beats semantic only. Establish a corpus large enough to tell the two apart before treating retrieval as settled. No target size is set here, because no evidence supports a specific number yet. Recorded so an accepted v1 limitation stays visible in the plan and is not later mistaken for a validated result
- **Corpus backfill from git history**: padding the JobPilot corpus from commit history if it proves too thin to evaluate hybrid versus semantic only retrieval; a conscious later choice, not assumed now
- **Corpus scoped record ids** (from spec 0003): `DM-<number>` is constant, not derived from the corpus, so a second project collides. Settle this before multi project querying starts, since changing ids later invalidates stored citations and embeddings
- **Recalibrate the code path shape test** (from spec 0003): the rule deciding which unresolved mentions are worth counting is tuned to one corpus's backtick habits and is already on its third calibration. A corpus that quotes prose containing slashes, or names files with no extension, will read differently. Retune when a second corpus exists, and record what changed
- **Hooks for declarative adapters**: a later escape hatch where a YAML mapping names a small Python function for one field. Do not scope this until real declarative adapters show which escapes repeat; repeated hook patterns should become config vocabulary instead.
- **Code reviews as a record source**: the validation corpus also has `docs/reviews/`. Code reviews hold recommendations, not decisions, so ingesting them as records would put "someone suggested X" into a corpus that answers "we decided X." The revisit question is rationale discoverability across linked artifacts: a spec may record that a decision changed after review while the reasoning that made the change necessary lives only in the review. A user asking "why Option B?" gets the spec's thinner summary. That is a completeness gap, not a correctness one.
- **Enforce no expected answers in spec prose** (from spec 0010 AC-14): holding spec 0010 out of its own gate fixes one gate; the rule that stops the next spec contaminating a different gate is discipline only, and nothing checks it. A cheap lint over `docs/specs/` for the gate manifest's query and answer strings would close it. Not scoped now because one gate does not justify the machinery; revisit when a second gate exists.
- **Fixture re baselining trigger** (from spec 0010 AC-14): the frozen self corpus fixture goes stale by design and only a deliberate regeneration surfaces the drift through its manifest hashes. What should prompt one (a spec count change, a release, or nothing at all) is left open until the gate has run enough times for the staleness cost to be observed rather than guessed.
- **Vacuous abstention on the live gates** (from spec 0010 AC-15): the self corpus gate now names the abstention cause it expects, so an abstention caused by every sentence being dropped stops counting as the behaviour being gated. The JobPilot abstention gates still pass on `expected_state` alone, and experiment 0002 already recorded query 5 abstaining 6 of 6 as an artifact of wholesale rejection rather than a verdict. `expected_abstention` is built as an optional `QueryOracle` field precisely so it can be applied to query 5, the unverifiable claim assertion, and query 4, and it is deliberately not applied there yet so feature 16 changes one measurable thing at a time. Revisit after the live batches report.
- **Embedding prefix onto the plain words field mapping** (from spec 0011): the two retrievers deliberately read different documents, the semantic side the dotted `value_path` and the lexical side the plain words label. Moving both onto one mapping is the cleaner invariant and the only thing making it a bad trade today is the forced rebuild: `prefix_version` is hashed into `pipeline_signature`, so changing it locks every existing store out until rebuilt and makes the experiment 0004 to 0007 baselines incomparable. Bound to a condition rather than left open: land it with the next pipeline signature bump that happens for an independent reason, when the rebuild is already being paid for.
- **Verify records**: review separately from code reviews even though they also live in the validation corpus. They are the same genre as the `verify.md` files already excluded from contributing files: procedural acceptance criteria evidence, not decision content. They stay excluded for that reason, not because they are recommendations.

## Legend

**The decision box.** Every feature carries at most one, the sub task whose label ends with `(spec)`. Its wording varies (`Design it (spec)` normally, `Decide the stack (spec)` on Stack & architecture), so skills locate it by that `(spec)` suffix, never by an exact label. Every other box is an execution box and `/architect` never ticks one.

**Feature lifecycle**: the scope updates as a feature moves; each row is what it shows and who sets it:

| State | Set by | The feature shows |
|---|---|---|
| `planned` · needs a decision | `/scope` | one box: `Design it (spec): /architect <feature>` |
| `in-progress` (designed) | `/architect` at spec capture | `Design it` ticked; spec linked; `Build it: /develop <feature>` plus 2 to 5 milestones; the tier's closing boxes (`Verify it` at Alpha and above, `Test it` at Beta and above, `Review it` plus `Document it` at GA); any surfaced follow up enrolled |
| `in-progress` (building) | `/develop` | milestone sub boxes tick one by one; code pointer filled |
| `in-progress` (verified) | `/check verify` | `Build it` plus milestones ticked; `Verify it` ticked |
| `done` | you, when you decide it is (any skill sets it when you say so); `/sync` reconciles | the boxes you ran are ticked, the ones you skipped are recorded as skipped; the tier's last stage (Prototype after `/develop`, Alpha after `/check verify`, Beta or GA after `/test`) is the suggested point to call it done, never a gate; `/sync` captures conventions |

- **Next step** = the first unticked box (always a command or a tracked milestone).
- **needs a decision** = run `/architect` first; otherwise straight to `/develop` (or `/audit` for standards and tooling). The tag drops once the spec is captured.
- **Atomic build tasks live in the spec's `## Build plan`, not here**: the scope carries only the milestone rollup.
- **Status** `planned` then `in-progress` then `done`, plus `existing` (pre workflow) and `dropped` (de scoped, kept for history).
- **Approach tag** beside a heading overrides the project default for that feature; no tag means it inherits.
- **Workflow tier tag** beside a heading (for example `· GA`, `· Prototype`) overrides the project default `**Workflow:**` tier for that one feature; no tag means it inherits. The effective tier (tag if set, else default) is the recommended verification depth; every skill reads it the same way to suggest the next step and shape the closing boxes. Those boxes are suggestions you run or skip; skipping never blocks `done`.
- **Workflow** (header line) is the project default tier, the stages each feature suggests running after `/develop`: Prototype means nothing beyond `/develop`'s own build time self check; Alpha means `/check verify`; Beta means `/check verify` then `/test`; GA adds a fresh model `/check review` then `/document`. `done` is your call, not gated on these; a skipped stage is recorded as skipped. An Assumed spec is flagged on the feature (its decision still owes ratification) but does not block you from marking `done`; `/architect` still records any load bearing decision, the one thing the workflow asks. A feature's own tier tag overrides the default.
- **Pointer line** (`spec <n> · code in <path>`): the spec link added by `/architect`, the code path by `/develop`.
