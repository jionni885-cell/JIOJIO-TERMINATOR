"""Portes d'abstention : quelles preuves de domaine laissent passer quoi ?

LE PROBLEME, mesure par `scripts/diagnostic-routeur.py` : sur 113 cas jamais vus, 24 objectifs du
domaine sont refuses par la porte, et 30 hors sujet sont refuses par la meme porte. Les deux
populations ont la MEME forme — 0 ou 1 mot de domaine, idf moyen 0,79 contre 0,72. Compter des
mots ne peut donc pas les separer : c'est un plafond de la mesure, pas un reglage a trouver.

Ce que ce script cherche : une PREUVE DE DOMAINE plus riche que le seul vocabulaire du tiers 0.
Trois sources existent dans le depot, et elles n'ont jamais ete comparees comme portes :

  * `V_lex`   : les classes du lexique (vocabulaire de domaine curé, FR et EN) ;
  * `V_tier0` : le vocabulaire des fiches (nom, tags, description, categorie) ;
  * `V_corps` : le vocabulaire des CORPS — la prose anglaise qui dit QUAND la competence
                s'applique. C'est la source la plus riche, et c'est aussi la plus dangereuse :
                un mot courant y entre facilement.

PROTOCOLE, et il est declare ici AVANT la mesure :
  * le BANC regle — il est sature (0 abstention a tort, 0 hors sujet charge), donc il ne
    discrimine plus rien ; il sert de garde-fou, pas de critere ;
  * les jeux C (detail relu) et le BANC servent au CHOIX ;
  * les jeux A, B et D VERIFIENT — D est le seul dont le detail n'a jamais ete ouvert ;
  * une porte est ACCEPTEE si et seulement si : aucun hors sujet de plus charge sur l'ensemble
    des cinq jeux, ET plus d'objectifs du domaine servis. Une porte qui echange des faux negatifs
    contre des faux positifs n'est pas une amelioration, c'est un deplacement — et le depot
    considere qu'une procedure chargee a tort coute plus cher qu'une procedure non chargee.
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

import jio.skills.router as R  # noqa: E402
from jio.skills import banc as B  # noqa: E402
from jio.skills.controle import JEUX  # noqa: E402
from jio.skills.lexique import CLASSES  # noqa: E402
from jio.skills.router import stem  # noqa: E402

CAT = R.catalogue_du_depot()


def vocabulaire(texte: str) -> frozenset[str]:
    """Le vocabulaire d'un texte, sous ses deux formes (mot et radical), comme le routeur."""
    return frozenset({m for mot in R.jetons(texte) for m in (mot, R.stem(mot))})


V_LEX = frozenset({m for classe in CLASSES for mot in classe
                   for m in (mot, R.stem(mot))})
V_TIER0 = frozenset(CAT._vocabulaire)
V_CORPS = frozenset().union(*(vocabulaire(d.corps) for d in CAT.documents if d.corps))

#: Les mots du corps qui NE SONT PAS dans le tiers 0 : c'est la prose procedurale proprement dite.
V_CORPS_SEUL = V_CORPS - V_TIER0


def mots(objectif: str, source: frozenset[str]) -> set[str]:
    return {stem(m) for m in R.jetons(objectif) if m in source or stem(m) in source}


# --------------------------------------------------------------------------------------- #
# Les portes candidates. Chacune rend True = « charger ».
# --------------------------------------------------------------------------------------- #

def porte_0(objectif: str) -> bool:
    """L'etat actuel : au moins DEUX mots de domaine (lexique ou tiers 0)."""
    return len(mots(objectif, V_LEX | V_TIER0)) >= 2


def porte_1(objectif: str) -> bool:
    """Les corps entrent dans la preuve de domaine (union des trois sources)."""
    return len(mots(objectif, V_LEX | V_TIER0 | V_CORPS)) >= 2


