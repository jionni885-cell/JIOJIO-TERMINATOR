---
name: context-budget
description: Tenir le contexte comme un budget : 40% de travail utile, externalisation des sorties longues, compaction aux frontieres.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [contexte, budget, compaction]
    category: harness
---

# Context Budget

## When to Use
Continuously, in any session longer than a few steps.

## Procedure
1. Budget the window: ~40% live working set, >= 20% margin, the rest for
   references loaded only when needed.
2. Anything above ~200 lines is a REFERENCE. Pass `path:symbol:lines`, never the
   contents. Whole-file pasting is the most common way to destroy a session.
3. Long command output: keep the head, the tail, and the exact failing line.
   Offload the rest to a file and keep the path.
4. Keep exactly one durable plan artifact per task, and REWRITE it each time the
   state changes. Appending turns the plan into noise by hour two.
5. Compact at ~85% of the window, at a decision boundary — after a verified
   result, before starting a new sub-problem. Never on a timer.
6. On compaction, preserve: objective, rules, open failures, decisions and their
   reasons. Discard: raw logs, superseded drafts, tool chatter.

## Pitfalls
- POISONING: keeping a fact you already corrected. When correcting, edit the
  original line — do not add a correction below it.
- DISTRACTION: relevant-looking volume crowding out the task.
- CONFUSION: too many tools or rules at once. Past a few dozen tools, accuracy
  collapses — disable what this task does not need.
- Compacting in the middle of a causal chain: you will lose the reason, keep the
  conclusion, and repeat the mistake.

## Verification
After compacting, you must still be able to answer: what is the objective, what
are the open rules, what failed last, and why the current approach was chosen.
If any of the four is gone, the compaction was too aggressive.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
