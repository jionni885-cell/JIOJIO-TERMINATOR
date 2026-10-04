"""Le CLASSEMENT : variantes mesurees sur le banc (reglage) puis sur les quatre jeux (verification).

La porte d'abstention est un plafond mesure (`scripts/experience-routeur.py` : six portes
candidates, six fois le meme resultat). Ce qui reste, c'est la qualite du classement la ou la
porte OUVRE — la seule chose qu'une retouche peut ameliorer sans inventer un signal qui n'existe
pas dans le texte.

Variantes, toutes implementees SANS toucher au depot (copie profonde du catalogue) :

  R0   l'etat actuel : deux champs satures SEPAREMENT puis additionnes (POIDS_CORPS = 0,75) ;
  R1   BM25F canonique (Robertson & Zaragoza) : les frequences des deux champs sont combinees
       AVANT la saturation, avec une normalisation de longueur par champ ;
  R1b  variantes du poids du corps dans R1 : 0,5 / 1,0 / 1,5 / 2,0 ;
  R2   repetition des champs courts du tiers 0 (nom, tags) : 1, 2, 3, 4, 5 ;
  R3   idf : par champ (etat actuel) contre idf pris sur le MAXIMUM des deux champs.

CE QUI EST MESURE : le premier choix du classement SEUL, sans porte d'abstention. La porte est
un objet separe, deja mesure ; la melanger ici rendrait impossible de dire d'ou vient un gain.

CRITERE D'ACCEPTATION, declare AVANT de lancer : une variante est retenue si elle ameliore le
TOTAL des quatre jeux sans degrader le banc. Un gain sur le banc seul est ecarte — le banc est
sature (27/31) et n'a plus de pouvoir de discrimination.
"""

from __future__ import annotations

import copy
import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

import jio.skills.router as R  # noqa: E402
from jio.skills import banc as B  # noqa: E402
from jio.skills.controle import JEUX  # noqa: E402

BASE = copy.deepcopy(R.catalogue_du_depot())

JEUX_MESURE: list[tuple[str, list[tuple[str, str, str]]]] = [
    (j.nom, list(j.cas)) for j in JEUX
]
JEUX_MESURE.append(("banc", [(o.texte, sorted(o.attendu)[0], "") for o in B.BANC if o.attendu]))


def requete_de(objectif: str) -> Counter[str]:
    """La requete que le routeur construit : mots ponderes, radicaux, puis pont bilingue."""
    from jio.skills.lexique import POIDS_VOISIN, PONT

    base = R.jetons(objectif)
    requete = R._termes(objectif)
    ecrits = set(base)
    for mot in base:
        for voisin in PONT.get(mot, ()):
            if voisin not in ecrits:
                requete[voisin] = max(requete.get(voisin, 0.0), POIDS_VOISIN)
    return requete


def bm25f(cat, nom: str, requete: Counter[str], *, poids_tiers: float = 1.0,
          poids_corps: float = 0.75, idf_maximum: bool = False,
          b_tiers: float = 0.75, b_corps: float = 0.75) -> float:
    """BM25F canonique : tf combine AVANT saturation, normalisation de longueur par champ."""
    tf_t = cat._termes.get(nom, {})
    tf_c = cat._termes_corps.get(nom, {})
    l_t, l_c = cat._longueur.get(nom, 1.0), cat._longueur_corps.get(nom, 1.0)
    n_t = 1 - b_tiers + b_tiers * l_t / (cat._moyenne or 1.0)
    n_c = 1 - b_corps + b_corps * l_c / (cat._moyenne_corps or 1.0)
    score = 0.0
    for terme, qtf in requete.items():
        a = poids_tiers * tf_t.get(terme, 0.0) / n_t
        b = poids_corps * tf_c.get(terme, 0.0) / n_c
        tf = a + b
        if not tf:
            continue
        if idf_maximum:
            idf = max(cat._idf.get(terme, 0.0), cat._idf_corps.get(terme, 0.0))
            if not idf:
                continue
        else:
            idf = cat._idf.get(terme, 0.0) if a else cat._idf_corps.get(terme, 0.0)
        score += idf * (tf / (R.K1 + tf)) * qtf
    return score


def catalogue_patche(methode) -> object:
    cat = copy.deepcopy(BASE)
    cat._bm25 = methode.__get__(cat)
    return cat


def reference(cat, nom: str, requete: Counter[str]) -> float:
    """La methode de score d'origine, gardee de cote pour la variante R0."""
    return type(BASE)._bm25(cat, nom, requete)


def premier_choix(cat, objectif: str) -> str | None:
    requete = requete_de(objectif)
    scores = {d.nom: cat._bm25(d.nom, requete) for d in cat.documents}
    meilleur = max(scores.values(), default=0.0)
    if meilleur <= 0:
        return None
    return max(scores, key=lambda n: (scores[n], n))


def ligne_pour(cat, etiquette: str) -> None:
    ligne = f"  {etiquette:34}"
    total_justes = total_cas = 0
    for nom, positifs in JEUX_MESURE:
        justes = sum(1 for t, a, _ in positifs if premier_choix(cat, t) == a)
        if nom != "banc":
            total_justes += justes
            total_cas += len(positifs)
        ligne += f"{justes:>3}/{len(positifs):<3}"
    print(ligne + f" | jeux {total_justes}/{total_cas} = {total_justes/total_cas:5.1%}")


def catalogue_repetition(poids: int):
    """R2 : la repetition des champs courts du tiers 0, sans toucher au depot."""
    origine = R.Document.__dict__["indexable"]
    R.Document.indexable = property(
        lambda self, _p=poids: " ".join([self.nom] * _p + list(self.tags) * _p
                                        + [self.description, self.categorie])
    )
    try:
        cat = R.Catalogue.depuis(
            [R.Document(nom=d.nom, categorie=d.categorie, description=d.description,
                        tags=d.tags, corps=d.corps) for d in BASE.documents]
        )
    finally:
        R.Document.indexable = origine
    return cat


def main() -> int:
    print("  CLASSEMENT SEUL, sans porte d'abstention — le premier choix du score brut\n")
    print(f"  {'variante':34}" + "".join(f"{n:>7}" for n, _ in JEUX_MESURE))
    ligne_pour(catalogue_patche(
        lambda self, nom, requete: reference(self, nom, requete)), "R0 etat actuel (deux champs)")
    for poids in (0.5, 0.75, 1.0, 1.5, 2.0):
        ligne_pour(catalogue_patche(
            lambda self, nom, requete, _p=poids: bm25f(self, nom, requete, poids_corps=_p)),
            f"R1 BM25F canonique, corps {poids}")
    ligne_pour(catalogue_patche(
        lambda self, nom, requete: bm25f(self, nom, requete, idf_maximum=True)),
        "R3 BM25F, idf = max des deux champs")
    for poids in (1, 2, 3, 4, 5):
        ligne_pour(catalogue_repetition(poids), f"R2 tiers 0 repete x{poids}")
    print()
    print("  Le banc est la colonne de droite : il a REGLE le routeur, donc un gain chez lui")
    print("  sans gain sur les quatre jeux serait de l'ajustement, pas une amelioration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
