# Le corps des competences entre dans l'index : ce que le routeur y gagne, et ce qu'il n'y gagne pas

- **date** : 2026-10-01 14:53:13 +0000
- **retouche** : BM25F : le corps des competences entre dans l'index comme second champ — un SEUL parametre change (`POIDS_CORPS` 0,00 -> 0,75)
- **materiel** : aucun modele appele, mesure deterministe · **commit** : `438d784`
- **reproductible par** : `jio skills --banc`, `jio skills --controle`, `scripts/mesure-routeur.py`

## Les trois jeux, avant et apres

| jeu | cas | avant | apres | gain (IC95) | hors sujet refuses |
| --- | ---: | ---: | ---: | ---: | ---: |
| banc (celui du reglage) | 31 | 83.9% | 87.1% | +3.2 pts [+0.0 ; +9.7] | 100% -> 100% |
| controle A (jamais vu) | 24 | 45.8% | 58.3% | +12.5 pts [+0.0 ; +25.0] | 100% -> 100% |
| jeu B (jamais vu) | 24 | 50.0% | 50.0% | +0.0 pts | 100% -> 100% |
| **jeux jamais vus, regroupes** | 48 | 47.9% | 54.2% | **+6.2 pts** [+0.0 ; +14.6] | 100 % -> 100 % |

## Ce que cette mesure dit, et ce qu'elle ne dit pas

**Elle dit** que la peur qui avait fait EXCLURE le corps etait mal placee. Le corps verse dans le
MEME index que le tiers 0 faisait perdre l'objectif de reference (son exemple cite `sum_even`, du
vocabulaire de depot) ; pese comme un SECOND champ, il fait GAGNER 3 cas sur 24 objectifs jamais
vus, sans rien couter au banc (87,1 % contre 83,9 %) ni aux abstentions (17/17 hors sujet refuses,
avant comme apres). L'ecart banc / controle se referme : 45,8 % -> 58,3 % sur le jeu ecrit avant
la retouche.

**Elle ne dit pas** que le gain est etabli au seuil de 95 % : sur 48 cas jamais vus le gain est de
**3 cas**, et la borne basse de l'intervalle touche zero (+6,2 pts [0 ; +14,6]). C'est une
DIRECTION, pas une preuve — l'honnetete de ce depot est de l'ecrire plutot que de choisir le jeu
qui l'arrange. Ce qui est etabli sans intervalle : le banc ne perd pas, les abstentions ne bougent
pas d'un cas, et un SEUL parametre a change.

**Elle ne dit pas non plus** que les objectifs reels de l'utilisateur sont mieux servis : sur 6
objectifs plausibles (« ecrire des tests », « corriger un bug », « documenter l'API »...), 2
chargent des procedures avant comme apres. Le seuil d'abstention n'est pas en cause — la mesure
`jio skills --seuil-balaye` et les trois jeux montrent que TOUS les hors sujet portent 0 ou 1 mot
de domaine, et que le seuil de 1 ferait entrer 8 hors sujet sur 17 sans servir un objectif de plus.
Ce qui est repare, c'est la DECOUVERTE : une abstention rend maintenant l'inventaire tier 0
(`jio skills`, `jio_skills` en MCP), au lieu de laisser l'agent croire qu'il n'existe rien.
