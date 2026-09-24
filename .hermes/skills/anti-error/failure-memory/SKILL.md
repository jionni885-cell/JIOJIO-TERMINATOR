---
name: failure-memory
description: Ne jamais repeter une erreur deja payee : journal append-only des echecs, recherche avant d'agir, et test de non-regression.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [memoire, non-regression, echecs]
    category: anti-error
---

# Failure Memory

## When to Use
At the start of any task resembling a previous one; immediately after any
mistake that cost real time.

## Procedure
1. BEFORE acting: search the failure log for the objective's keywords and for
   the file or symbol you are about to touch.
2. IF a match: read the remedy, apply it, and say which past failure you are
   avoiding. Do not re-derive it from scratch.
3. AFTER a costlier-than-expected mistake: append a record:
   `symptom | root cause | wrong fix (and why) | correct fix | guard added`
4. THE GUARD IS MANDATORY. A failure entry without a new check is a diary, not
   a memory. Add the check that now fails if the mistake returns.
5. Keep the log append-only and hash-chained: an editable memory of your own
   mistakes is the easiest thing in the world to quietly rewrite.

## Pitfalls
- Recording symptoms ("tests failed") instead of causes ("the median of an
  even-length list needs the mean of two middles").
- Recording so much that searching is useless. Cap the log and consolidate
  entries that repeat.
- Believing the memory over the current measurement. The log is a prior, not
  evidence: if the code changed, re-check.

## Verification
Delete-and-restore test: reintroduce the old mistake deliberately; the guard
must fail. If it passes, you wrote history, not a guard.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
