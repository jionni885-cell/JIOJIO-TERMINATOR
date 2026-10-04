---
name: structured-failure
description: Convertir chaque echec en donnee exploitable plutot qu'en recit : regle, attendu, observe, temoin, contre-exemple minimal.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [erreurs, feedback, reprise]
    category: harness
---

# Structured Failure

## When to Use
Every time something fails, and every time you hand a failure to another agent
or to your future self.

## Procedure
Emit a record, not a paragraph:
```
stage:          build | test | typecheck | review
rule_id:        R-003
expected:       [1,2,3,4] -> 6
observed:       [1,2,3,4] -> 4
witness:        python -c "..." (exit 1)
counterexample: sum_even([1,2,3,4])
already_tried:  bounded loop fix (same failure)
remedy_hypothesis: the loop must include n itself
```
Rules:
- FIRST failing rule only. A list of ten failures hides the cause.
- Always include the minimal reproducing input.
- Always include what was already tried, so attempt N+1 differs from attempt N.
- Never write "tests failed" without the assertion and its input.

## Pitfalls
- Paraphrasing the error into prose. Translate the error verbatim, then add a
  one-line hypothesis — the verbatim part is what can be checked.
- Reporting the last failure instead of the first: later failures are usually
  consequences.
- Dropping the witness command, which makes the failure unverifiable.

## Verification
Another agent, given only your record, must be able to reproduce the failure
without asking a question. If they must ask, the record is incomplete.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
