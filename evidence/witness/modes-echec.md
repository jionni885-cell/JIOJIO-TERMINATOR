# Le mode d'echec du traducteur de regles

`jio/spec/witness.py` demande a un modele de traduire les regles de la mission en
tests executables. Cette traduction est une **competence**, et elle peut echouer.
Un mode d'echec qu'on ne sait pas simuler ne doit pas etre compte comme simule :
sinon la borne basse qu'on annonce n'est pas la borne basse qu'on mesure.

`jio/bench/temoins.py` fabrique donc, pour CHAQUE regle du banc, la reponse d'un
traducteur qui se trompe — la **contrefacon**. Trois formes, essayees dans cet
ordre, toutes verifiees par `tests/test_witness.py` : la contrefacon doit etre

* **satisfaite par une implementation fausse** (sinon elle ne mesure pas la faute) ;
* **refusee par l'implementation correcte** (sinon elle ne mesure rien du tout).

## 1. La mauvaise valeur

> regle : « somme des pairs de `[1, 2, 3, 4, 5, 6]` = 12 »
> traduction fidele : `assert sum_even([1, 2, 3, 4, 5, 6]) == 12`
> contrefacon : `assert sum_even([1, 2, 3, 4, 5, 6]) == 21`

21 est ce que rend le distracteur « oublie le filtre ». Le modele a encode
l'attente d'une implementation fausse : il accuse donc l'implementation correcte.

## 2. Le contrat d'erreur lu a l'envers

> regle : « une division par zero leve `ValueError` »
> traduction fidele : `try: safe_divide(1, 0) except ValueError: ok = True`
> contrefacon : « ne doit pas lever » — `except Exception: ok = False`

C'est le bug d'erreur silencieuse, le plus courant de tous : la regle est lue
comme une permission d'echouer en silence.

## 3. La regle lue a l'envers (negation generique)

> regle : « 2 et 3 sont premiers »
> traduction fidele : `assert is_prime(2) and is_prime(3)`
> contrefacon : `assert not (is_prime(2) and is_prime(3))`

Cette forme couvre tout ce que les deux premieres ne couvrent pas (assertions
composees, `isinstance`, refus). Elle est constructible pour **22 regles sur 22**
du banc — l'echelle de fidelite porte donc sur la totalite des regles, pas sur un
sous-ensemble commode.

## Ce que la mesure en fait

`scripts/evidence.sh` (etape 3 bis) fait tourner le moteur sans aucun oracle, a
budget egal (3 candidats + 1 appel de traduction), a trois fidelites :

| fidelite du traducteur | livre juste | abstention | faux + reserve | **sans reserve** |
|---|---|---|---|---|
| 100 % | 5/5 | 0 | 0 | **0** |
| 50 % | 2/5 | 3 | 0 | **0** |
| 0 % | 0/5 | 5 | 0 | **0** |

Deux choses a lire dans ce tableau :

* un traducteur faux ne fait pas livrer faux — il fait **renoncer**. Le cout d'une
  mauvaise traduction est une livraison perdue, jamais une erreur livree ;
* la derniere colonne est la seule qui doive rester nulle : une erreur livree
  **sans que rien ne le dise**.

Le garde-fou tient en une phrase : un temoin que **tous** les candidats echouent ne
prouve rien sur eux. Soit il est faux, soit tous les candidats sont faux, et rien ne
permet de trancher. La regle est donc declaree NON PROUVEE — le temoin ne peut ni
accuser ni innocenter — et son echec n'est pas efface du verdict.

### Une erreur corrigee, et elle vaut la peine d'etre racontee

La premiere version du garde-fou faisait autre chose : elle EFFACAIT l'echec du
verdict (les temoins concernes etaient reclassees en avertissements). Consequence
mesuree au banc : un artefact **faux** etait livre avec une simple reserve, la ou
l'abstention etait la bonne sortie. « Non prouve » etait devenu « livre ». La
mesure a montre la faute, la regle est desormais : **on ne prouve rien avec un
temoin que personne ne passe — mais on n'efface pas non plus ce qu'il signale.**
