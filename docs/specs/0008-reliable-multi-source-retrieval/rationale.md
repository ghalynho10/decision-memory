# Rationale: reliable multi source retrieval

## Context

> ⚠️ Premise note: The 15 record JobPilot corpus cannot establish that hybrid retrieval is better at scale, and one defining question asks about evidence the adapter does not ingest. This feature proves deterministic multi source behavior, complete diagnostics, and honest abstention. It does not claim general retrieval superiority.

Spec 0007 ships one semantic retrieval path. Chroma returns up to 24 candidates, the application accepts eight, and the relevance floor is deliberately disabled. The trace can explain semantic rank and claim verification, but it cannot show whether an exact term would have recovered a missed record, whether an explicit constraint excluded it, or whether one record crowded several relevant records out of the final context.

The current store already has the required metadata in SQLite: record ids, status, tags, value paths, and chunk text. The corpus is small enough to score every accepted chunk with BM25 in memory. The design must keep SQLite authoritative, keep third party libraries out of application code, and preserve the existing read only query boundary and full shared lock.

The JobPilot corpus exposes two different correctness cases. Query 2 has direct evidence across `DM-0004` and `DM-0019`. Query 4 does not have answer evidence in adapted decision records. Its relevant text lives in `context/library-docs.md` and `context/code-standards.md`, outside the adapter's deliberate `docs/specs/` boundary. A cited answer is therefore impossible by construction. Changing the corpus or replacing the question would hide that fact.

## Oracle correction (2026-08-11)

The original AC-13 named `DM-0014` as a third cited record for the projects exclusion claim. `DM-0014` is `0014-optional-projects-capture-in-resume-extraction.md`, a flat single file spec that the built in adapter does not ingest (flat single file support is Feature 12, deferred). The projects exclusion claim actually lives in `DM-0019` (its AC-9), which is indexed and cited. The oracle was corrected in place to cite `DM-0004` and `DM-0019`, with each remaining claim mapped to the record now carrying it and the multi record property confirmed to hold across two records. This makes query 2 the second defining query whose evidence sits partly outside the adapted corpus (query 4 was known, query 2 partially was not). Feature 11's harness should surface this class of gap rather than have it rediscovered mid build.

## Query 4 verification finding (2026-08-11)

AC-14's premise is confirmed correct: the server side and browser side database client decision lives in `context/library-docs.md` ("Never use browser client in server context / never use server client in browser context"), which the adapter does not ingest. However, against the rebuilt index the exact query 4 answered five of five runs with a fabricated citation to `DM-0002` (profile save logic), which mentions server, client, and browser but records no such decision. The fabrication passes claim verification: the deterministic containment check fails, but the model entailment verdict accepts adjacent evidence ("the server route is a security boundary", "reading one scoped row on the server is simpler") as supporting the invented claim, and coverage passes. This is the claim verification weakness already observed in Feature 9, and under hybrid retrieval it is reliable rather than intermittent. The relevance floor, which would abstain at retrieval on weak evidence, remains `None` pending Feature 11 calibration. Feature 10 cannot be marked done until query 4 abstains per AC-15; the fix belongs to claim verification strictness (Feature 9 territory) or the Feature 11 relevance floor.

The verification layer also has observed intermittent abstentions on supported questions and one unsupported answer on an unrelated question. Hybrid breadth is not allowed to make that grounding problem quieter. Unsupported cited output from either live oracle blocks this feature, while Feature 11 remains responsible for the reusable harness and measured calibration.

## Options considered

### Option 1: Fix the query path with parallel retrieval and rank fusion

Apply explicit metadata constraints, run BM25 and Chroma over the accepted chunks, sort every eligible semantic distance locally, combine the top ranks with reciprocal rank fusion, then apply record diversity before the existing generation path. (basis: specs 0001 and 0007; reciprocal rank fusion; SQLite authority)

**Pros**:

1. Neither retriever limits the other's recall.
2. Rank fusion avoids an invented comparison between BM25 and cosine scales.
3. Fetching every eligible vector makes the top 24 boundary deterministic under tied distances.
4. One execution path keeps failure and trace behavior consistent.

**Cons**:

1. Query work and trace volume grow linearly with eligible chunks.
2. A store format rebuild is required to enforce exact chunk eligibility in Chroma.

### Option 2: Run old and new retrieval paths side by side

Keep semantic retrieval as version `1`, add hybrid retrieval as version `2`, and compare or select them with a feature flag. (basis: strangler pattern for live migrations)

**Pros**:

1. Rollback is immediate.
2. Both paths could be compared on identical questions.

**Cons**:

1. The local derived index has no public clients or live service rollout that justifies two paths.
2. Dual DTOs, traces, failure rules, and tests would preserve the old path indefinitely.
3. The small corpus cannot support a meaningful quality comparison yet.

### Option 3: Normalize raw scores and use a weighted sum

Convert BM25 and cosine results to a shared range, choose a weight for each, and sort by the combined value. (basis: weighted hybrid ranking)

**Pros**:

1. Weights can express a preference for exact terms or semantic meaning.
2. Raw score gaps can influence ranking.

**Cons**:

1. The normalization method and weights would be unmeasured policy.
2. Score distributions change with each question and corpus, so simple range normalization is unstable.

### Option 4: Use one retriever as a candidate gate and the other as a reranker

Run lexical then semantic, or semantic then lexical, over one narrowed candidate set. (basis: cascade retrieval)

**Pros**:

1. The second retriever processes fewer chunks.
2. Stage order is simple to explain.

**Cons**:

1. The first retriever becomes a hard recall ceiling.
2. A fact found only by the second retriever can never enter fusion.
3. Conditional fallback would add an unmeasured definition of when the first result looks weak.

