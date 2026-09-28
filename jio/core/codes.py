"""Les codes de sortie de `jio` : une doctrine, un seul endroit.

POURQUOI CE MODULE EXISTE
-------------------------
Les codes etaient poses commande par commande, et deux d'entre eux se confondaient :

  * `jio run` rendait **1** aussi bien pour « livre AVEC une reserve nommee » que pour
    « ABSTENTION : rien n'a pu etre prouve ». Un appelant — script, hook, agent — ne pouvait
    donc pas distinguer « j'ai un livrable, avec une reserve a lever » de « je n'ai rien, et il
    me manque quelque chose ». Ce sont deux actions differentes.

LA DOCTRINE, en quatre codes, chacun avec l'ACTION qu'il demande
----------------------------------------------------------------
    0  OK          ce qui etait demande est fait, et prouve.
    1  PROBLEME    quelque chose est faux, ou une reserve doit etre levee. Il y a un defaut a
                   corriger : un document falsifie, un artefact divergent, une mission
                   livree avec une reserve nommee.
    2  INDETERMINE on ne peut pas conclure. Il manque de quoi conclure : un fournisseur, une
                   preuve, une entree suffisante. Ce n'est pas une faute — c'est une absence,
                   et l'appelant sait QUOI fournir.
    3  EN_ATTENTE  une reponse HUMAINE est necessaire avant de commencer (`jio run --strict`
                   avec des questions bloquantes). Aucun travail n'a ete fait, et c'est le
                   bon resultat : travailler sur la mauvaise question coute plus cher.

Le code 3 existe deja dans le code ; il est declare ici pour la meme raison que les autres :
un code de sortie sans action associee n'est qu'un nombre.

Pourquoi 2 pour l'abstention. `ABSTAINED` est un resultat de premiere classe dans ce projet :
le moteur dit qu'il ne peut pas prouver. Le ranger avec les defauts le transformerait en faute,
alors que la bonne action de l'appelant n'est pas de corriger mais de FOURNIR. `argparse` utilise
deja 2 pour un usage incorrect : c'est la meme famille — la commande n'a pas pu travailler.

Pourquoi une reserve vaut 1. Une reserve n'est pas une accusation, mais ce n'est pas un quitus :
quelqu'un doit la lever ou la declarer (meme regle que `--strict`, documents : « en CI, elle doit
etre levee ou declaree »). Un agent qui enchaine sur un 0 avec reserve ne saurait jamais qu'il
reste quelque chose a faire.


LIRE UN ETAT VIDE, CE N'EST PAS MESURER DANS LE VIDE
----------------------------------------------------
Trois commandes rendaient 0 pour deux situations OPPOSEES. La distinction, ecrite ici pour
qu'une modification future ne la « repare » pas dans le mauvais sens :

  * **lire un etat vide rend 0** — `jio memory` sans souvenir, `jio trust` sans observation,
    `jio trace` sans journal dans le depot. L'etat vide EST la reponse a la question posee
    (« qu'y a-t-il en memoire ? » -> « rien »). Rendre 2 ferait echouer une CI sur une base
    saine qu'on vient de creer ;
  * **mesurer ou verifier sans matiere rend 2** — `jio mutants` sans dossier `tests/`,
    `jio trace` sur un chemin inexistant, `jio sorties --document` introuvable. La mesure est
    IMPOSSIBLE, pas bonne : un « 0 probleme » sur du vide ferait passer une CI pour un succes
    alors qu'aucun controle n'a eu lieu.

Le critere est donc la QUESTION de la commande : « que contient cet etat ? » (0) contre
« cet artefact est-il bon ? » (2 quand il n'y a pas d'artefact a juger).
"""

from __future__ import annotations

from ..core.types import MissionStatus

__all__ = ["OK", "PROBLEME", "INDETERMINE", "EN_ATTENTE", "CODES", "code_de_mission", "TABLE"]

OK = 0
PROBLEME = 1
INDETERMINE = 2
EN_ATTENTE = 3

#: Tous les codes que `jio` peut rendre. Un test lit ce tuple et verifie qu'aucune commande
#: n'en invente un autre : la doctrine ne doit pas se perdre dans un `return 4` isole.
CODES: tuple[int, ...] = (OK, PROBLEME, INDETERMINE, EN_ATTENTE)

#: La correspondance etat -> code, ecrite une fois et lue par la documentation, les tests et
#: les commandes. Une table, pour qu'une modification se voie au lieu de se deduire.
TABLE: dict[MissionStatus, int] = {
    MissionStatus.DELIVERED: OK,
    MissionStatus.DELIVERED_WITH_RESERVATION: PROBLEME,
    MissionStatus.ABSTAINED: INDETERMINE,
    MissionStatus.FAILED: PROBLEME,
}

#: Ce que l'appelant doit FAIRE, par code. C'est la partie utile : un code sans action associee
#: n'est qu'un nombre.
ACTION: dict[int, str] = {
    OK: "rien : le travail est fait et prouve.",
    PROBLEME: "corriger, ou lever la reserve nommee dans le rapport.",
    INDETERMINE: "fournir ce qui manque (preuve, fournisseur, entree) puis relancer.",
    EN_ATTENTE: "repondre aux questions essentielles, puis relancer.",
}


def code_de_mission(statut: MissionStatus) -> int:
    """Le code de sortie d'une mission. Un etat inconnu est une erreur de programmation, pas un
    code par defaut : on le dit, au lieu de rendre un nombre qui n'a pas ete decide."""
    try:
        return TABLE[statut]
    except KeyError:  # pragma: no cover - garde-fou de developpement
        raise ValueError(f"etat de mission sans code de sortie declare : {statut!r}") from None
