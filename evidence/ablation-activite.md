# L'instrument d'ablation : « non distingue » avait deux causes

**La question.** `jio ablation` enleve une brique du harness et compare, sur les **memes**
missions (appariement par tache et par graine), ce qui change. Un rapport precedent a montre
que sur douze leviers, **neuf** ressortaient « NON DISTINGUABLE » avec exactement le meme
profil. Deux causes tres differentes produisent ce meme silence :

* la brique **n'a rien fait** sur ces missions — il faut alors regarder le code ;
* le banc **ne l'a jamais mise a l'epreuve** — il faut alors changer de missions, pas de code.

Un instrument qui repond la meme chose dans les deux cas ne peut pas se tromper, donc ne
prouve rien. Cette preuve enregistre la correction : une **empreinte d'activite** par mission,
lue dans le rapport de mission (jamais instrumentee : un instrument qui modifie ce qu'il
mesure mesure autre chose).

## Ce qui est compte, et ce qui est exclu

Six familles d'observables sont comptees, toutes deja presentes dans le rapport :

| observable | pourquoi il porte un sens |
|---|---|
| `temoins`, `temoins_ok` | ce que la preuve a reellement **execute** — le cœur du harness |
| `votes` | ce que le panel a rendu (une brique peut changer la decision sans changer les voix) |
| `constat:<agent>` | le travail des briques sans ligne a elles : `mutation`, `redteam`, `temoins`, `monde` |
| `exploits`, `integrite_etapes` | ce que le moniteur a cherche, et le journal qu'il a **rejoue** |

Sont **exclus** les compteurs de volume (`usage:*`, `sujet_caracteres`) : ils bougent des
qu'un chemin de code differe, meme quand aucune decision ne change. Mesure a l'origine : sans
ce filtre, `usage:events` variait pour **les douze leviers** (142 -> 104) et l'instrument
declarait « actif » tout le monde — c'est-a-dire personne.

## Ce que l'instrument a ensuite revele : trois leviers retiraient un FANTOME

Une fois l'instrument en place, il a repondu « le banc ne l'exerce pas » sur `memoire`,
`bibliotheque` et `routeur`. La cause exacte etait plus dure que le diagnostic : **le banc ne
construisait pas ces briques**. `jio run` branche la memoire des echecs, la bibliotheque de
temoins et le routeur de confiance (`_attach_learning`) ; le banc d'ablation, lui, les
retirait d'un moteur ou elles n'avaient jamais ete chargees — l'ablation d'un fantome, muette
par construction. Reparation : le banc branche maintenant l'apprentissage sur chaque moteur,
avec **un dossier d'etat par bras** (tous partent du meme vide ; ce qui s'y accumule est le
produit de la trajectoire de CE bras). Deux tests verrouillent le branchement et le nettoyage.

## Resultat mesure — regime par defaut (10 missions, competence 0,35, banc reparé)

```
levier          verdict             activite   ce que le retrait change
preuve          PREUVE              10/10      appels 3,3 -> 2,2 ; livraisons propres 7 -> 0 (p = 0,016)
red-team        PREUVE              10/10      appels 3,3 -> 8,4 ; livraisons propres 7 -> 0 (p = 0,016)
consensus       PREUVE               0/10      la decision change, les voix brutes non
porte           NON DISTINGUABLE     0/10      aucun observable (le banc ne l'exerce pas)
integrite       NON DISTINGUABLE    10/10      journal rejoue : 524 -> 0 pas ; aucune decision bougee
mutation        NON CONCLUANT        2/10      2 constats de mutant
auto-coherence  NON DISTINGUABLE    9/10       journal rejoue : 524 -> 515 ; redondance mesuree
differentiel    NON DISTINGUABLE     0/10      aucun observable
temoins         NON DISTINGUABLE     0/10      normal ici : le banc fournit ses tests, rien a traduire
memoire         NON DISTINGUABLE     0/10      volume seul : 30057 -> 29730 jetons de prompt
bibliotheque    NON DISTINGUABLE     0/10      normal ici : avec oracle fourni, rien n'est a retenir
routeur         NON CONCLUANT       10/10      journal 524 -> 508, constats du panel 4 -> 0 ;
                                               SANS lui : +1 livraison propre (p = 1,0) — a interroger
```

