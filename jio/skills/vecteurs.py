"""Similarite SEMANTIQUE pour le routeur : la ressource qui manquait a la porte.

LE DEFAUT QUE CE MODULE REPARE, chiffre. Sur les 113 cas de controle, 24 objectifs du domaine
sont refuses par la porte d'abstention. Ces 24 ne partagent AUCUN mot avec les douze fiches :
l'objectif « prove the fix by running it » ne contient ni « executer », ni « preuve », ni
« verification ». Le lexique ne peut donc rien voir — et six portes candidates ont ete mesurees
avant d'accepter ce constat, toutes au meme niveau. Ce qui manque n'est pas un reglage, c'est une
ressource : de quoi rapprocher deux mots qui ne s'ecrivent pas pareil.

CE QUE CE MODULE APPORTE, et comment il est MESURE. Une table de vecteurs de mots (GloVe, via le
paquet npm `wink-embeddings-sg-100d` ; provenance et construction dans
`scripts/construire-vecteurs.py`) permet deux choses que le lexique ne permet pas :

  * un APPARIEMENT SOUPLE mot a mot : pour chaque mot de l'objectif, la meilleure ressemblance
    avec les mots-cles d'une competence, ponderee par `idf`. Un objectif et une fiche peuvent donc
    se rapprocher sans partager un seul mot ;
  * une FUSION des deux classements (`RRF`, Reciprocal Rank Fusion, Cormack et al. 2009), qui
    garde l'ordre BM25F quand il est sur et le corrige quand il ne voit rien.

Mesure sur les 24 objectifs refuses : la bonne competence etait dans la liste a `@5` 16 fois
(67 %) en BM25F seul, 22 fois (**92 %**) apres fusion, et a `@12` 21 fois (88 %) contre 24 (100 %).
Le gain tient dans CHAQUE jeu separe (McNemar : 6 gagnes, 0 perdu a `@5`). Le premier element, lui,
ne bouge pas : 10/24 avant, 10/24 apres. C'est un gain sur ce qui manquait, pas un deplacement.

TROIS GARDE-FOUS, parce qu'un gain de classement ne doit pas relacher une garantie :

  * la PORTE n'est pas touchee : ce module classe, il ne decide pas. `choisir()` garde son seuil
    et ses invariants (zero corps injecte a tort, zero exploit) ;
  * le fichier de vecteurs est traite comme du contenu NON FIABLE : entete verifiee, longueurs
    bornees, aucune exception ne remonte — une table absente ou abimee rend `None`, et le routeur
    retombe exactement sur son comportement d'avant, en le DISANT (`PROVENANCE_ABSENTE`) ;
  * aucun `pickle` : le format est ecrit et relu ici. Un fichier de donnees qui execute du code
    n'est pas une donnee.
"""

from __future__ import annotations

import gzip
import json
import pathlib
import struct
from array import array
from dataclasses import dataclass, field

from .router import Catalogue, stem

__all__ = [
    "APPARIEMENT",
    "CHEMIN_TABLE",
    "FUSION_K",
    "MAX_MOTS_CLES",
    "POIDS_SEMANTIQUE",
    "TableVecteurs",
    "appariement",
    "raisons_semantiques",
    "charger",
    "classement_semantique",
    "fusionner",
    "table_du_depot",
]

CHEMIN_TABLE = pathlib.Path(__file__).resolve().parent / "vecteurs" / "glove-sg-100d-jio.bin.gz"
MAGIC = b"JIOVEC1\n"
#: Echelle de quantification : l'ecriture multiplie un vecteur NORMALISE par 127 (puis arrondit),
#: la relecture divise le produit scalaire par 127^2. Sans cela, un cosinus vaudrait 16 000 —
#: le nombre serait juste et illisible, et un seuil ecrit a l'oeil deviendrait faux.
ECHELLE_INT8 = 127.0
#: Bornes de securite a la relecture : un fichier hostile ne doit pas fixer la memoire de l'outil.
MAX_MOTS_FICHIER = 200_000
MAX_DIMS = 512
MAX_OCTETS_MOT = 64
#: Nombre de mots-cles retenus par competence pour l'appariement. Mesure au banc : 25 mots
#: suffisent a la porte, 45 classent mieux, 60 n'ajoutent plus rien (cf. evidence).
MAX_MOTS_CLES = 45
#: Poids du classement semantique dans la fusion. Mesure de la courbe entiere dans
#: `evidence/vecteurs-semantiques.md` : a 1,0 la fusion REPARE le milieu de liste mais casse la
#: tete (le premier element juste tombe de 10/24 a 7/24) ; a 0,35 elle garde la tete ET repare le
#: milieu. La valeur n'a pas ete choisie a l'oeil : c'est le plus grand poids qui ne perd aucun
#: premier choix sur les 24 objectifs refuses, et il tient sur le banc comme sur les jeux.
POIDS_SEMANTIQUE = 0.35
#: Constante de la fusion RRF. 60 est la valeur de la litterature (Cormack et al.) : elle a ete
#: gardee telle quelle plutot que reglee sur les jeux de controle — choisir `k` sur la mesure
#: qu'on publie serait ajuster le temoin sur le resultat.
FUSION_K = 60
#: Poids de l'appariement dans le score de classement semantique (comptage borne, pas une mise a
#: l'echelle) : la REPETITION d'un mot utile compte un peu, elle ne domine pas.
APPARIEMENT = 0.5


