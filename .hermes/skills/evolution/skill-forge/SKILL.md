---
name: skill-forge
description: Auto-amelioration disciplinee : transformer les echecs repetes en competences bornees, mesurees et reversibles.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [auto-amelioration, skills, metacognition]
    category: evolution
---

# Skill Forge

## When to Use
After a task, when a failure repeated, or when a procedure proved itself worth
keeping.

## Procedure
1. COLLECT failures that occurred at least twice. One occurrence is noise.
2. DIAGNOSE and be honest: missing knowledge? missing procedure? ambiguous
   spec? tool limit? model limit? Only the first two are fixable by writing a
   skill. Writing a skill around a model limitation produces a document that
   lies about what is possible.
3. WRITE one skill per problem, with the sections: When to Use / Procedure /
   Pitfalls / Verification.
4. BOUND it: under ~5000 tokens per skill, under ~25000 for the whole library,
   and the description must say WHEN to use it — routing is the hard part.
5. MEASURE: record the baseline before and the result after. No number, no
   improvement — only a hypothesis.
6. REVERT if it did not help. A library that only grows eventually contradicts
   itself.

## Pitfalls
- Writing a skill about how good you are instead of how to do the work.
- Vague verification sections ("make sure it works") — the checker must be able
  to FAIL, otherwise the section is decoration.
- Editing a skill in place with no previous version: an improvement you cannot
  roll back is a gamble.
- Repeating the model's own rationalisation as a lesson. The lesson must come
  from the failure's structure, not from the story told about it.

## Verification
Replay an old failure. With the new skill loaded, the failure must not recur.
If it recurs, the skill did not address the cause.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
