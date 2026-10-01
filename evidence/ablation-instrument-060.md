# Ablation : réparer l'INSTRUMENT, pas seulement le candidat

**Régime de mesure** (le chiffre ne se lit pas sans lui) : `jio ablation --missions 15
--taches 5 --graines 3 --skill 0.4 --sans-oracle --fidelite 0.6 --levers preuve,red-team,
consensus,porte,integrite,mutation,auto-coherence,differentiel`.

Autrement dit : aucun oracle fourni par la mission, le modèle simule écrit lui-même les témoins,
et **40 % de ces témoins sont contrefaits** — c'est-à-dire le régime réel d'une mission sans
oracle, celui où il n'y a rien à rattraper si le harness ne rattrape pas l'instrument.

Fichier machine : `evidence/ablation-instrument-060.json` · progression : `.progres.txt` ·
durée mesurée : 3 min 48 s pour 135 missions.

## Le chiffre qui juge l'axe

| | témoins naïfs (avant) | témoins auto-validés (après) |
|---|---|---|
| missions justes | 9 / 15 | **13 / 15** |
| livrées **sans** réserve | 0 | 0 |
| livrées **avec** réserve nommée | 0 | **15 / 15** |
| **abstentions** | **15 / 15** | **0 / 15** |
| **erreurs silencieuses** | **0** | **0** |
| appels par mission | 3,7 | 5,2 |
| leviers distinguables | 0 | **1** (`preuve`, p = 0,031) |

Lecture. Le moteur ne s'abstenait pas par prudence : il s'abstenait parce que **l'instrument
fourni mentait** et qu'il n'avait aucun moyen de le lui dire. Un témoin qui ne peut pas échouer
ne prouve rien ; un moteur qui refuse tous les témoins ne peut rien livrer. Une fois les témoins
**exécutés avant d'être crus** (le test doit passer sur la référence fournie avec lui et échouer
sur sa contrefaçon), l'abstention tombe à zéro et les missions justes montent de 9 à 13.

Le levier `preuve` devient **mesurable** : sans lui, 6 missions justes sur 15 en moins
(40 points, IC95 [15 ; 65], p = 0,031 apparié exact). Il était « NON DISTINGUABLE » dans les deux
régimes précédents, non parce qu'il était inutile, mais parce que l'instrument brouillait la
mesure.

## L'invariant, et la régression que le banc a attrapée

`erreurs silencieuses = 0` dans **les deux** colonnes : le progrès n'a pas été acheté en
relâchant l'hypothèse. Ce chiffre a failli ne pas tenir — et c'est le banc qui l'a vu.

La première version du contrôle refusait **trop tôt**. Une règle dont l'instrument était refusé
n'avait plus de témoin du tout, et plus aucun mécanisme ne la déclarait non couverte :

* mesure, sur `safe_divide` (graine 0, même régime) : témoins de `R-003` et `R-004` refusés par
  exécution, `R-001` en aveu, **un seul** témoin valide sur quatre règles ;
* la mission est repartie **`delivered` — sans réserve — avec un artefact FAUX** ;
* cause : l'ancien régime *acceptait* ces témoins, l'artefact les ratait, et le mécanisme
  « témoin que personne ne passe » déclenchait la réserve. En refusant l'instrument plus tôt,
  on avait supprimé ce signal.

Correction, même doctrine : une règle dont l'instrument est **refusé** n'a aucun témoin ⇒ elle
est déclarée **NON COUVERTE** dans le rapport, et la livraison porte la réserve. Après
correction, la même mission rend `delivered_with_reservation`, et le chiffre
`erreurs silencieuses` reste à **0**. Verrouillé par
`tests/test_instrument_auto_valide.py::test_une_regle_dont_l_instrument_est_REFUSE_ne_part_pas_SANS_RESERVE`.

## Ce que la mesure a coûté

**5,2 appels par mission au lieu de 3,7** (+41 %). Ce coût est un coût d'**instrument**, pas de
candidat : deux exécutions en bac à sable par témoin, plus **une** passe de réparation bornée par
témoin refusé. Il ne dépend pas de la taille du modèle et ne peut pas boucler.

## Leviers non distinguables sur ce banc (et pourquoi ce n'est pas un verdict)

`red-team` (p = 0,5, 11/15 sans lui), `consensus`, `porte`, `integrite`, `mutation`,
`auto-coherence`, `differentiel` : NON DISTINGUABLE **dans ce régime**. Le régime est choisi pour
éprouver la traduction des règles (`--fidelite 0,6`) ; il ne fournit pas les conditions où ces
leviers peuvent payer. Un levier mesuré dans un régime où il ne peut rien faire n'est pas un
levier inutile : c'est une mesure inadaptée — et c'est écrit ici pour que personne ne lise ce
tableau comme un classement.

## Reproduction

```sh
jio ablation --missions 15 --skill 0.4 --sans-oracle --fidelite 0.6 \
  --levers preuve,red-team,consensus,porte,integrite,mutation,auto-coherence,differentiel --json
```

## Dépôts utilisés

* [`karpathy/nanoGPT`](https://github.com/karpathy/nanoGPT) et
  [`karpathy/minGPT`](https://github.com/karpathy/minGPT) — architecture du décodeur local
  (self-attention causale, embeddings de position appris, tête de langage), utilisée pour la
  mesure sur modèle réel (`scripts/modele-local/`).
* [`pytorch/pytorch`](https://github.com/pytorch/pytorch) — seule dépendance d'exécution du
  modèle local, installée depuis PyPI (2.14.1).