@dataclass(frozen=True)
class TableVecteurs:
    """La table lue : des radicaux, leurs vecteurs signes, et la provenance du fichier."""

    mots: dict[str, array]
    dims: int
    entete: dict[str, object] = field(default_factory=dict)

    def cosinus(self, gauche: array, droite: array) -> float:
        """Cosinus de deux vecteurs quantifies : produit scalaire, ramene a l'echelle reelle."""
        return sum(a * b for a, b in zip(gauche, droite)) / (ECHELLE_INT8 * ECHELLE_INT8)

    def vecteur(self, mot: str) -> array | None:
        return self.mots.get(stem(mot))


def charger(chemin: pathlib.Path | None = None) -> TableVecteurs | None:
    """Lit la table. Rend `None` — jamais une exception — si elle est absente ou incoherente.

    Un contenu non fiable ne doit pas pouvoir faire tomber l'outil : chaque longueur lue dans le
    fichier est confrontée a une borne avant d'etre utilisee.
    """
    chemin = chemin or CHEMIN_TABLE
    try:
        with gzip.open(chemin, "rb") as flux:
            entete_magique = flux.read(len(MAGIC))
            if entete_magique != MAGIC:
                return None
            brut = flux.read(4)
            if len(brut) != 4:
                return None
            (taille_entete,) = struct.unpack("<I", brut)
            if not 0 < taille_entete < 64 * 1024:
                return None
            entete = json.loads(flux.read(taille_entete).decode("utf-8"))
            dims = int(entete.get("dims", 0))
            declares = int(entete.get("mots", 0))
            if not 0 < dims <= MAX_DIMS or not 0 < declares <= MAX_MOTS_FICHIER:
                return None
            mots: dict[str, array] = {}
            while len(mots) < declares:
                brut = flux.read(2)
                if len(brut) != 2:
                    break
                (longueur,) = struct.unpack("<H", brut)
                if not 0 < longueur <= MAX_OCTETS_MOT:
                    return None  # fichier incoherent : on prefere ne rien rendre qu'un demi-mot
                cle = flux.read(longueur)
                donnees = flux.read(dims)
                if len(cle) != longueur or len(donnees) != dims:
                    break
                mots[cle.decode("utf-8", "replace")] = array("b", donnees)
    except (OSError, EOFError, ValueError, struct.error, json.JSONDecodeError):
        return None
    if not mots:
        return None
    return TableVecteurs(mots=mots, dims=dims, entete=entete)


_TABLE: TableVecteurs | None = None
_CHARGEE = False


def table_du_depot() -> TableVecteurs | None:
    """La table du depot, lue UNE fois (memoire). `None` si elle manque : le routeur le dira."""
    global _TABLE, _CHARGEE
    if not _CHARGEE:
        _TABLE = charger()
        _CHARGEE = True
    return _TABLE


def _idf(catalogue: Catalogue) -> dict[str, float]:
    """`idf` du champ 1 (tiers 0) : c'est lui qui decide, et lui seul definit le domaine."""
    return catalogue.idf


