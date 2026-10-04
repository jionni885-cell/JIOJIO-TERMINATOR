# Duel sur DOCUMENTS : ce que le harness apporte, sur des rapports

- **date** : 2026-10-01 13:04:03 +0000
- **modele mesure** : `simule` — documents simules ; la VERIFICATION de leurs affirmations, elle, est reelle
- **taches** : 1 document(s) · **5 tirage(s)** · 4 tour(s) de boucle maximum
- **duree** : 14.1 s · **commit** : `0608fcd`

## Les bras, avec leurs intervalles

| competence | justes | IC95 | aveugle | best-of (oracle) | SILENCIEUX | sous reserve | abstentions | appels |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0.00 | 0.0% | [0% ; 43%] | 0.0% | 0.0% | **0** | 5 | 0 | 9.6 |
| 0.35 | 100.0% | [57% ; 100%] | 0.0% | 100.0% | **0** | 0 | 0 | 3.6 |

**Erreurs livrees SANS RIEN DIRE : 0** — le seul chiffre qui doit rester
a zero dans tout le projet. Un document FAUX livre *sous reserve nommee* n'est pas un
silence : le systeme a dit ce qu'il ne pouvait pas garantir.

## Ce que cette mesure ne dit pas

- un document peut etre FAUX sans qu'aucune de ses affirmations ne le soit : la
  verification porte sur ce qui est CALCULABLE, pas sur le sens ;
- a competence 0,00, tous les tirages sont des distracteurs : le systeme livre alors
  sous reserve, ou s'abstient — jamais en presentant un faux calcul comme prouve ;
- les documents sont SIMULES : ce chiffre mesure l'architecture, pas un modele reel.

## Reproduction

```sh
jio bench --prose --runs 5 --rounds 4 --rapport evidence/bench-prose-skill-020.md
```
