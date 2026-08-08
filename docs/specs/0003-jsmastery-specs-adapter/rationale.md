# Rationale for 0003. jsmastery specs adapter

## Context

> ⚠️ Premise note: the chosen id scheme, `DM-<number>`, is constant rather than derived from the corpus, so two projects ingested into one index both produce `DM-0001`. Multi project querying is on the deferred list rather than out of scope, and ids are exactly what citations and stored embeddings point at, so resolving this later means rewriting every stored citation rather than adding a field. The corpus derived alternative was offered and declined on the grounds that a corpus directory name is itself unstable, which is a fair objection. Proceeding as chosen, with a Follow-up item to settle a corpus scoped scheme before multi project querying starts, not after.

This project answers why a codebase is built the way it is, with citations back to source. Everything downstream of ingestion depends on records that faithfully represent real decisions, so the component that converts other people's documents into canonical records is where the whole chain's trustworthiness is set. A mapping that guesses produces a record that reads as authoritative and is wrong, which is worse than producing nothing.

Feature 3 fixed the canonical record shape and the rules that validate it (`docs/specs/0002-canonical-decision-record-schema.md`). It deliberately left `attempted_fields` empty and noted that this feature is what fills it. So the schema exists and the validator exists; what is missing is anything that produces a record from a real source.

The corpus this must work against is a real project's `docs/specs/`, and reading it changed several assumptions the scope row carried. The scope row describes sources as `docs/specs/<n> <name>/index.md`; the real naming is `NNNN-kebab-title/` with no spaces. It anticipates one shape; the corpus holds two, fifteen directory specs and five flat single files. It assumes the degradation cases are about missing fields; the harder cases turn out to be structural, with the same section appearing in two files, sections that are pointers rather than content, and two incompatible ways of laying out the options that were weighed. The full inventory is below, under `## Corpus evidence`.

There is also a constraint the source imposes and this project cannot change: the corpus is another repository, maintained by someone else, for its own purposes. It will keep drifting, it was never written to be machine read, and it contains things nobody anticipated. Any design that requires the corpus to be correct before it can be ingested is a design that does not work.

The cost of not deciding is that feature 5 has nothing to ingest. Every retrieval slice, and the evaluation harness that proves the whole thing works, waits on real records existing.

## Options considered

### Option 1: Section driven mapping behind a source adapter protocol

A `SourceAdapter` protocol in the application layer declares `discover`, `parse`, and `fingerprint`; a jsmastery implementation in infrastructure knows this format's section names and fills canonical fields from them, with explicit precedence and fallback rules where a section appears twice (basis: `AGENTS.md`, the dependency rule that infrastructure implements interfaces from application).

**Pros**:
- Mapping rules are explicit and readable, so a wrong record traces to one named rule rather than to a scoring function
- Feature 5 depends on the protocol, so a second source format needs no change to ingestion (basis: PEP 544, structural subtyping)
- The application layer stays testable with a fake adapter and no filesystem

**Cons**:
- The protocol has exactly one implementation today, so part of it is structure bought before it is needed
- Every mapping rule is tuned to one project's habits, and a differently written corpus needs new rules rather than new configuration

### Option 2: A concrete jsmastery module in infrastructure, no protocol

The same mapping, exposed as plain functions, with no interface. Feature 5 imports the module directly.

**Pros**:
- The least code, and truest to shipping the smallest usable whole
- Nothing speculative: an interface with one implementation is an assumption about a second one

**Cons**:
- Ingestion in feature 5 binds to a concrete infrastructure module, which the architecture rules do not allow the application layer to do
- Extracting the interface later means editing ingestion, which is the slice most expensive to disturb

### Option 3: A generic markdown mapper with no per format knowledge

Instead of naming this format's sections, infer canonical fields from any markdown decision document by matching heading names loosely and scoring content.

**Pros**:
- Works against a second and third corpus with no new code, which is where this project eventually has to go
- No mapping table to maintain as the source drifts

**Cons**:
- It fabricates by construction: a loose match is a guess, and the one rule this feature cannot break is never inventing a field
- Failures are unattributable, since a wrong record traces to a score rather than to a rule, which makes it undebuggable against a corpus that keeps changing
- The corpus evidence shows the hard cases are structural, not lexical; no amount of heading matching resolves a section that appears in two files, or options laid out in two incompatible shapes

## Rationale

