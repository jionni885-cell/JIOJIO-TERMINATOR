# La similarité sémantique : ce qu'elle répare, et les deux choses qu'elle ne réparera pas

- **date** : 2026-10-01 · **table** : 11 000 radicaux, 100 dimensions, 0,88 Mo
- **preuve appariée** : `evidence/vecteurs-semantiques.json` (rejouable :
  `python scripts/mesure-vecteurs.py --json`)
- **source** : `wink-embeddings-sg-100d` 1.1.0 — paquet npm (MIT) de vecteurs dérivés de
  **GloVe** (Stanford, PDDL, domaine public), empreinte du paquet
  `2d1bea7f…647c`, construction par `scripts/construire-vecteurs.py`

## Pourquoi cette brique existe

Le routeur a un plafond **mesuré** : sur les 113 cas jamais vus, **24 objectifs du domaine sont
refusés** par la porte, et ces 24 ne partagent **aucun mot** avec les douze fiches. Six portes
candidates et douze variantes de classement ont été mesurées avant d'accepter ce constat : ce qui
manquait n'était pas un réglage, mais une **ressource** capable de rapprocher deux mots qui ne
s'écrivent pas pareil. C'est cette ressource, et rien d'autre, que ce fichier met en face de ses
résultats — y compris des résultats négatifs.

## 1. Une porte sémantique : **IMPOSSIBLE** (mesuré)

Un seuil sur la ressemblance pourrait-il remplacer la porte lexicale ? Non — les deux populations
se **recouvrent** :

| population | n | ressemblance du meilleur | contraste (meilleur − médiane) |
| --- | ---: | --- | ---: |
| objectifs du domaine refusés | 24 | min 0,496 · médiane 0,713 · **max 0,806** | médiane 0,101 |
| hors sujet | 30 | min 0,367 · médiane 0,619 · **max 0,998** | médiane 0,090 |

Un hors sujet atteint **0,998** quand un objectif du domaine refuse plafonne a **0,806** : tout
seuil qui accepterait les 24 ferait entrer des hors sujet. Le **contraste** (ecart au median des
douze competences, qui ne depend d'aucune constante absolue) ne separe pas davantage : 0,101
contre 0,090. Conclusion : la porte reste **lexicale**, et la ressemblance ne decide rien.

## 2. Réordonner toute la liste (RRF) : **ÉCARTÉ**

Fusion RRF (Cormack et al., k = 60) du classement BM25F et du classement sémantique :

| population | BM25F + MMR | après fusion |
| --- | --- | --- |
| 24 objectifs refusés | @1 **10** · @3 14 · @5 16 · @12 21 | @1 **9** · @3 15 · @5 19 · @12 24 |
| banc (31 positifs) | @1 **27** · @3 30 · @5 30 · @12 31 | @1 **22** · @3 30 · @5 30 · @12 31 |

La fusion **gagne au milieu** (jusqu'à +3 au cinquième rang) et **perd la tête** : 10 → 9 sur les
refusés, et surtout 27 → **22** sur le banc. Or la tête est ce qu'un agent lit d'abord, et le
premier élément est le chiffre publié. Critère déclaré avant la mesure : améliorer sans dégrader.
Il n'est pas atteint → **rien n'est retenu de cette variante**, et c'est écrit ici pour ne pas la
refaire.

## 3. Compléter une liste trop courte : **RETENU** (domination stricte)

`proches()` ne rend que les compétences **marquées** par BM25F. Sur les 24 objectifs refusés,
**5 listes n'avaient que 1 à 3 éléments** — alors que l'en-tête annonçait « LES PLUS PROCHES (5) » :
l'outil mentait sur sa propre sortie. La tête est gardée **telle quelle**, et la ressemblance ne
sert qu'à ordonner les places laissées vides.

| population | avant | après complétion |
| --- | --- | --- |
| 24 objectifs refusés | @1 10 · @3 14 · @5 16 · @12 21 | @1 10 · @3 14 · @5 **17** · @12 **24** |
| 113 cas jamais vus | @1 56 · @3 86 · @5 92 · @12 107 | @1 56 · @3 86 · @5 **93** · @12 **112** |
| banc (31 positifs) | @1 27 · @3 30 · @5 30 · @12 31 | **inchangé** |

Aucune métrique ne baisse, sur aucune des trois populations : c'est une **domination**, pas un
compromis. La propriété achetée est nette : quand la porte se ferme sur un objectif du domaine, la
compétence qu'un humain chargerait est **toujours** dans la liste complète (**24/24**, contre
21/24 sans la table) — un agent qui demande plus de cinq éléments ne peut plus tomber sur une liste
où la bonne réponse manque.

## Ce que la complétion N'EST PAS

- Elle ne **charge** rien : aucun corps de compétence n'entre dans le contexte, la porte n'est pas
  touchée ; `choix` reste vide dans le JSON. La ressemblance ordonne des trous.
- Elle n'est pas silencieuse : un élément ajouté a `score 0.0`, une `proximite` (échelle 0..1) et
  la raison **« aucun mot commun — voisin X~Y »**. Un élément marqué par le lexique n'a pas de
  `proximite` du tout (`null` = « pas mesurée », jamais « nulle »). La CLI et le serveur MCP
  annoncent le partage : « N élément(s) MARQUÉ(S) par le lexique, M AJOUTÉ(S) par RESSEMBLANCE ».
- Elle **ajoute du bruit sur les hors sujet** : un objectif sans aucun mot du domaine reçoit cinq
  lignes à 0,48–0,50, sans information. C'est mesuré et assumé — le tri par **contraste** a été
  essayé pour les écarter, il ne sépare pas davantage (0,090 chez les hors sujet contre 0,101 chez
  les objectifs du domaine). Le bruit est **étiqueté**, pas caché.

## Le compromis de taille (mesuré avant de choisir)

| radicaux retenus | fichier | bonne réponse dans la liste complète (24 refusés) |
| ---: | ---: | --- |
| 3 000 | 0,24 Mo | 22/24 |
| 6 000 | 0,47 Mo | 23/24 |
| **11 000** | **0,88 Mo** | **24/24** |

11 000 est retenu : c'est la taille où la propriété « jamais absente » devient vraie sur toute la
population. La courbe est écrite ici pour qu'un futur changement se juge sur elle, et pas sur une
intuition de taille de fichier.

## Si la table disparaît

Une copie partielle, un clone superficiel ou un fichier abîmé laissent le routeur **exactement**
comme avant : `charger()` ne lève jamais, toute longueur lue est bornée, l'en-tête est vérifié, et
`proximite == null` dit l'absence au lieu de la faire deviner. Quatre formes d'abus sont couvertes
par un test (en-tête inconnu, troncature, dimensions absurdes, longueur de mot incohérente).
