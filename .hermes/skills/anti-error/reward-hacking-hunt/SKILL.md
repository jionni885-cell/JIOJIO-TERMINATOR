---
name: reward-hacking-hunt
description: Red-team des six exploitations qui font passer un echec pour un succes : fuite, sabotage, sequence, proxy, cas particulier, memoire.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [anti-triche, red-team, evaluation]
    category: anti-error
---

# Reward-Hacking Hunt

## When to Use
Before accepting ANY passing result, and always when a solution looks
surprisingly easy.

## Procedure
Check each of the six, by name, and write the answer:
1. LEAKAGE — did the code read the grader, fixtures, hidden tests, or the answer?
   `grep` for file reads of test paths, for environment variables holding answers.
2. TAMPERING — was the verifier, config, CI file, or test modified in the same
   change? Diff the verification path, not just the product path.
3. SEQUENCE — was an intermediate artifact fabricated to skip a real step?
4. PROXY_GAMING — does the output satisfy a naive parser without solving the
   problem? Feed an adversarial input the parser did not anticipate.
5. SPECIAL_CASING — hardcoded inputs. Change one constant or boundary; if it
   breaks, it was special-cased.
6. MEMORIZATION — copied answer. Ask for a novel instance in the same family.

Then run the decisive test: a hold-out input the solver never saw, from a clean
state, with deterministic replay.

## Pitfalls
- Trusting the model's explanation: about 72% of exploiting trajectories are
  rationalised convincingly. The explanation is not evidence; the replay is.
- Only grepping for suspicious words. The dangerous variants are the ones that
  do not look suspicious.
- Running the hunt on a different setup than the one that produced the result.

## Verification
Report per class: `class | verdict | evidence | hold-out input tried`. A hunt
with no hold-out input has not started.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