Option 1 is chosen because the governing constraint from Context is that the source is not trustworthy and cannot be made trustworthy. Every hard case the corpus actually presents is one where the adapter must decide between two candidate sources or recognise that a section is not content at all, and both are decisions someone will need to read, argue with, and change. Explicit rules can be argued with; a scoring function cannot, which is what rules out Option 3 despite it being the only option that generalises for free. The generalisation it offers is also the wrong shape: it buys reach across formats at the cost of the one property this component exists to have.

Option 2 is the honest minimalist reading, and on a different feature it would win. It loses here on a specific ordering fact rather than on principle: feature 5 is the next slice, it consumes this adapter directly, and it is the slice where a boundary change is most expensive. Paying a small amount of structure now, while there is nothing to disturb, is cheaper than extracting an interface out from under ingestion later.

Three of the detailed rules exist specifically to stop a plausible looking wrong answer, which is the failure mode that matters most for a tool whose output is citations. Stub detection exists so that a fallback does not fill `decision.alternatives` with the string `See rationale.md`, which would validate cleanly and be entirely false. The winner ladder ends in flagging rather than in a guess, because emitting every option as a rejected alternative would assert that the chosen option was rejected. And `context.triggering_change` is left unflagged rather than reported as attempted, because a warning that fires on every record in the corpus trains the reader to ignore warnings, which costs more than the missing field.

The engineer's preference shaped two decisions against the recommendation made at the time, and both are recorded here as deliberate. Evidence includes code paths mentioned in prose, not only the source files, which is richer but rests on extraction heuristics; the extraction rule was tightened considerably in response, and unresolved mentions are counted rather than silently dropped. And `body` holds only the sections no field consumed, rather than both files verbatim, which avoids storing the same prose twice at the cost of a chunk sometimes losing the framing of the section it came from.

## Corpus evidence

Gathered by reading `docs/specs/` of the validation corpus (`github.com/ghalynho10/job_pilot`) on 2026-08-08. Every mapping rule in `index.md` traces to something here.

**Shapes**: 20 sources, 15 directory specs and 5 flat single files. Directory specs hold `index.md` plus `rationale.md`, and 14 of 15 also hold `verify.md`. Flat files are out of scope this slice.

**Naming**: `NNNN-kebab-title/`, not the `<n> <name>/` the scope row describes. `0019-resume-generation-quality` exists as both a directory and a flat file, producing an identical slug and therefore a genuine id collision once flat files are read.

**Status distribution**, directory specs only: 14 `Accepted`, 1 `In Progress`. Across the 5 flat files: 2 `Accepted`, 1 `Done`, 1 `In Progress`, 1 `Proposed`. So `Done` and `Proposed` do not occur in anything this slice reads, and their mapping rows are forward cover for the flat file slice rather than a description of the current corpus.

**Sections in `index.md`**, by count across the 15 directory specs: `Summary` 15, `Requirements` 15, `Feature design` 15, `Decision` 15, `Consequences` 15, `Build plan` 15, `Rationale` 14, `Follow-up` 14, `Options considered` 2, `Context` 2.

**Sections in `rationale.md`**: `Rationale` 15, `Options considered` 15, `Context` 15, `References` 5, plus irregular one off sections including `Cross check (a different model, read only) and the fixes it prompted`, three dated revision sections, and three variants of `Evidence`. These irregulars are why the body is defined as residue rather than as a list of known sections.

**The duplicated sections**: `## Context` and `## Options considered` both appear in `index.md` only for 0005 and 0007. Their `## Options considered` is a stub in both cases (``See `rationale.md`.`` and `See [rationale.md](rationale.md).`), while their `## Context` is substantial real content, 0005's running to several paragraphs. That split is exactly why stub detection is a general rule applied at fallback time rather than a special case for one section.

**Options layout**: only 0009 (3 panels) and 0012 (4 panels) use the `### Panel N:` shape with `**Option A —**` entries inside. The other 13 use `### Option N:` directly. The scope row's degradation policy anticipated the panel shape, which is the minority by a wide margin.

**Chosen option markers**: only 5 of 43 `### Option N` headings across all directory specs carry any marker, and they are not consistent; 0006 uses `(recommended)` where 0013 uses `(chosen)`. So a heading marker cannot identify the winner for a plain option spec. The `**Chosen option**` line in `index.md` can, but not uniformly: 0001, 0011, and 0013 carry the `Option N:` ordinal, while 0006 gives the title alone with the heading's `(recommended)` suffix absent. Both forms are covered by the ladder, in that order.

Panel entries are different and better behaved: every panel in 0009 and 0012 marks its winner inline, as in `**Option A — Synchronous request/response (chosen)**`, so a panel unit carries two independent signals, the marker and its own `**Decision**` line. That redundancy is why ladder step 4 survives despite doing nothing for plain option specs.

