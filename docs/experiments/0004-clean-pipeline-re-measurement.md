# Experiment 0004: the gate on a clean instrument, re measured

**Date**: 2026-08-13
**Status**: Complete
**Follows**: [Experiment 0003](0003-whole-sentence-gate-and-a-misdiagnosis.md)
**Result**: The two causes experiment 0003 could not separate are now removed, and the drop rate barely moved: 19 of 21 draft sentences still dropped, 0 of 12 queries answered. `not_additive` is 68 percent of drops. The gate still fails. A third cause surfaced that no calibration reaches, and a coverage defect was found and fixed on the way in.

## What changed under the measurement

Experiment 0003 measured a starved pipeline and said so. Two causes were named there and both are now gone, which is what makes this run readable:

- **Inline chunk id markers** are stripped at the generation boundary (spec 0010 AC-13, shipped in `630e8d8`). Confirmed live: no `ch_` marker reached `DraftSentence.text` in any of the 12 transcripts.
- **The contaminated corpus** is replaced by the frozen fixture with spec 0010 held out (AC-14, shipped in `374c269`). The gate reads `docs/experiments/data/self-corpus-fixture/`, and its queries and expected records come from that fixture's `manifest.json`, not from a spec.

Same 12 queries as experiment 0003, so the figures are comparable. The instrument is `docs/experiments/data/drop-rate-fixture.sh`.

**Faithfulness was confirmed before any result was read**, as spec 0010 task 11 requires. All 6 fixture tests pass: the gate record `DM-0008` chunks identically live and from the fixture, the fixture's nested tree is invisible to discovery at the repository root, and every committed manifest hash matches the committed bytes.

## Finding 1: removing both causes did not move the drop rate

| Cause | 0003 count | 0003 share | 0004 count | 0004 share |
|---|---|---|---|---|
| `not_additive` | 14 | 74% | 13 | 68% |
| `incomplete` | 3 | 16% | 3 | 16% |
| `unsupported_sub_claim` | 0 | 0% | 3 | 16% |
| `duplicate` | 1 | 5% | 0 | 0% |
| `over_cap` | 0 | 0% | 0 | 0% |
| `no_available_citations` | 0 | 0% | 0 | 0% |

**19 of 21 draft sentences dropped. 2 emitted. 0 queries of 12 answered** (experiment 0003: 19 of 20 dropped, 1 of 12 answered).

The marker strip was expected to change the mix once markers stopped consuming sentences. It did not. `not_additive` stays the critical path at roughly seven drops in ten, and the calibration target for spec 0010 task 13 is now read from a clean instrument rather than a starved one: **68 percent of drops, 13 of 19**.

The one query that answered in experiment 0003 does not answer here, and the two emitted sentences did not produce an answered result: both their queries still abstained because coverage found their remaining facet uncovered.

## Finding 2: over splitting, a third cause no calibration reaches

`unsupported_sub_claim` went from 0 to 3 of 19 drops. It fires now for a plain reason: sentences finally reach entailment. Reading the claims shows the mechanism is not the enumerated list splitting that experiment 0003 recorded as finding 3. It is sharper than that. Decomposition returns fragments so atomic that they no longer carry what grounds them:

```text
S1.1 (S1)  Sub claim decomposition was chosen.
           entailment=unsupported
           reason=The evidence does not mention sub claim decomposition or
                  provide any context that supports the assertion that it
                  was chosen.

S1.1 (S1)  The adapter warns.
           entailment=unsupported
           reason=The evidence does not mention any warnings from the
                  adapter; it discusses the shape test and its implications
                  without indicating that the adapter itself issues warnings.
```

