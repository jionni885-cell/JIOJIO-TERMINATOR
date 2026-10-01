# L'instrument d'ablation : « non distingue » avait deux causes

**La question.** `jio ablation` enleve une brique du harness et compare, sur les **memes**
missions (appariement par tache et par graine), ce qui change. Un rapport precedent a montre
que sur douze leviers, **neuf** ressortaient « NON DISTINGUABLE » avec exactement le meme
profil : meme justesse, memes livraisons, memes appels. Deux causes tres differentes
produisent ce meme silence :

* la brique **n'a rien fait** sur ces missions — il faut alors regarder le code, et se
  demander si elle doit rester ;
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
| `constat:<agent>` | le travail des briques qui n'ont pas de ligne a elles : `mutation`, `redteam`, `temoins`, `integrite` |
| `exploits`, `integrite_etapes` | ce que le moniteur a cherche, et le journal qu'il a **rejoue** |

Sont **exclus** les compteurs de volume (`usage:*`, `sujet_caracteres`) : ils bougent des
qu'un chemin de code differe, meme quand aucune decision ne change. Mesure a l'origine : sans
ce filtre, `usage:events` variait pour **les douze leviers** (142 -> 104) et l'instrument
declarait « actif » tout le monde — c'est-a-dire personne.

## Resultat mesure (10 missions, competence 0,35, temoins fournis par le banc)

```
levier          verdict             activite   observations (complet -> sans)
preuve          PREUVE              10/10      33272 -> 27589
red-team        PREUVE              10/10      33272 -> 100990   (10,5 appels/mission au lieu de 3,3)
consensus       PREUVE               0/10      33272 -> 33272    (la decision change, les votes non)
porte           NON DISTINGUABLE     0/10      33272 -> 33272
integrite       NON DISTINGUABLE    10/10      33272 -> 32764    (journal rejoue : 508 -> 0)
mutation        NON CONCLUANT        2/10      33272 -> 33090    (2 constats de mutant)
auto-coherence  NON DISTINGUABLE    10/10      33272 -> 33252
differentiel    NON DISTINGUABLE     0/10      33272 -> 33272
temoins         NON DISTINGUABLE     0/10      33272 -> 33272    (le banc fournit ses tests)
memoire         NON DISTINGUABLE     0/10      33272 -> 33272
bibliotheque    NON DISTINGUABLE     0/10      33272 -> 33272
routeur         NON DISTINGUABLE     0/10      33272 -> 33272
```

**Ce que ce tableau change.** Sept briques ne sont pas exercees par ce banc : `porte`,
`differentiel`, `temoins`, `memoire`, `bibliotheque`, `routeur` — et `consensus`, mais lui est
**prouve** par ailleurs (8 livraisons propres perdues contre 0, p = 0,0078), donc sa ligne
n'est pas un doute : la decision qu'il prend n'apparait simplement pas dans les voix brutes.
Le rapport ne conseille plus d'**elargir l'echantillon** pour ces sept-la : la mesure dirait la
meme chose pendant des heures. Il nomme ce qu'il faudrait a la place : « une mission ou la
brique ait quelque chose a faire, ou un autre mode ».

A l'inverse, `integrite` est le cas qui a corrige la premiere version du compteur : il ne
change aucun verdict, mais son retrait fait passer le journal rejoue de **508 pas a zero** —
la brique **travaille**, et le banc n'a simplement jamais d'exploit a lui donner. La phrase
l'ecrit : « elle agit, et ce qui manque est un echantillon plus grand ou des missions plus
dures — pas une brique a retirer ».

## Ce que l'instrument refuse d'ecrire

* il se **tait** quand il n'a rien compte : « je n'ai pas regarde » ne s'ecrit pas comme « il
  ne s'est rien passe » (test dedie) ;
* il nomme la **redondance** quand la brique agit sans deplacer un verdict, et ne l'appelle
  jamais « inutile » ;
* il nomme le **cout** quand les ecarts vont **contre** la brique : « une brique qui degrade
  la ou elle agit est un cout, pas une assurance » ;
* il ne melange pas volume et sens, et l'ordre d'affichage met les observables de sens en
  premier — sinon l'apercu parlerait de trafic au lieu de parler de travail.

## Rejouer

```sh
jio ablation --missions 10                    # le tableau ci-dessus
jio ablation --missions 10 --json             # les memes nombres, cle par cle
bash scripts/evidence.sh                      # etape 26 : echec si l'instrument se tait
```

Le fichier JSON de cette mesure est `evidence/ablation-activite.json`. Les tests qui
protegent l'instrument sont dans `tests/test_ablation.py` (sept tests ajoutes : filtre du
volume, ordre des ecarts, trois lectures, silence quand rien n'est compte).