**A trap in the panel decision lines**: 0012's Panel 3 reads `**Decision**: Option B, revised after a cross check review on 2026-08-01. Option A was chosen first, on the argument that ...`. Two option letters appear in one decision sentence, and the loser is discussed at length. Any rule that scans the sentence rather than taking the token immediately after `**Decision**:` picks the wrong winner, and would then emit the real winner as a rejected alternative. This single line is why the extraction rule is stated so narrowly.

**Nothing in this corpus can fail validation**: every field whose absence would produce an error is present in all 15 directory specs. A digit leading directory name 15, an H1 title 15, `**Date**` 15, `## Decision` 15, a `**Chosen option**` line 15, and `## Rationale` in `rationale.md` 15. Evidence is non empty by construction. So the invalid record path and the exit `1` branch are unreachable from real sources and need synthetic fixtures, which `index.md` states at both acceptance criteria rather than leaving a reader to assume the first real run will cover them.

**`why` bullets**: the `## Rationale` section contains a bullet list in exactly 1 of the 15 directory specs (0006, two bullets). The other 14 are prose only. So `rationale_summary` carries essentially the whole rationale across this corpus and `why` is close to vestigial, which is recorded in Consequences rather than papered over.

**What the unresolved mention count did in reality, and the third calibration**: the counting rule was written, shipped, and then measured against this repository's own `docs/specs/`, which is the honest test the first two calibrations never got. Adapting spec 0003 reported 4,999 counted mentions, about 1,515 of them distinct. The cause is not a bug in resolution; it is that backticks in this corpus mark prose at least as often as they mark paths. This project writes `` `read only` `` and quotes whole sentences in single backticks, so splitting every span on whitespace turns ordinary words into path candidates that predictably fail to resolve. A warning reading "4,999 unresolved mentions" cannot be acted on, which defeats what **AC-6** existed for.

The shape test in step 7 is therefore the third calibration of this rule, and the history is worth stating plainly so the next person reads it as tuning rather than principle. The first was too narrow: an identifier heuristic that would have dropped real evidence such as `proxy.ts`, `AGENTS.md`, and every directory reference, which is why the original spec chose existence as the disambiguator and said so explicitly. The second, the shipped one, moved all the way to the other end and counted anything that failed to resolve, which is how 4,999 happened. The third narrows the count without touching extraction.

Measured on spec 0003 before and after, the four resolved evidence paths (`.`, `AGENTS.md`, `docs/specs`, `tests`) are unchanged and the count falls from 4,999 occurrences to 34, or from 1,515 distinct tokens to 7. Both pairs are stated because `unresolved_mention_count` reports occurrences, so 34 is the number a person actually sees in the warning; the distinct figures are the better measure of how much there is to read. Two variants were rejected against that measurement. Putting the shape test upstream in extraction, which reads as the simpler single filter, drops `tests` and the `` `lib/` `` case the acceptance criteria already pin, reproducing the first calibration's failure in milder form. Accepting any one to six characters after a dot as a file extension keeps `decision.chosen` in the count, because this spec's own vocabulary is full of dotted field names such as `consequences.negative`; a known extension list removes that class at the cost of being a list someone maintains.

The general lesson, and the reason this is recorded rather than quietly fixed: a heuristic tuned against fixtures written by the person who wrote the heuristic will look right and be wrong. Both earlier calibrations passed their tests. Only running the adapter against real prose that nobody wrote for the adapter exposed the problem (basis: this repository's own `docs/specs/`, adapted with the shipped adapter).

## References

**Project sources** (verifiable, in this repo):
- `docs/specs/0002-canonical-decision-record-schema.md`: the canonical record shape, the rule id vocabulary, the exit code convention, and the case sensitive path rule this feature preserves
- `docs/specs/0001-stack-and-architecture.md`: the stack this builds on, and the layer list
- `AGENTS.md`: Clean Architecture rules, no framework code in domain or application, strict typing
- `docs/scope/scope.md`: feature 4's intent, its degradation policy, and the named validation corpus
- The validation corpus itself, read directly; see `## Corpus evidence`

**Practices & standards**:
- Structural subtyping for a boundary with one implementation today and more expected
- Content addressed fingerprints for incremental work, versioned so a change in the producer invalidates prior output
- Fail soft on untrusted input: skip and report the individual source, never abort the run

**Links** (web verified):
- Python `hashlib`, `sha256` and incremental `update()`: https://docs.python.org/3/library/hashlib.html
- PEP 544, Protocols and structural subtyping: https://peps.python.org/pep-0544/
