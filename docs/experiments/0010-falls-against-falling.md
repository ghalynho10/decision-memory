# Experiment 0010: `falls` against `falling`, and a matcher at war with its own job

**Date**: 2026-08-14
**Status**: Complete
**Follows**: [Experiment 0009](0009-why-query-two-abstains.md)
**Result**: The token is **`falls`**, against the parent's **`falling`**. The decomposition was flawless: four faithful, near verbatim sub claims. It was rejected because the AC-11 stem rules compare two tokens **pairwise**, deriving one from the other by suffix addition, so two different inflections of a common base never match. `falls` and `falling` both come from `fall`, and neither is reachable from the other. This is the **narrow morphology** cause, not the synonym cause, so the fix is a matcher change rather than a rethink of lexical verification. It also generalises badly: turning a subordinate clause into a standalone atomic claim requires changing a participle into a finite verb, which is what correct decomposition does, so the additive half systematically punishes the behaviour the decomposition prompt asks for.

## Why this run happened

Experiment 0009 recorded `additive_failure=content_token` on a correct answer sentence and could go no further, because `RejectedDecomposition` records the failure category and never the claim text. The category leaves two possibilities open, and they are very far apart in cost:

- **Narrow morphology.** The sub claim used a word form the stem rules do not reach. A matcher fix.
- **Genuine paraphrase.** The sub claim substituted a synonym, which no stem rule can ever reach, meaning the lexical additive check cannot work as designed and needs replacing.

Both were live. Spec 0010's AC-9 already records one observed synonym substitution, `goal`, so the expensive case was not hypothetical.

## Method

`docs/experiments/data/additive-failure-token.py`, committed with this experiment. It takes the parent sentence and its cited chunk verbatim from the experiment 0009 traces, calls the shipped `decompose_sentence`, then judges each sub claim with the shipped `sentence_tokens` and `sub_claim_is_additive_free`.

Naming the offending token needs a position, and the shipped matcher returns a category rather than an index, so the greedy walk is written in the script. **It is cross checked against the shipped verdict on every sub claim**, outcome and category both, and a disagreement is reported as a script bug rather than as a finding. A hand written replica that silently disagreed with the shipped pipeline is what put wrong figures into spec 0003's `rationale.md`, and this cross check exists for that reason.

Three runs. Decomposition is stochastic; the result was identical each time.

## Result

Parent sentence, 48 tokens:

```text
The decision was made to use a fallback behavior for resume generation, where a
role whose bullets are affected by a dropped number never ends up empty, and
only the offending bullet is dropped first, with the role falling back to the
user's own written text if necessary.
```

Every run returned the same four sub claims with the same verdicts:

```text
[1] ok       The decision was made to use a fallback behavior for resume generation.
[2] ok       A role whose bullets are affected by a dropped number never ends up empty.
[3] ok       Only the offending bullet is dropped first.
[4] FAILS    content_token: 'falls'
             The role falls back to the user's own written text if necessary.
```

## Finding 1: the decomposition is correct and the matcher is wrong

Read the four sub claims against the parent. They divide it faithfully, add nothing, omit nothing, and stay nearly verbatim, which is exactly what `DECOMPOSE_SYSTEM_PROMPT` asks for and what AC-11 is written to check.

The single difference between sub claim 4 and its clause in the parent is the verb form: the parent has `falling`, the sub claim has `falls`. Nothing else in the response is disputed.

The provider did its job. The whole answer was destroyed by the check.

## Finding 2: pairwise stem rules cannot match two inflections of one base

`_stem_match` names its two arguments `shorter` and `longer` and tries to derive `longer` from `shorter`: equality, `shorter` plus `s`, `es`, `ed` or `ing`, `shorter` losing a final `e` and gaining `ed` or `ing`, `shorter` repeating its final character and gaining `ed` or `ing`, or `shorter` trading a final `y` for `i` and gaining `es` or `ed`.

Apply that to this pair. `shorter` is `falls`, `longer` is `falling`:

- `falls` + `s`, `es`, `ed`, `ing` gives `fallss`, `fallses`, `fallsed`, `fallsing`. None is `falling`.
- No final `e` to drop.
- Repeating the final character gives `fallssed` and `fallssing`.
- No final `y`.

Both tokens derive from `fall`, but the rules never reach a common base; they only ever transform one surface form into the other. **So any two different inflections of the same word fail to match each other**: `falls` against `falling`, `drops` against `dropped`, `decides` against `deciding`. A match happens only when the parent carries the bare base form.

## Finding 3: this puts the check at war with the job it is checking

Decomposition turns subordinate clauses into standalone claims. English subordinate clauses use participles (`with the role falling back`) and standalone sentences use finite verbs (`the role falls back`). **Changing the inflection is not a paraphrase, it is what the operation requires.**

So the additive half systematically rejects the transformation the decomposition prompt asks the model to perform, on any sentence built from participial clauses. That is a structural explanation for figures previously recorded as a tolerance problem: the 68 percent `not_additive` share of experiment 0004, and the 7 of 7 `content_token` split of experiment 0007.

## Finding 4: the cheap cause, and the deliberate trade behind it

No synonym was substituted. The expensive possibility, that lexical additive checking cannot work in principle, is not what this sentence hits.

The pairwise design was deliberate: it avoids over stripping, which would create false matches and weaken the substitution guard the additive half exists to provide. That trade was made without this evidence. It now has a measured cost: on this query it converts a correct, cited answer into an abstention, deterministically.

Naming the fix is out of scope here. The obvious direction, reducing both tokens to a common stem before comparing, is precisely the over stripping the current design avoids, so the trade needs deciding with the false match risk in view rather than assumed away.

## A script bug the cross check caught

The first version of this script compared the shipped verdict against a boolean. `sub_claim_is_additive_free` returned `bool` before task 17 and returns `str | None` after it (spec 0010 AC-19 made it report the category). Every row therefore printed as a disagreement and no finding was reported.

The walk had been right the whole time and the check around it was wrong. Recorded because the check working is the point: it refused to emit a finding while it could not agree with the shipped matcher, which is the failure mode spec 0003 suffered when nothing was cross checking.

## Limits

- **One sentence, one query, three runs.** The mechanism in finding 2 is deterministic and provable from the rules, but the claim that it explains the bulk of `not_additive` drops across the corpus is an inference from two prior measurements, not something this experiment measured.
- **The cited chunk was trimmed** in the script to the invariant the sentence draws from, rather than the full `body[2]` chunk. The decomposition prompt is dominated by the parent sentence and the result was stable across three runs, but this is not byte identical to the live call.
- **The greedy walk is a replica**, mitigated by the per sub claim cross check rather than eliminated. If `sub_claim_is_additive_free` changes, the walk must be rechecked against it.
- **Nothing here measures the fix.** No alternative matcher was tried, and the over stripping risk that motivated the current design is unquantified.

## What this changes

- **The additive matcher is the next decision, and it is now a scoped one.** A named defect, a reproducible case, a deterministic failure, and a known trade to weigh. That is `/architect` work with evidence rather than another round of localisation.
- **Task 13 is confirmed as the wrong instrument for this**, for the third time and now with a mechanism rather than a category. Calibrating `MAX_ADDED_FUNCTION_WORDS` cannot reach a verb inflection.
- **The shipping calculus changes.** The expensive scenario is ruled out for this case, so the distance between the current build and a tool that answers questions is one matcher fix rather than a rethink.
- **Recording the offending token in the trace is now clearly worth doing.** This experiment needed a separate script and a live provider call to learn one word. A closed field carrying the token, which is not claim text, would have put it in the trace of every failing run.
