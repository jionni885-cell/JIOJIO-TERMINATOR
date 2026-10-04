"""Classement des souvenirs — BM25, pas recouvrement de mots.

Pourquoi ce module existe
-------------------------
`FailureMemory.recall()` classait par Jaccard : `|inter| / |union|` sur des ensembles
de mots. Ce score a deux defauts qui grandissent avec la memoire, et c'est
exactement ce qu'on cherche a eviter (une memoire qui grossit doit devenir plus
utile, pas plus bruyante) :

* **aucune ponderation par la rarete.** « mission », « memoire », « patch » pesent
  autant qu'un `F541` ou un `mcnemar_exact`. Or c'est l'identifiant technique qui
  dit que deux echecs sont LE MEME echec ;
* **aucune saturation.** Un souvenir qui repete dix fois le mot « erreur » n'est
  pas dix fois plus pertinent — et une union large (souvenir long) fait baisser
  le score mecaniquement.

BM25 est le classement standard de la recherche d'information (Lucene,
Elasticsearch, `rank_bm25`) : ponderation IDF, saturation de la frequence, et
normalisation par la longueur du document. Trois proprietes voulues ici :

1. **Aucune liste de mots vides.** Le depot est bilingue : une liste de mots vides
   francaise casserait les requetes anglaises et inversement. L'IDF fait le
   travail, dans la langue des donnees, sans liste a maintenir.
2. **Aucune dependance.** Quatre-vingts lignes de Python pur, hors-ligne, sans
   cle API, et lisibles — la reproductibilite prime sur la mode.
3. **Aucune boite noire.** Un score decomposable en `idf x tf-sature`, donc
   explicable dans un rapport ; un plongement vectoriel ne l'est pas.

Le score est rendu **normalise dans [0, 1]** (division par le meilleur score
atteignable pour la requete) pour que le seuil `min_score` de `recall()` garde un
sens : « ce souvenir couvre au moins X % de ce que la requete sait demander ». Un
score brut de BM25 n'est pas comparable d'une requete a l'autre (il depend du
nombre de termes et de leurs IDF), et un seuil sur un score non comparable est un
seuil qui se deplace sans qu'on le sache.
"""

from __future__ import annotations

import math
import re
from collections import Counter

__all__ = ["terms", "idf", "bm25", "jaccard", "normalized_bm25"]

#: Meme decoupage que le reste du noyau : minuscules, et les identifiants
#: techniques (`F541`, `mcnemar_exact`, `o_excl`) restent des jetons entiers.
_TOKEN = re.compile(r"[a-z0-9_]{3,}")

#: Constantes standard (Lucene par defaut) : `k1` borne l'effet de la frequence,
#: `b` dose la normalisation par la longueur. Elles sont ici parce qu'elles sont
#: universellement utilisees, pas parce qu'elles ont ete ajustees sur ce corpus —
#: les ajuster sur un jeu de test le transformerait en jeu d'entrainement.
K1 = 1.2
B = 0.75


def terms(text: str) -> list[str]:
    """Les jetons d'un texte, en gardant les REPETITIONS (BM25 en a besoin)."""
    return _TOKEN.findall((text or "").lower())


def idf(frequence_documentaire: int, total: int) -> float:
    """IDF de Robertson, forme utilisee par Lucene : toujours strictement positive.

    La forme classique `log((N - df + 0.5) / (df + 0.5))` devient NEGATIVE pour un
    terme present dans plus de la moitie des documents : un mot tres frequent
    *retirerait* des points. Le `log(1 + ...)` borne le defaut.
    """
    if total <= 0:
        return 0.0
    df = max(0, min(frequence_documentaire, total))
    return math.log(1.0 + (total - df + 0.5) / (df + 0.5))


def _tf_sature(frequence: int, longueur: int, longueur_moyenne: float) -> float:
    """Le facteur de frequence de BM25 : croissant, borne, et penalise les longs."""
    if frequence <= 0:
        return 0.0
    if longueur_moyenne <= 0:
        return frequence / (frequence + K1)
    denominateur = frequence + K1 * (1.0 - B + B * longueur / longueur_moyenne)
    return frequence * (K1 + 1.0) / denominateur


def jaccard(requete: list[str], documents: list[list[str]]) -> list[float]:
    """Le score REMPLACE par ce module : `|inter| / |union|` sur des ensembles.

    Garde ici comme BRAS TEMOIN : un classement neuf ne vaut que compare a
    l'ancien, sur un meme corpus et dans un meme test. C'est ce que fait
    `tests/test_memory_recall.py` — le jour ou ce temoin disparait, la preuve du
    progres disparait avec lui.
    """
    want = set(requete)
    if not want:
        return [0.0] * len(documents)
    scores: list[float] = []
    for doc in documents:
        have = set(doc)
        if not have:
            scores.append(0.0)
            continue
        scores.append(len(want & have) / len(want | have))
    return scores


def bm25(requete: list[str], documents: list[list[str]], *, k1: float = K1,
         b: float = B) -> list[float]:
    """Score BM25 de chaque document pour la requete. Scores bruts (non normalises)."""
    total = len(documents)
    if not total or not requete:
        return [0.0] * total
    frequences_documentaires: Counter[str] = Counter()
    for doc in documents:
        frequences_documentaires.update(set(doc))
    longueurs = [len(doc) for doc in documents]
    moyenne = sum(longueurs) / total if total else 0.0
    requete_uniques = Counter(requete)
    scores: list[float] = []
    for doc, longueur in zip(documents, longueurs):
        compte = Counter(doc)
        score = 0.0
        for terme, repetitions in requete_uniques.items():
            frequence = compte.get(terme, 0)
            if not frequence:
                continue
            poids = idf(frequences_documentaires.get(terme, 0), total)
            # La repetition du terme DANS LA REQUETE ne doit pas multiplier
            # indefiniment le score d'un meme document : on la borne a `k1 + 1`,
            # la valeur que le facteur de frequence peut lui-meme atteindre.
            repetition_requete = min(repetitions, k1 + 1.0)
            score += poids * repetition_requete * _tf_sature(frequence, longueur, moyenne)
        scores.append(score)
    return scores


def normalized_bm25(requete: list[str], documents: list[list[str]], *, k1: float = K1,
                    b: float = B) -> list[float]:
    """BM25 ramene dans [0, 1] : part du meilleur score atteignable par la requete.

    Le denominateur est `somme des idf des termes de la requete x (k1 + 1)`, soit le
    score d'un document qui contiendrait tous les termes de la requete avec une
    frequence saturante et une longueur moyenne. Le score devient donc lisible :
    « ce document couvre X % de ce que la requete demande », et un seuil dessus
    veut dire la meme chose pour toutes les requetes.
    """
    brut = bm25(requete, documents, k1=k1, b=b)
    total = len(documents)
    if not total:
        return []
    frequences_documentaires: Counter[str] = Counter()
    for doc in documents:
        frequences_documentaires.update(set(doc))
    plafond = sum(
        idf(frequences_documentaires.get(terme, 0), total) * (k1 + 1.0)
        for terme in set(requete)
    )
    if plafond <= 0:
        return [0.0] * total
    return [min(1.0, score / plafond) for score in brut]
