---
name: decorrelated-panel
description: Obtenir plusieurs avis reellement independants : D1 a D5, quorum n >= 3f+1, et detection de l'echo entre verificateurs.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [consensus, decorrelation, quorum]
    category: harness
---

# Decorrelated Panel

## When to Use
Whenever a decision matters and one opinion is not enough — before shipping,
before a destructive action, when a result is surprising.

## Procedure
1. Make the raters genuinely independent along the five axes:
   D1 different context (raw artifact only), D2 different model, D3 different
   role, D4 different grounding (execute vs read), D5 different input
   perturbation.
2. Ask each rater: "find the flaw", not "is this good". Framing is part of the
   independence.
3. Size the quorum by the fault model: with up to `f` liars you need `n >= 3f+1`.
   For two honest raters, three is the minimum; five for safety.
4. DETECT ECHO: compare the raters' rationales. Near-identical explanations with
   the same blind spot mean they are correlated, and their agreement counts once.
5. Aggregate by rule, not by vote count: for each rule, how many INDEPENDENT
   raters witnessed a failure?

## Pitfalls
- Showing raters each other's answers: immediately destroys independence.
- Summing correlated opinions as if they were independent evidence.
- Averaging a "fix it" and a "reject it" into "partially fine".
- Using the same model with the same context three times and calling it a panel.

## Verification
Ask: "could two of these raters have produced the same wrong answer for the same
reason?" If yes, your panel is narrower than it looks, and you should say so.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
