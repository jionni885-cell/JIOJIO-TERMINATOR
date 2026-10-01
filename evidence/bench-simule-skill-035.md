# Duel : ce que le harness apporte, sur CE modele

- **date** : 2026-10-01 13:01:07 +0000
- **modele mesure** : `simule` (simule)
- **taches** : 5 tache(s) du banc · **5 tirage(s)** · 4 tour(s) de boucle maximum
- **duree** : 168.2 s · **commit** : `ab2d3ff`
- **note** : reponses simulees deterministes ; la verification, elle, est reelle

## Les bras, avec leurs intervalles

| config | reussite | IC95 | appels/tache | essais |
| --- | ---: | ---: | ---: | ---: |
| modele brut (1 appel) | 32.0% | [17% ; 52%] | 1.0 | 25 |
| echantillonnage seul (best-of-3) | 76.0% | [57% ; 89%] | 3.0 | 25 |
| CONTROLE : autant d'appels, 0 verification | 76.0% | [57% ; 89%] | 3.6 | 25 |
| verification executable + reprise | 100.0% | [87% ; 100%] | 3.6 | 25 |
| JIO complet (livraison auditee) | 100.0% | [87% ; 100%] | 3.6 | 25 |
| AUCUN ORACLE : regles traduites en temoins | 96.0% | [80% ; 99%] | 4.6 | 25 |
| AUCUN ORACLE : traducteur a 50 % de fidelite | 80.0% | [61% ; 91%] | 5.6 | 25 |
| AUCUN ORACLE : traducteur FAUX (lue a l'envers) | 0.0% | [0% ; 13%] | 5.0 | 25 |
| AUCUN ORACLE : VOS regles traduites par le modele | non mesure | — | — | 0 |
| CONTROLE sans oracle : meme budget, 0 verification | non mesure | — | — | 0 |

Lire la colonne IC95 avant toute conclusion : un bras dont l'intervalle est large situe la mesure, il ne la tranche pas. Et un bras « non mesure » n'est pas un bras a zero — c'est un bras qui n'a pas tourne.

## Les comparaisons qui tranchent

| question | ecart | IC95 | intervalle exclut zero |
| --- | ---: | ---: | --- |
| budget d'appels EGAL : verification vs echantillonnage | +24.0 pts | [+4.6 ; +42.3] | oui |
| gain total du harness (modele brut -> JIO) | +68.0 pts | [+53.2 ; +91.7] | oui |

- **budget d'appels EGAL : verification vs echantillonnage** — ecart de +24.0 points, intervalle excluant zero a 25 essais.
- **gain total du harness (modele brut -> JIO)** — ecart de +68.0 points, intervalle excluant zero a 25 essais.

## Integrite (ce qui doit rester a zero)

- exploits d'integrite detectes : 0
- abstentions sans oracle : 25
- regles contrefaites par un traducteur faux : 460
- candidats CORRECTS rejetes : 6
- ERREURS LIVREES SANS RESERVE : 0

## Ce que ce rapport prouve, et ce qu'il ne prouve pas

**Il prouve** : ce que le harness change sur CE modele, a budget d'appels EGAL — le controle apparie utilise autant d'appels du modele que le bras qu'il controle, donc un gain ne peut pas venir du nombre d'essais.

**Il ne prouve pas** : le niveau absolu du modele sur un benchmark public. Les chiffres de la litterature (Terminal-Bench, SWE-bench) portent sur d'autres taches, d'autres budgets et d'autres reglages ; les citer ici comme reference serait un raccourci faux. Ce rapport repond a une question locale, et il y repond avec ses intervalles.

**Pour aller plus loin** : `--runs` elargit l'echantillon (les intervalles se resserrent), `--taches 0` prend tout le banc, et `jio ablation` retire une brique du harness pour dire laquelle porte le gain.
