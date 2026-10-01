# Duel : ce que le harness apporte, sur CE modele

- **date** : 2026-09-30 19:53:36 +0000
- **modele mesure** : `openai:modele-local-char` (openai)
- **taches** : 5 tache(s) du banc · **1 tirage(s)** · 4 tour(s) de boucle maximum
- **duree** : 716.6 s · **commit** : `e951a5f`
- **note** : point d'acces compatible OpenAI, modele modele-local-char

## Les bras, avec leurs intervalles

| config | reussite | IC95 | appels/tache | essais |
| --- | ---: | ---: | ---: | ---: |
| modele brut (1 appel) | 0.0% | [0% ; 43%] | 1.0 | 5 |
| echantillonnage seul (best-of-3) | 0.0% | [0% ; 43%] | 3.0 | 5 |
| CONTROLE : autant d'appels, 0 verification | 0.0% | [0% ; 43%] | 3.0 | 5 |
| verification executable + reprise | 0.0% | [0% ; 43%] | 3.0 | 5 |
| JIO complet (livraison auditee) | 0.0% | [0% ; 43%] | 3.0 | 5 |
| AUCUN ORACLE : regles traduites en temoins | non mesure | — | — | 0 |
| AUCUN ORACLE : traducteur a 50 % de fidelite | non mesure | — | — | 0 |
| AUCUN ORACLE : traducteur FAUX (lue a l'envers) | non mesure | — | — | 0 |
| AUCUN ORACLE : VOS regles traduites par le modele | non mesure | — | — | 0 |
| CONTROLE sans oracle : meme budget, 0 verification | non mesure | — | — | 0 |

Lire la colonne IC95 avant toute conclusion : un bras dont l'intervalle est large situe la mesure, il ne la tranche pas. Et un bras « non mesure » n'est pas un bras a zero — c'est un bras qui n'a pas tourne.

## Les comparaisons qui tranchent

| question | ecart | IC95 | intervalle exclut zero |
| --- | ---: | ---: | --- |
| budget d'appels EGAL : verification vs echantillonnage | +0.0 pts | [-43.4 ; +43.4] | NON |
| gain total du harness (modele brut -> JIO) | +0.0 pts | [-43.4 ; +43.4] | NON |

- **budget d'appels EGAL : verification vs echantillonnage** — aucune difference sur ce jeu de taches.
- **gain total du harness (modele brut -> JIO)** — aucune difference sur ce jeu de taches.

## Integrite (ce qui doit rester a zero)

- exploits d'integrite detectes : 0
- abstentions sans oracle : 0
- candidats CORRECTS rejetes : 0
- ERREURS LIVREES SANS RESERVE : 0

## Ce que ce rapport prouve, et ce qu'il ne prouve pas

**Il prouve** : ce que le harness change sur CE modele, a budget d'appels EGAL — le controle apparie utilise autant d'appels du modele que le bras qu'il controle, donc un gain ne peut pas venir du nombre d'essais.

**Il ne prouve pas** : le niveau absolu du modele sur un benchmark public. Les chiffres de la litterature (Terminal-Bench, SWE-bench) portent sur d'autres taches, d'autres budgets et d'autres reglages ; les citer ici comme reference serait un raccourci faux. Ce rapport repond a une question locale, et il y repond avec ses intervalles.

**Pour aller plus loin** : `--runs` elargit l'echantillon (les intervalles se resserrent), `--taches 0` prend tout le banc, et `jio ablation` retire une brique du harness pour dire laquelle porte le gain.
