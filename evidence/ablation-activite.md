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
sa decision n'apparait pas dans les voix) et `porte`.

## La porte : le filtre de decision, et sa lecture qui a failli tromper l'instrument

`--correlee` (panel a biais partage : le cas « meme modele partout ») donne a la porte le
regime ou elle a quelque chose a filtrer. Mesure : son retrait ne change AUCUN observable de
mission, mais deplace les livraisons (0 contre 1 en livraisons propres). La premiere lecture
de l'instrument disait alors « le banc ne l'exerce pas : aucune puissance d'echantillon ne
conclura » — **faux**, et la faute est instructive : la porte est un FILTRE DE DECISION, elle
agit sur livrees/reservees/abstentions (les colonnes du verdict), pas sur le travail de la
mission. L'instrument distingue maintenant la quatrieme lecture :

```
la brique est un FILTRE DE DECISION : elle n'agit sur aucun observable de mission, mais son
retrait deplace les livraisons (0 contre 0, livraisons propres 0 contre 1). C'est son
travail — la decision fait partie de ce qu'elle gouverne. `--missions` peut trancher :
chaque dissociation supplementaire rapproche du seuil.
```

Deux observables de decision ont aussi rejoint l'empreinte : la **composition des votes**
(`votes_pass`/`votes_fail`/`votes_abstain` — « 5 voix » ne dit pas si le panel a statue a
l'unanime ou a une voix) et la sentinelle **`avis_en_phase`** (la decision retenue suit-elle
le vote majoritaire ? c'est l'observable du consensus ; un test unitaire la verrouille sur
une decision qui contredit sa majorite).

## La sonde decisive : 90 missions, et la porte sort COÛT MESURÉ

`jio ablation --correlee --skill 0.3 --missions 45 --levers porte` (90 missions appariees) :

```
porte   COUT MESURE   b_propre/c_propre = 0/6 · McNemar exact p = 0.0312
        complet : 38/40 justes · 19 livrees · 19 reservees · 0 SILENCIEUSE · 7 abstentions
```

Retirer la porte rend les livraisons PLUS propres en regime correle (6 gagnees contre 0
perdues), et la securite ne bouge pas (zero erreur silencieuse des deux cotes). C'est la
premiere brique dont le retrait AMELIORE une metrique avec un p significatif. Le rapport
ecrit « A justifier, ou a interroger » et ne conclut pas « supprimez » : le cout mesure est
celui du fail-closed face a un panel corrèle — il se paie en livraisons retenues qui se
reveleont justes. La meme porte vaut ce qu'elle coute quand la confiance ment (fournisseurs
reels), et `jio learn` fournit les points de calibration pour l'ajuster au lieu de la croire.
Ce chiffre est un RESULTAT DE MESURE, pas une decision : la decision attend son humain.

## Ce que la grille ne peut toujours pas dire

`porte` reste NON CONCLUANTE en corrèle a cette taille (1 dissociation pour 6 requises) —
mais pour la premiere fois, elargir `--missions` est la BONNE action, et l'instrument le dit.
`consensus` n'a pas besoin de cette grille : sa preuve est ailleurs et tient.

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
jio ablation --correlee --skill 0.3 --missions 6 --levers porte   # le filtre de decision
jio ablation --correlee --skill 0.3 --missions 45 --levers porte  # COUT MESURE (p = 0.0312)
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