Both parents were reasonable sentences. Both died because a fragment of them, read alone, is not something the evidence states. This passes the AC-11 lexical test by construction (the tokens are all the parent's), so no tolerance setting touches it: the additive half is about substituted vocabulary and the completeness half is about dropped clauses, and this is neither.

Spec 0010's follow up tracks **under** splitting, where a decomposition returns the parent undivided and degrades to the whole sentence check. This is the opposite failure and nothing currently tracks it. It also means loosening the additive tolerance (task 13) will not simply raise the answer rate: sentences that stop dying at `not_additive` arrive at entailment, where this cause is waiting.

## Finding 3: the coverage provider failed the query instead of abstaining

Found while running the gate, because it blocked the gate from being read at all. The `decision` query returned `state: failed` with `claim_verification provider.coverage`, twice.

Instrumenting `validate_coverage` showed the coverage model returning a correct verdict in an invalid shape, on 4 of 4 attempts across 2 runs:

```text
payload:  {"rows":[{"facet_id":"F1","covered":false,
           "reason":"The sentence does not state a decision about hybrid ...",
           "sentence_ids":["S3"]}]}
REJECTED: uncovered row F1 names sentences
```

The verdict was right: F1 was genuinely uncovered. The model listed the sentence it had judged and rejected. AC-12 rejects an uncovered row that names sentences, and the repair attempt returned the same shape, so a correct abstention became a hard query failure. `failed` is never an expected gate state.

The cause is that nothing ever told the model the rule. `COVERAGE_SYSTEM_PROMPT` does not state it and the coverage JSON schema carried no property descriptions. The fix mirrors the shape AC-13 already established, hard enforcement in code plus soft guidance to the model: `validate_coverage` is unchanged and still rejects the shape, and the schema's `sentence_ids` property now carries a description saying to leave it empty when `covered` is false.

Measured either side of the change, as small as the sample is:

| | Coverage calls | Rejected attempts |
|---|---|---|
| before | 2 | 4 of 4 |
| after | 3 | 0 of 3 |

The repair attempt was **not** already absorbing this. Before the change both attempts failed every time; after it, every call returned an uncovered row with empty ids on the first attempt. This is a deviation from spec 0010 recorded for `/architect` to ratify, and the pattern deserves ratifying rather than only this instance, since no other schema in `openai_generation.py` uses `description`.

## Finding 4: the gate still fails, and it fails stochastically

| Query | Expected (manifest) | Actual |
|---|---|---|
| What was decided about hybrid lexical and semantic retrieval? | `answered`, `DM-0008` | **abstained** in the sweep; **answered** in a separate run |
| Why did we choose hybrid lexical and semantic retrieval? | `abstained` | abstains, still vacuously |

The `reason` query meets its expected state but for the wrong reason again: all 3 of its draft sentences were dropped as `decomposition_invalid`, so nothing reached coverage. That is the same artifact pass experiment 0003 recorded.

The `decision` query is worse than a plain fail. In the run where it answered, the sentence that actually states the decision was dropped as `not_additive`, and coverage marked the decision facet covered by this:

```text
S4  The JobPilot corpus cannot establish that hybrid retrieval is better at
    scale, and it does not claim general retrieval superiority.
```

That is a caveat, not a decision. Under the AC-12 directness rule a context or consequence fragment does not state a decision, so this is a coverage directness failure, and it produced a run that matches the manifest's `expected_record` and `expected_state` while answering the question wrongly. **The gate's oracle is state plus record, and that oracle cannot see this.** Worth noting for whoever tightens the gate: experiment 0003 had to tighten query 1's oracle for the same class of reason.

## What this changes

1. **Task 13 calibration keeps its priority and its target is now clean: 68 percent, 13 of 19 drops.** The share did not fall when the two known contaminants were removed, so it is a property of the additive half rather than of the starved pipeline.
2. **Over splitting is a new item and belongs in the spec's follow up**, beside the under splitting item that already exists. It is not reachable by calibration, and it will grow as calibration lets more sentences through to entailment.
3. **The coverage schema description needs ratifying**, both this instance and the pattern.
4. **The gate oracle is weaker than the gate's purpose.** State plus record passed a substantively wrong answer. Consider requiring the answer to cite the decision statement rather than any chunk of the record.

## Threats to validity

- 12 queries, one run each, on a 6 record corpus. Decomposition is stochastic and the `decision` query returned two different states in two runs, so these are small sample rates, not stable figures. The 68 percent additive share is large enough to act on; the 16 percent for `unsupported_sub_claim` rests on 3 events.
- The fixture adapts 6 records, not 7: `0009-proven-correctness-evaluation-harness` holds only a `verify.md` and is skipped for having no `index.md`, live and in the fixture alike. Two more specs are single files rather than directories and are not discovered either. This matches the live corpus, so it is not fixture drift, but the gate reads a smaller corpus than `docs/specs/` appears to hold.
- The coverage before and after figures rest on 2 and 3 calls. The shape of the change is unambiguous (every attempt wrong, then every attempt right), the rate is not.
- The queries are the same ones experiment 0003 used, written by the person who read those results. Comparability was the point, neutrality is still not claimed.
- Coverage only runs when a sentence survives, so with 19 of 21 dropped the coverage stage is barely sampled at all. Every coverage figure here is measured on the same starved pipeline problem one stage further down.
