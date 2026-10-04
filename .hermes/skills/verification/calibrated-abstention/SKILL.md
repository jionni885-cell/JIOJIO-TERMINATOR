---
name: calibrated-abstention
description: Transformer l'incertitude en decision : accepter, accepter sous reserve, ou s'abstenir avec un risque borne.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [abstention, calibration, risk]
    category: verification
---

# Calibrated Abstention

## When to Use
Before delivering any claim you cannot fully witness, and whenever the cost of a
silent error is high.

## Procedure
1. Count what was actually checked, not what was intended:
   - `a` = checks that passed, `n` = checks attempted.
2. Estimate the conformal risk: `(errors + 1) / (n + 1)`. With no evidence,
   assume the worst — never assume 0.
3. Compare to the acceptable risk `alpha`:
   - `risk <= alpha` -> deliver;
   - `risk` slightly above, or only partially applicable checks -> deliver
     UNDER RESERVATION, naming the reserve;
   - `risk` clearly above, or fewer than `ceil(1/alpha) - 1` observations ->
     ABSTAIN.
4. When abstaining, always supply the remedy: the experiment, the data, or the
   access that would turn abstention into a proof.

## Pitfalls
- "Social conformity": if everyone else agrees, confidence rises and real
  coverage collapses (measured: 90% -> 74%). Independence of raters is part of
  the guarantee; agreement between correlated raters is not evidence.
- Treating a small `n` as a small risk. Few observations mean wide intervals.
- Abstaining after doing the work instead of before it: check feasibility first.
- Hiding the reservation in a footnote.

## Verification
Write the sentence a reviewer would use to challenge you: "you claim risk <= X
on the basis of N observations". If that sentence is embarrassing, abstain.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