def mots_cles(catalogue: Catalogue, nom: str, table: TableVecteurs, maximum: int = MAX_MOTS_CLES):
    """Les mots les plus DISCRIMINANTS d'une competence, et leurs vecteurs.

    Le tri melange deux choses : `idf` (un mot rare discrimine) et une petite prime de
    repetition (`1 + 0.5 (n - 1)`) — un mot qu'une fiche emploie trois fois compte un peu plus,
    sans qu'une fiche bavarde prenne la main.
    """
    idf = _idf(catalogue)
    defaut = max(idf.values()) if idf else 1.0
    compte = catalogue.termes_de(nom)
    classe = sorted(
        compte,
        key=lambda mot: -(idf.get(mot, defaut) * (1 + APPARIEMENT * (compte[mot] - 1))),
    )
    return [(mot, table.mots[stem(mot)]) for mot in classe[:maximum] if stem(mot) in table.mots]


def appariement(
    catalogue: Catalogue,
    objectif: str,
    cles: dict[str, list[tuple[str, array]]],
    table: TableVecteurs,
) -> dict[str, float]:
    """Score d'appariement SOUPLE : chaque mot de l'objectif cherche son meilleur voisin.

    L'objectif est vectorise mot a mot (pas en moyenne) : c'est ce qui permet a « running »
    d'aller chercher « execution » sans que les autres mots de la phrase ne diluent le signal.
    """
    idf = _idf(catalogue)
    defaut = max(idf.values()) if idf else 1.0
    from .router import jetons

    mots = [(mot, table.mots[stem(mot)]) for mot in jetons(objectif) if stem(mot) in table.mots]
    if not mots:
        return {}
    scores: dict[str, float] = {}
    for nom, voisins in cles.items():
        total = poids = 0.0
        for mot, vecteur in mots:
            poids_mot = idf.get(mot, defaut)
            meilleur = max((table.cosinus(vecteur, v) for _, v in voisins), default=0.0)
            total += poids_mot * meilleur
            poids += poids_mot
        scores[nom] = (total / poids) if poids else 0.0
    return scores


def classement_semantique(catalogue: Catalogue, objectif: str, table: TableVecteurs,
                          cles: dict[str, list[tuple[str, array]]] | None = None):
    """Le classement des competences par appariement semantique, du plus proche au plus loin."""
    if cles is None:
        cles = {doc.nom: mots_cles(catalogue, doc.nom, table) for doc in catalogue.documents}
    scores = appariement(catalogue, objectif, cles, table)
    return sorted(scores, key=lambda nom: (-scores[nom], nom))


def fusionner(liste_bm25: list[str], liste_semantique: list[str], k: int = FUSION_K,
              poids_semantique: float = POIDS_SEMANTIQUE) -> list[str]:
    """Fusion RRF de deux classements : `1/(k + rang)` dans chacun, on additionne.

    Choisie plutot qu'une somme ponderee parce qu'elle ne compare PAS les deux echelles (le score
    BM25 n'a pas d'unite, le cosinus en a une) : elle ne regarde que les rangs. Une competence
    absente d'une liste prend un rang tres mauvais — ne pas la voir du tout revient a la classer
    derniere, pas a l'ignorer.
    """
    rangs: dict[str, float] = {}
    for liste, poids in ((liste_bm25, 1.0), (liste_semantique, poids_semantique)):
        for rang, nom in enumerate(liste, start=1):
            rangs[nom] = rangs.get(nom, 0.0) + poids / (k + rang)
    return sorted(rangs, key=lambda nom: (-rangs[nom], nom))


def raisons_semantiques(nom: str, objectif: str, table: TableVecteurs,
                        voisins: list[tuple[str, array]], combien: int = 2) -> tuple[str, ...]:
    """Pourquoi ce nom est la, en clair : les mots qui ont porte la ressemblance.

    Sans cela, un choix par similarite serait INEXPLIQUABLE — et ce depot refuse un classement
    qu'on ne peut pas expliquer.
    """
    from .router import jetons

    if not voisins:
        return ()
    apports: list[tuple[float, str, str]] = []
    for mot in jetons(objectif):
        vecteur = table.mots.get(stem(mot))
        if vecteur is None:
            continue
        score, cle = max(((table.cosinus(vecteur, v), cle) for cle, v in voisins),
                         default=(0.0, ""))
        if score > 0.30:      # en dessous, la « ressemblance » est du bruit : on ne l'invoque pas
            apports.append((score, mot, cle))
    apports.sort(reverse=True)
    return tuple(f"voisin {mot}~{cle} ({score:.2f})" for score, mot, cle in apports[:combien])