## Rationale

Option 1 is the smallest direct improvement to the live query path. SQLite already carries the filter facts and chunk text, while Chroma already carries the vectors. BM25 adds one local scorer, not another store. Reciprocal rank fusion uses rank position because raw BM25 values and cosine similarity have no shared meaning. Constant `60` follows the conventional RRF starting point and stays provisional for Feature 11. (basis: spec 0001; reciprocal rank fusion; measure before tuning)

Chroma is deliberately not trusted to choose the semantic top 24. A limited query can return an arbitrary subset when more candidates share the boundary distance. Format `2` pins cosine distance, fetches one vector result for every accepted id, and lets application sort by distance then chunk id before cutting locally. This makes `similarity = 1 - distance` sound and makes repeated runs stable at tied boundaries. The small corpus makes the linear result set acceptable. (basis: deterministic ordering discipline; current corpus scale)

The lexical contract is equally explicit. Token intersection decides `no_term_match` before score sign is considered, so zero score states cannot overlap. The tokenizer and its 171 word effective vocabulary are versioned and digested rather than delegated to an ambient language package. Decision relevant negation remains searchable. (basis: spec 0001 tokenizer direction; reproducible traces)

Explicit filters remain constraints, not a natural language query planner. A model rewrite before retrieval would place an unattributable guess upstream of both retrievers. Date ranges and graph traversal also need semantics that current evidence does not justify. The original question therefore reaches both retrievers unchanged, and facet extraction stays after retrieval. (basis: spec 0007; explicit over inferred behavior)

The two pass diversity rule intentionally completes a decision deferred by spec 0007. Two chunks per record in the breadth pass gives query 2 room for three records. The fill pass avoids a hard cap and can still accept a strong third chunk from one record. Keeping breadth and final dispositions separately makes the effect machine checkable. (basis: spec 0007, Feature 10 boundary; complete query traces)

Option 2 would normally be attractive for a live service migration. Here the index is local, derived, explicitly rebuildable, and has no public compatibility consumer. A direct store format cutover is safer than maintaining two retrieval meanings. Canonical records, manifests, chunk text, and embedding inputs remain untouched, but rebuild recomputes vectors and repeats provider spend. Rollback is therefore a code revert plus another rebuild rather than a data recovery operation. (basis: spec 0007 rebuild contract; direct replacement of rebuildable derived data)

Query 4 remains in the acceptance set because its abstention records a real system boundary. Expanding the adapter to selected context files would change what a decision record means to fit a test. Replacing the query would erase the discovery. The terminal abstention stage is not fixed because the relevance floor remains `None`; pinning retrieval or claim verification now would encode an unmeasured cutoff. (basis: specs 0003 and 0007; honest untested dispositions)

Five consecutive passes per query are a smoke gate against an already observed intermittent pattern. They do not estimate a failure rate. The settings trace records every provisional constant so Feature 11 can attribute later changes without invalidating unchanged embeddings. (basis: docs/session-notes.md; reproducible evaluation)

## Evidence from the validation corpus

Query 2 has three required direct sources:

1. `DM-0004` Summary, Decision, AC-4, and the API design confirm on demand generation from the caller's saved profile, storage of the new PDF, and update of `profiles.resume_pdf_url`.
2. `DM-0014` AC-7 and its key invariants explicitly require resume generation to remain untouched and exclude projects from the generated resume.
3. `DM-0019` adds ATS quality guidance and deterministic checks for unsupported numeric claims and em dash output.

Query 4 has no direct source under JobPilot `docs/specs/`. The relevant browser and server client rules occur in `context/library-docs.md` and `context/code-standards.md`. Those files are outside the built in adapter's discovery boundary. This is an expected abstention, not a retrieval miss.

Feature 11 therefore has two expected abstentions among its five defining questions: query 4 because the evidence is outside the adapted corpus, and query 5 because the required supersession evidence is not mapped.

## References

**Project sources**:

1. `AGENTS.md`, Clean Architecture, strict typing, test separation, and the Skateboard build approach.
2. `docs/specs/0001-stack-and-architecture.md`, the selected BM25 dependency, tokenizer direction, Chroma and SQLite roles, corpus scale, and provisional retrieval limits.
3. `docs/specs/0002-canonical-decision-record-schema.md`, canonical value paths and exact field identity.
4. `docs/specs/0003-jsmastery-specs-adapter/`, the `docs/specs/` corpus boundary and honest untested dispositions.
5. `docs/specs/0006-adapter-conformance-test-adapter/`, stable closed rule vocabularies.
6. `docs/specs/0007-core-cited-query/`, semantic retrieval, disabled relevance floor, trace contract, diversity deferral, rebuild behavior, and claim verification boundary.
7. `docs/session-notes.md`, observed verification instability and unsupported answer evidence.
8. JobPilot `docs/specs/0004-resume-pdf-generation-from-profile/`, `docs/specs/0014-optional-projects-capture-in-resume-extraction.md`, and `docs/specs/0019-resume-generation-quality/`, the query 2 oracle.
9. JobPilot `context/library-docs.md` and `context/code-standards.md`, the excluded query 4 evidence.

**Practices and standards**:

1. Reciprocal rank fusion for combining rankings without raw score normalization.
2. BM25 Okapi for local lexical retrieval.
3. Snowball English stopword vocabulary with decision relevant negation retained.
4. SQLite as authoritative data and Chroma as a derived vector index.
5. `lexical-stopwords-v1.txt`, the normative 171 word effective vocabulary and digest input.
6. Measure before tuning provisional ranking constants.
7. Rebuild derived data instead of maintaining compatibility paths with no consumer.
