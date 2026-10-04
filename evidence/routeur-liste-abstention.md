# Ce que le routeur rend quand il dit NON : la liste classée

- **date** : 2026-10-01
- **question** : quand la porte d'abstention se ferme, que reçoit l'agent ?
- **population** : les **24 objectifs du domaine que la porte refuse**, sur les 113 cas jamais vus
  des quatre jeux de contrôle · **hasard** : 1/12 = 8 % (12 compétences)
- **reproductible par** : `jio skills --controle`, `scripts/diagnostic-routeur.py liste`,
  `scripts/experience-routeur.py`, `scripts/experience-classement.py`

## La bonne compétence est-elle dans la liste ?

| liste rendue | cas justes | taux | IC95 (Wilson) | rapport au hasard |
| --- | ---: | ---: | --- | ---: |
| premier élément | 10/24 | 42 % | [24 % ; 61 %] | **5,0×** |
| deux premiers | 11/24 | 46 % | [28 % ; 65 %] | 5,5× |
| trois premiers | 14/24 | 58 % | [39 % ; 76 %] | 7,0× |
| **cinq premiers** (retenu) | 16/24 | 67 % | [47 % ; 82 %] | 8,0× |
| inventaire complet (12) | 21/24 | 88 % | [69 % ; 96 %] | 10,5× |

**Ce que ce tableau décide** : la liste est rendue à **cinq** éléments. Trois à cinq fait gagner
9 points de « la bonne réponse est visible » pour une quinzaine de jetons de plus (des noms et
des scores, jamais des corps de compétence). Au-delà, on retombe sur l'inventaire complet, qui
n'est **pas classé** — et un inventaire non classé vaut le hasard pour un premier choix.

**Ce qu'il ne dit pas** : l'intervalle de confiance de la première ligne est large
([24 % ; 61 %]) parce que la population est petite — 24 cas. Le chiffre qui résiste à
l'intervalle est le **rapport au hasard** (5×), pas le taux. Et la liste n'est pas une décision :
le routeur ne prétend pas qu'une procédure s'applique, il montre ce qu'il a trouvé de moins
éloigné, dans un ordre explicable (`pourquoi : ...`).

## Ce qui n'a PAS été touché, et pourquoi

La porte et le classement sont **inchangés** : ce fichier documente ce que le routeur rend, pas
un nouveau réglage. Deux campagnes de mesures ont été menées avant, et toutes deux ont conclu au
plateau :

| levier essayé | résultat | décision |
| --- | --- | --- |
| **six portes d'abstention** : prose des corps dans la preuve, lexique ET autre source, 2 mots dont un du lexique, pondération, idf fort… | identiques à la porte actuelle, ou pires (jusqu'à −3 justes) | **écartées** : les objectifs refusés ne partagent *aucun* mot avec le corpus (« prove the fix by running it ») — aucun enrichissement de vocabulaire ne peut les sauver |
| **seconde porte par le lexique** (≥ 1 mot) | charge **3 hors-sujet sur 8 du banc** | **écartée sur le banc**, avant même de regarder les jeux de contrôle — la méthode a fonctionné |
| **seconde porte par le score** | positifs refusés : médiane 5,96 · hors-sujet refusés : médiane 1,30 mais **max 7,07** | **refusée par protocole** : elle serait sélectionnée sur les jeux de contrôle, donc ajustée sur eux |
| **12 variantes de classement** (BM25F canonique, poids du corps 0,5→2,0, idf fusionné, répétition des champs courts 1→5) | meilleur gain **+2 cas sur 113**, toutes avec régression sur le banc (27/31 → 22-26/31) | **écartées** : le classement est à son plateau |

Le critère d'acceptation avait été déclaré **avant** la mesure : améliorer le total des quatre
jeux **sans** dégrader le banc. Aucune variante ne le passe — et c'est un résultat en soi.

## Ce qui a changé dans le produit

- `jio skills "<objectif>"` : l'abstention rend la **liste classée à cinq** (nom, catégorie, score,
  et *pourquoi*), puis l'inventaire complet, puis les deux sorties de secours. Le JSON expose
  `proches` **et** `tier0`, et `choix` reste vide — la porte n'a pas bougé.
- `jio_skills` (MCP) : la même liste, avec la même mesure citée, pour qu'un agent qui passe par
  MCP soit servi exactement comme celui qui passe par le shell.
- Le début de la liste **ne dépend pas de sa longueur** (24/24 préfixes identiques sur les cas
  refusés) : « montre-moi 3 » et « montre-moi 5 » donnent les mêmes trois premiers. Sans cela,
  un agent qui compare deux sorties ne saurait plus laquelle croire — c'est vérifié par un test.
