"""Name the token that fails the AC-11 additive half (experiment 0010).

Experiment 0009 recorded ``additive_failure=content_token`` on a correct answer
sentence and could go no further: ``RejectedDecomposition`` records the failure
category but never the claim text, so the offending token is not in the trace.
The category does not say which of two very different things happened:

  narrow morphology   the sub claim used a word form the stem rules do not
                      reach (``decide`` against ``decision``), which is a rule
                      fix
  genuine paraphrase  the sub claim substituted a synonym, which no stem rule
                      can ever reach, and which means the lexical additive
                      check cannot work as designed

Spec 0010 AC-9 already records one observed synonym substitution (``goal``), so
both are live. This script decides which one a given sentence hits.

It calls the shipped functions for every verdict: ``decompose_sentence`` for the
split, ``sentence_tokens`` and ``sub_claim_is_additive_free`` for the judgement.
The greedy walk that names the token is the one piece written here, because the
shipped matcher returns a bool and not a position, so the walk is **cross
checked against the shipped verdict on every sub claim** and any disagreement is
reported as a script bug rather than as a finding. A hand written replica that
silently disagreed with the shipped pipeline is what put wrong figures into spec
0003, and that is what this cross check exists to prevent.

Usage, from the repository root:

    uv run --env-file .env python \
        docs/experiments/data/additive-failure-token.py [runs]
"""

from __future__ import annotations

import sys

from decision_memory.application.verification import (
    FUNCTION_WORDS,
    MAX_ADDED_FUNCTION_WORDS,
    sentence_tokens,
    sub_claim_is_additive_free,
    tokens_match,
)
from decision_memory.infrastructure.openai_generation import decompose_sentence

# The parent sentence and its cited chunk, captured verbatim from the
# experiment 0009 traces. The bracketed chunk id the debug renderer appends at
# print time is not part of the sentence text and is not included here.
PARENT = (
    "The decision was made to use a fallback behavior for resume generation, "
    "where a role whose bullets are affected by a dropped number never ends up "
    "empty, and only the offending bullet is dropped first, with the role "
    "falling back to the user's own written text if necessary."
)

CHUNK_ID = "ch_02173a64eebd5b1d6866e668a65a9227547d4dec0cb19d5e19efa90241002c88"

# DM-0019 body[2], the only chunk this sentence cites. Trimmed to the invariant
# the sentence draws from; the decomposition prompt is dominated by the parent
# sentence, and the full chunk is in the store if a fuller run is wanted.
CHUNK_TEXT = (
    "**Key invariants**:\n"
    "- A role whose bullets are affected by a dropped number never ends up "
    "empty: only the offending bullet is dropped first, and the role only "
    "falls back to the user's own written text if that drop would otherwise "
    "leave it with nothing."
)


def first_failing_token(
    sub_tokens: list[str], parent_tokens: list[str]
) -> tuple[str, str] | None:
    """The first token that fails, and why, mirroring the shipped walk.

    Returns ``(token, kind)`` where kind is ``content_token`` or
    ``function_word_overrun``, or None when the sub claim passes. Cross checked
    against ``sub_claim_is_additive_free`` by the caller.
    """
    used = [False] * len(parent_tokens)
    added_function_words = 0
    for token in sub_tokens:
        matched = False
        for index, parent_token in enumerate(parent_tokens):
            if not used[index] and tokens_match(token, parent_token):
                used[index] = True
                matched = True
                break
        if matched:
            continue
        if token not in FUNCTION_WORDS:
            return token, "content_token"
        added_function_words += 1
        if added_function_words > MAX_ADDED_FUNCTION_WORDS:
            return token, "function_word_overrun"
    return None


def main() -> int:
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    parent_tokens = sentence_tokens(PARENT)
    print(f"parent: {len(parent_tokens)} tokens\n{PARENT}\n")

    for run in range(1, runs + 1):
        print(f"=== run {run} ===")
        sub_claims = decompose_sentence(PARENT, [(CHUNK_ID, CHUNK_TEXT)])
        print(f"{len(sub_claims)} sub claims returned")
        for position, text in enumerate(sub_claims, start=1):
            sub_tokens = sentence_tokens(text)
            shipped_verdict = sub_claim_is_additive_free(sub_tokens, parent_tokens)
            walked = first_failing_token(sub_tokens, parent_tokens)
            # The walk and the shipped verdict must agree, or the walk is
            # wrong. ``sub_claim_is_additive_free`` returns None or the closed
            # category, so both the outcome and the category must line up.
            agrees = (shipped_verdict is None) == (walked is None) and (
                walked is None or shipped_verdict == walked[1]
            )
            if not agrees:
                print(
                    f"  [{position}] SCRIPT BUG: shipped verdict "
                    f"{shipped_verdict} disagrees with the walk {walked}; "
                    "ignore this run"
                )
                continue
            if walked is None:
                print(f"  [{position}] ok       {text}")
            else:
                token, kind = walked
                print(f"  [{position}] FAILS    {kind}: {token!r}")
                print(f"           {text}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