def porte_2(objectif: str) -> bool:
    """Un mot du lexique ET un mot d'une autre source : deux temoignages distincts."""
    return bool(mots(objectif, V_LEX)) and bool(mots(objectif, V_TIER0 | V_CORPS_SEUL))


def porte_3(objectif: str) -> bool:
    """Deux mots du domaine, dont AU MOINS UN du lexique (le vocabulaire cure)."""
    ev = mots(objectif, V_LEX | V_TIER0 | V_CORPS_SEUL)
    return len(ev) >= 2 and bool(mots(objectif, V_LEX))


def porte_4(objectif: str) -> bool:
    """Ponderation : le lexique compte double, la prose des corps compte une fois."""
    score = 2 * len(mots(objectif, V_LEX)) + len(mots(objectif, V_TIER0 | V_CORPS_SEUL))
    return score >= 2


def porte_5(objectif: str) -> bool:
    """Deux mots, mais un seul suffit s'il vient du lexique et pese lourd (idf eleve)."""
    ev = mots(objectif, V_LEX | V_TIER0 | V_CORPS_SEUL)
    if len(ev) >= 2:
        return True
    if len(ev) == 1:
        (seul,) = ev
        return CAT._idf_corps.get(seul, 0.0) + CAT._idf.get(seul, 0.0) >= 3.0
    return False


PORTES = (
    ("0  actuelle : 2 mots (lexique + tiers 0)", porte_0),
    ("1  + prose des corps dans la preuve", porte_1),
    ("2  lexique ET une autre source", porte_2),
    ("3  2 mots dont un du lexique", porte_3),
    ("4  pondere (lexique x2)", porte_4),
    ("5  2 mots, ou 1 mot a idf fort", porte_5),
)


def servir(objectif: str, porte) -> str | None:
    """Le premier choix si la porte ouvre, sinon None. Le classement ne change pas."""
    if not porte(objectif):
        return None
    choix = R.choisir(objectif, maximum=3)
    return choix[0].nom if choix else None


def evaluer(porte) -> dict[str, tuple[int, int, int]]:
    """Par jeu : (justes, servis, charges a tort)."""
    resultat = {}
    jeux = [(f"{j.nom}", [c for c in j.cas], list(j.hors_sujet)) for j in JEUX]
    jeux.append(("banc", [(o.texte, sorted(o.attendu)[0], "") for o in B.BANC if o.attendu],
                 [o.texte for o in B.BANC if not o.attendu]))
    for nom, positifs, negatifs in jeux:
        justes = servis = 0
        for texte, attendu, _ in positifs:
            premier = servir(texte, porte)
            if premier is not None:
                servis += 1
                justes += premier == attendu
        charges = sum(1 for t in negatifs if servir(t, porte) is not None)
        resultat[nom] = (justes, servis, charges)
    return resultat


def main() -> int:
    print("  Les portes, jeu par jeu. Format : justes/servis, hors sujet charges.\n")
    entete = "  " + f"{'porte':44}" + "".join(f"{n:>12}" for n in
                                             ["A", "B", "C", "D", "banc"])
    print(entete)
    for nom, porte in PORTES:
        r = evaluer(porte)
        ligne = f"  {nom:44}"
        for jeu in ("A", "B", "C", "D", "banc"):
            justes, servis, charges = r[jeu]
            ligne += f"{justes:>5}/{servis:<5}{charges:>1} "
        tot_justes = sum(r[j][0] for j in ("A", "B", "C", "D"))
        tot_charge = sum(r[j][2] for j in ("A", "B", "C", "D"))
        tot_servis = sum(r[j][1] for j in ("A", "B", "C", "D"))
        print(ligne + f"  | 4 jeux : {tot_justes}/{tot_servis} justes, {tot_charge} charges")
    print()
    print("  Lecture : `justes/servis` compte les premiers choix justes PARMI les objectifs")
    print("  servis. Un jeu ou servis = 31/31 est un jeu sature, il ne discrimine plus rien.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
