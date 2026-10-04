---
name: executable-proof
description: Prouver une affirmation par execution plutot que par raisonnement : temoin, commande exacte, code de sortie, et mode fail-closed.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [verification, tests, fail-closed]
    category: verification
---

# Executable Proof

## When to Use
Any time you are about to assert that something works, is fixed, or is correct.

## Procedure
1. Name the claim in one sentence, with the rule id it serves.
2. Find the cheapest executable witness: compile > type-check > import > unit
   test > integration test > replay > human judgement. Stop at the first that
   can actually FAIL.
3. Run it. Capture: exact command, exit code, the relevant output lines.
4. Record the witness next to the claim, in the form:
   `rule R-003 | cmd: pytest -k median | exit 0 | observed: 5 passed`
5. If no witness is possible, downgrade the claim to "unverified" and say what
   would settle it. Never upgrade it by repeating it more confidently.

## Pitfalls
- Running a test that cannot fail (assert True, no assertions, mocked success).
- Treating a green suite as proof of the property you actually care about —
  tests prove only what they exercise.
- Letting the author of the artifact be the only witness.
- `2>/dev/null` and `|| true`: this removes the evidence you were collecting.
- Reading a log instead of re-running the command.

## Verification
A proof is acceptable when a second person, given only your witness line, gets
the same exit code. If they cannot reproduce it, it was an anecdote.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
