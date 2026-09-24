---
name: metamorphic-invariance
description: Verifier une propriete par mutation de l'entree : une invariance qui ne survit pas a la perturbation etait une coincidence.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [verification, mutation, oracle-free]
    category: verification
---

# Metamorphic Invariance

## When to Use
When you have no ground truth but you do have relationships the correct answer
must satisfy. Common for numerical code, parsers, formatters, search, ranking.

## Procedure
1. Derive a metamorphic relation: a change to the input whose effect on the
   output is KNOWN.
   - `sort(x)` and `sort(shuffle(x))` must be equal.
   - `parse(f(x)) == parse(x)` for a lossless re-encoding `f`.
   - `search(q + unrelated_term)` must not drop the exact match on `q`.
   - `f(x)` and `f(x)` must be equal (determinism).
2. Apply the transformation, run both sides, compare.
3. If the comparison is fuzzy (text, scores), use an explicit threshold and say
   which one; a "similarity > 0.9" claim must name the metric.
4. A violation gives you a counterexample, not a yes/no. Keep the minimal pair.

## Pitfalls
- Applying a negation or inverse check to a question that has no boolean
  answer: this produces a false alarm, and a false alarm destroys trust in the
  whole gate. Confirm the relation applies to THIS output shape first.
- Comparing floats exactly.
- Using a transformation that is not actually invariant (e.g. reordering a list
  where order is semantically significant).
- More than ~10 transformations without results: pick the three strongest.

## Verification
State the relation, the transformation applied, the two outputs, and the
threshold. A reader must be able to disagree with your relation specifically.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
