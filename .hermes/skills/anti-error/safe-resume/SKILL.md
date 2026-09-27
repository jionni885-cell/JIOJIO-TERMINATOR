---
name: safe-resume
description: Reprendre un travail interrompu sans jamais reutiliser un resultat obtenu dans un AUTRE monde : revision, fichiers, outils.
version: 1.0.0
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [reprise, cache, rollback, anti-erreur]
    category: anti-error
---

# Safe Resume

## When to Use
Any work that was interrupted: a blocked plan, a crashed run, a new session on the
same task, a rollback, a restored workspace. Also before trusting a result marked
"already verified".

## Procedure
1. Re-establish the WORLD before reusing anything: revision, files, tool versions,
   environment. A check is only valid for the state it was made on.
2. If the world changed, REPLAY. Re-running costs one command per step; believing a
   stale check costs a whole mission built on nothing.
3. Skip only what carries its own evidence, and say out loud which steps you
   skipped and why. A resume that hides its skips is indistinguishable from work
   that never happened.
4. Never "repair" a corrupted state file. A repaired state is a plan somebody
   invented — refuse, and ask for the plan again.
5. When the revision is unchanged but a dependency moved (another interpreter,
   another tool version, another model), treat it as a changed world too.
6. Write the skipped steps INTO the artifact you hand over, so the next reader
   sees the difference between "verified now" and "verified earlier".

## Pitfalls
- Caching on the wrong key: a timestamp, "it worked earlier", a green check from
  another branch — none of these identify a state.
- Restoring a snapshot and keeping the verifications made before the restore.
  That is the documented attack on agent rollback (arXiv 2608.29381): the state is
  hostile again while the checks still say "fine".
- Reading "0 steps executed" as "nothing to do". It may mean every step was
  skipped on a stale key.
- Resuming without saying which world you resumed in: the reader cannot tell a
  genuine continuation from a fresh claim.

## Verification
Name the revision before and after, and the exact command. `jio auto --reprendre`
prints one of two lines, and both are checkable:

    revision identique (6e6e58d6) : 1 etape(s) deja prouvee(s) sont sautees, le reste est rejoue
    revision differente (6e6e58d6 -> be2c3f16) : ... le plan est rejoue ENTIER

If neither line appears, the resume did not go through this discipline. A skipped
step must also carry its reason in the report, not only its absence from the logs.

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
