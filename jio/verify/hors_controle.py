"""Les zones qu'un document declare HORS CONTROLE — et pourquoi.

Le besoin, et la raison pour laquelle il n'est pas negociable
------------------------------------------------------------
Un document doit pouvoir RACONTER ses erreurs. Ce depot en est plein : « il a annonce 187 tests
verts quand la suite en comptait 520 », « l'artefact citait `jio verify`, une commande qui
n'existe pas ». Ce sont des faits historiques, pas des affirmations du jour. Si les controles
les prennent pour telles, deux consequences egalement mauvaises :

  * le controle REPARE le recit (`--appliquer` ecrit la valeur vraie du jour a la place du
    chiffre historique) — le document devient un mensonge *par correction automatique* ;
  * ou bien l'auteur supprime le recit, et le depot perd la memoire de ses propres defauts.

La seconde est pire que la premiere. Un depot qui ne peut plus raconter ce qu'il a casse
recommencera a le casser, sans personne pour reconnaitre le symptome.

La reponse : une exemption explicite, ECONOME et TRACABLE
---------------------------------------------------------
Une zone est declaree entre deux marqueurs, et la raison s'ecrit APRES le marqueur d'ouverture —
sur la meme ligne. Trois formes sont reconnues :

    <!-- hors-controle: recit d'un defaut passe -->
    <!-- chiffres:hors-controle: chiffres historiques -->        (forme historique)
    <!-- prose:hors-controle: exemple de sortie d'outil -->

Regles, toutes verifiees par des tests :

  * **la raison est obligatoire** : `raisons_manquantes()` nomme les zones qui n'en portent pas,
    et le rapport d'ensemble les affiche. Une exemption sans raison est presque toujours une
    exemption qu'on ne saura plus justifier six mois plus tard ;
  * **les zones sont DECLAREES, jamais devinees** : aucun controle n'exempte un texte de sa
    propre initiative (`if "exemple" in ligne` est exactement ce qu'on refuse). Ce qui est
    exempte est visible dans le document ;
  * **les zones sont visibles dans le rapport** : `jio coherence` les compte et les nomme. Une
    exemption silencieuse serait un trou dans la porte.

Implementation : on rend un masque de LIGNES et, pour les controles qui travaillent sur des
offsets absolus, `masquer()` qui remplace le texte exempte par des espaces de MEME LONGUEUR.
C'est le point qui compte : retirer des lignes decalerait toutes les positions suivantes, et un
controle qui pointe la mauvaise ligne est pire qu'un controle absent.
"""

from __future__ import annotations

import re

__all__ = [
    "FERME",
    "OUVRE",
    "masquer",
    "raisons",
    "raisons_manquantes",
    "zones",
]

#: Le marqueur d'ouverture. Le prefixe de domaine (`chiffres:`, `prose:`) est facultatif : il
#: sert a dire QUEL controle l'auteur avait en tete, jamais a restreindre l'exemption — une
#: exception qui ne vaut que pour un controle oblige a recopier le meme bloc trois fois.
OUVRE = "hors-controle"
OUVRE_RE = re.compile(r"<!--\s*(?:(?P<domaine>[a-z][a-z0-9_-]*)\s*:\s*)?hors-controle\b(?P<reste>[^>]*)-->")
FERME_RE = re.compile(r"<!--\s*/?\s*(?:(?P<domaine>[a-z][a-z0-9_-]*)\s*:\s*)?hors-controle\b[^>]*-->")
#: Le marqueur de fermeture, exprime pour la documentation et les messages.
FERME = "<!-- /hors-controle -->"


def _raison(reste: str) -> str:
    """La raison ecrite apres le marqueur, ou une chaine vide.

    On tolere `:` ou `-` comme separateur, et on refuse de fabriquer une raison a partir du nom
    de domaine : « chiffres » n'est pas une raison, c'est une etiquette.
    """
    return reste.lstrip(" \t:-—").strip().rstrip(">").strip()


def zones(texte: str) -> tuple[set[int], list[str]]:
    """Rend les numeros de ligne hors controle (1-indexes) et les raisons declarees.

    Une seule implementation pour DEUX usages : ne pas VOIR ces lignes, et ne pas y ECRIRE.
    Deux fonctions separees auraient fini par diverger — et une reparation qui ecrit la ou le
    controle ne regarde pas est un trou invisible.
    """
    # Sans `keepends` : ici on ne lit que le CONTENU des lignes. La version precedente
    # demandait les fins de ligne sans jamais les utiliser ; `jio mutants` l'a designee comme
    # survivante, et un mutant equivalent n'apprend rien — la bonne reponse est de supprimer
    # la ligne inutile, pas d'ecrire un test de theatre pour la defendre.
    lignes = texte.splitlines()
    masquees: set[int] = set()
    raisons: list[str] = []
    dedans = False
    for indice, ligne in enumerate(lignes, start=1):
        if FERME_RE.search(ligne) and not OUVRE_RE.search(ligne):
            dedans = False
            masquees.add(indice)
            continue
        ouverture = OUVRE_RE.search(ligne)
        if ouverture and not dedans:
            dedans = True
            masquees.add(indice)
            raisons.append(_raison(ouverture.group("reste")))
            continue
        if dedans:
            masquees.add(indice)
    return masquees, raisons


def raisons(texte: str) -> list[str]:
    """Les raisons declarees, dans l'ordre du document."""
    return zones(texte)[1]


def raisons_manquantes(texte: str) -> list[int]:
    """Les lignes d'ouverture qui declarent une exemption SANS dire pourquoi."""
    trouves: list[int] = []
    for indice, ligne in enumerate(texte.splitlines(), start=1):
        ouverture = OUVRE_RE.search(ligne)
        if ouverture and not _raison(ouverture.group("reste")):
            trouves.append(indice)
    return trouves


def masquer(texte: str, *, caractere: str = " ") -> str:
    """Remplace le contenu des zones exemptees par des espaces, longueur PRESERVEE.

    C'est la forme utilisable par les controles qui travaillent sur des offsets absolus
    (`jio claims` enregistre la position de chaque affirmation) : masquer au lieu de retirer
    garde chaque position intacte, donc chaque message continue de pointer la bonne ligne.

    Les marqueurs eux-memes sont masques aussi : ils ne sont pas du texte a verifier.
    """
    hors, _ = zones(texte)
    lignes = texte.splitlines(keepends=True)
    sortie: list[str] = []
    for indice, ligne in enumerate(lignes, start=1):
        if indice in hors:
            sortie.append(caractere * len(ligne.rstrip("\n")) + ("\n" if ligne.endswith("\n") else ""))
        else:
            sortie.append(ligne)
    return "".join(sortie)
