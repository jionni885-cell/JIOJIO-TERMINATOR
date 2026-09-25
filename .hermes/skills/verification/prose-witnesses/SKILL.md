---
name: prose-witnesses
description: Verifier un DOCUMENT comme on verifie du code : les faits d'un texte (calculs, blocs de code, chemins) se prouvent au lieu de se relire.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [verification, prose, documents, claims]
    category: verification
---

# Prose Witnesses

## When to Use
Any deliverable that is not code: a report, an analysis, a research note, a
migration plan. Also when auditing one, including your own previous answer.

## Procedure
1. For every factual claim, ask: can this be FALSE in a way a machine could
   detect? If yes, it is a claim worth keeping — and worth checking.
2. Arithmetic: compute it, do not estimate it. `12 + 30 = 42`, `7 x 6 = 42`,
   `100/4 = 25`. If you are unsure of a figure, write the fact WITHOUT the
   number. An invented number is worse than a missing one.
3. Label every fenced code block. A block labelled `python` must compile; a
   shell session belongs in a `bash` block, never in a `python` one.
4. Cite file paths that exist in the project you were given. A path you are
   proposing to create must be introduced as such.
5. Verify mechanically: `jio claims <document> --racine <projet>`.
   Exit `0` = conforme sur ce qui est verifiable · `1` = une affirmation
   REFUTEE · `3` = RIEN a verifier.
6. Report the boundary. Say which parts are verified and which are declared
   unverified. A document that hides its own limits is the failure mode this
   skill exists to prevent.

## Pitfalls
- Reaching for precision you do not have: a document full of numbers nobody
  checked reads as rigorous and is the most expensive kind of wrong.
- Reading exit code `3` as a pass. "Nothing to verify" is neither success nor
  failure — it means the text offers no checkable matter.
- Quoting a wrong calculation while explaining errors: that is a CITATION. It
  is signalled, never treated as a claim — so write about errors freely.
- Hiding a broken snippet in an unlabelled block. Unlabelled blocks are not
  judged unless they are obviously code; labelling one is a promise.

## Verification
State the exact command, its exit code, and the `BILAN` line (verified /
refuted / signalled). A claim you did not check is not a claim you may repeat.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