Moteur complet : 9/10 justes · 7 livrees sans reserve · 2 reservees · **1 abstention** — le
systeme refuse de livrer sans preuve, c'est le comportement contractuel.

## Les regimes : quelle mesure reveille quelle brique

| levier | defaut | sans oracle, fidelite 1,0 | sans oracle, fidelite 0,6 |
|---|---|---|---|
| `temoins` | muet (tests fournis) | **PREUVE (perte)**, act 10/10, appels 3,9 -> 1,0 | **PREUVE (perte)**, act 10/10 |
| `bibliotheque` | muet (rien a retenir) | **AGIT 4/10** : sans elle, +4 appels et +4 constats de temoins (re-traduire) | muet (temoins contrefaits : rien de valide a retenir) |
| `routeur` | NON CONCLUANT, act 10/10 | NON CONCLUANT, act 10/10 | NON CONCLUANT, act 10/10, **economise 0,4 appel/mission** |
| `porte`, `differentiel` | muet | muet | muet |
| `memoire` | volume seul | — | muet |

Pour `differentiel`, le chantier de banc a ete fait : les cinq taches archives ont une
specification TOTALE — deux implementations correctes y coincident sur toute entree, donc le
levier ressortait muet sur tout regime (mesure : defaut, sans oracle, competence 0,05 a 0,9).
La sixieme tache, `mean_partial` (volontairement hors du pool par defaut : les releves
archives restent comparables), ajoute ce qui manque — l'oracle se tait sur la liste vide, deux
implementations legitimes divergent (`ZeroDivisionError` contre `0.0`), et le differentiel
sonde les entrees derivees pour avouer le desaccord en constat nomme :

```
jio ablation --taches mean_partial --skill 0.7 --missions 6 --levers differentiel
    differentiel   NON CONCLUANT   act=4/6   constat:divergence 4 -> 0
```

Retirer la brique fait disparaitre les 4 aveux : sans elle, deux candidats a egalite de
preuves sont departages par l'ordre d'arrivee, EN SILENCE.

Restent `consensus` (prouve ailleurs : 8 livraisons propres perdues contre 0, p = 0,0078 —
sa decision n'apparait pas dans les voix) et `porte`, a peine exercee (1 mission sur 10, aux
deux extremes de competence 0,05 et 0,9). La reponse honnete n'est pas « elargir
l'echantillon » : il faut des **missions** ou la confiance deborde — un chantier de banc,
pas un re-reglage.

## Ce que l'instrument refuse d'ecrire

* il se **tait** quand il n'a rien compte : « je n'ai pas regarde » ne s'ecrit pas comme « il
  ne s'est rien passe » (test dedie) ;
* il nomme la **redondance** quand la brique agit sans deplacer un verdict, et ne l'appelle
  jamais « inutile » ;
* il nomme le **cout** quand les ecarts vont **contre** la brique : « une brique qui degrade
  la ou elle agit est un cout, pas une assurance » — lecture appliquee au routeur ici ;
* il ne conseille plus d'**elargir l'echantillon** quand l'activite est identique : la mesure
  dirait la meme chose pendant des heures.

## Rejouer

```sh
jio ablation --missions 10                          # le tableau du regime par defaut
jio ablation --sans-oracle --fidelite 1.0 --missions 6 --levers bibliotheque,temoins,routeur
jio ablation --sans-oracle --fidelite 0.6 --missions 6 --levers temoins,porte,differentiel,memoire,bibliotheque,routeur
jio ablation --taches mean_partial --skill 0.7 --missions 6 --levers differentiel
jio ablation --missions 10 --json                   # les memes nombres, cle par cle
bash scripts/evidence.sh                            # etape 26 : echec si l'instrument se tait
```

Le fichier JSON de cette mesure est `evidence/ablation-activite.json` (regime par defaut).
Les tests qui protegent l'instrument et le banc sont dans `tests/test_ablation.py` (neuf
tests ajoutes : filtre du volume, ordre des ecarts, trois lectures, silence quand rien
n'est compte, branchement de l'apprentissage, nettoyage de l'etat).
