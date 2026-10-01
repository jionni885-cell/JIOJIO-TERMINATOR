"""Ou le routeur perd ses points : diagnostic AVANT retouche, sur les cinq jeux.

Ce script ne modifie rien. Il mesure, pour chaque objectif de chaque jeu, trois nombres :

  * `mots`   : les mots de domaine du TIERS 0 (la porte d'abstention actuelle) ;
  * `idf`    : la somme de leur `idf` dans l'index — un mot present dans une seule competence
               (« invariant », « temoins ») pese lourd, un mot present dans six (« fichier »,
               « message ») ne distingue rien ;
  * `score`  : le meilleur score BM25F obtenu.

But : savoir si la porte d'abstention rate des objectifs du domaine a cause de son COMPTAGE
(elle compte les mots sans regarder leur pouvoir discriminant) — et si les faux positifs des
jeux C et D entrent par un mot GENERIQUE plutot que par un mot de domaine.

Sortie : distributions, puis la liste des objectifs servis/refuses, par jeu.
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from jio.skills import banc as B  # noqa: E402
from jio.skills.controle import JEUX  # noqa: E402
from jio.skills.router import catalogue_du_depot, choisir, jetons, stem  # noqa: E402


def diagnostic(objectif: str, cat) -> tuple[int, float, float, str | None]:
    """(nombre de mots de domaine, idf cumule, meilleur score, premier choix)."""
    from jio.skills.lexique import CONCEPT

    mots = [m for m in jetons(objectif)
            if m in CONCEPT or m in cat._vocabulaire or stem(m) in cat._vocabulaire]
    idf = sum(cat._idf.get(stem(m) if stem(m) in cat._idf else m, 0.0) for m in mots)
    choix = choisir(objectif, maximum=3)
    score = choix[0].score if choix else 0.0
    return len(set(stem(m) for m in mots)), round(idf, 2), score, (choix[0].nom if choix else None)


def main() -> int:
    cat = catalogue_du_depot()
    jeux = [(f"jeu {j.nom}", list(j.cas), list(j.hors_sujet)) for j in JEUX]
    jeux.append(("banc", [(o.texte, sorted(o.attendu)[0] if o.attendu else "", "") for o in B.BANC
                          if o.attendu if o.attendu],
                 [o.texte for o in B.BANC if not o.attendu]))

    for nom, positifs, negatifs in jeux:
        print(f"\n=== {nom} : {len(positifs)} objectifs, {len(negatifs)} hors sujet ===")
        abstenus = []
        for texte, attendu, _ in positifs:
            mots, idf, score, premier = diagnostic(texte, cat)
            if premier is None:
                abstenus.append((texte, mots, idf))
        print(f"  abstentions sur des objectifs du domaine : {len(abstenus)}/{len(positifs)}")
        for texte, mots, idf in abstenus[:12]:
            print(f"     [{mots} mot(s), idf {idf:5.2f}] {texte[:66]}")
        faux = []
        for texte in negatifs:
            mots, idf, score, premier = diagnostic(texte, cat)
            if premier is not None:
                faux.append((texte, mots, idf, premier))
        print(f"  hors sujet charges : {len(faux)}/{len(negatifs)}")
        for texte, mots, idf, premier in faux:
            print(f"     [{mots} mot(s), idf {idf:5.2f}] {texte[:50]} -> {premier}")

    # Ce qui distingue les deux populations : le nombre de mots, et l'idf cumule.
    def population(positifs, negatifs):
        d = {
            "positifs servis": [(m, i) for t, a, _ in positifs
                                for m, i, s, p in [diagnostic(t, cat)] if p is not None],
            "positifs abstenus": [(m, i) for t, a, _ in positifs
                                  for m, i, s, p in [diagnostic(t, cat)] if p is None],
            "hors sujet refuses": [(m, i) for t in negatifs
                                   for m, i, s, p in [diagnostic(t, cat)] if p is None],
            "hors sujet charges": [(m, i) for t in negatifs
                                   for m, i, s, p in [diagnostic(t, cat)] if p is not None],
        }
        return d

    total_pos = [c for _, p, _ in jeux for c in p]
    total_neg = [c for _, _, n in jeux for c in n]
    print("\n=== les quatre populations, tous jeux confondus ===")
    for nom, valeurs in population(total_pos, total_neg).items():
        if not valeurs:
            print(f"  {nom:22} : aucun cas")
            continue
        mots = Counter(m for m, _ in valeurs)
        idfs = [i for _, i in valeurs]
        moyenne = sum(idfs) / len(idfs)
        print(f"  {nom:22} : {len(valeurs):3} cas · mots {dict(sorted(mots.items()))} · "
              f"idf moyen {moyenne:5.2f} · idf min {min(idfs):5.2f} · idf max {max(idfs):5.2f}")
    return 0


def second_rapport() -> int:
    """La porte fermee : que vaut la LISTE que le routeur pourrait rendre ?

    La porte d'abstention refuse 24 objectifs du domaine (mesure ci-dessus) et 30 hors sujet.
    Le classement, lui, tourne quand meme : il suffit de ne pas s'en servir pour decider.

    Deux questions, et elles decident de ce que le routeur doit RENDRE quand il s'abstient :
      * parmi les objectifs refuses a tort, le premier de la liste est-il le bon ? (a 1 chance
        sur 12 au hasard : 12 competences) ;
      * les hors sujet refuses auraient-ils eu un score ELEVE ? Si oui, une seconde porte sur le
        score laisserait entrer les faux negatifs ET les faux positifs — donc non.
    """
    from jio.skills.controle import JEUX
    from jio.skills.router import choisir

    cat = catalogue_du_depot()
    refuses_bon = []      # objectifs du domaine, refuses : (texte, attendu, top1, score)
    refuses_faux = []     # hors sujet refuses : (texte, top1, score)
    jeux = [(j.nom, list(j.cas), list(j.hors_sujet)) for j in JEUX]

    for nom, positifs, negatifs in jeux:
        for texte, attendu, _ in positifs:
            if choisir(texte, maximum=3):
                continue
            choix = choisir(texte, maximum=3, seuil=0)
            premier = choix[0].nom if choix else None
            score = choix[0].score if choix else 0.0
            refuses_bon.append((nom, texte, attendu, premier, score))
        for texte in negatifs:
            if choisir(texte, maximum=3):
                continue
            choix = choisir(texte, maximum=3, seuil=0)
            refuses_faux.append((nom, texte, choix[0].nom if choix else None,
                                 choix[0].score if choix else 0.0))

    justes = sum(1 for _, _, attendu, premier, _ in refuses_bon if premier == attendu)
    print("\n=== la liste rendue quand la porte se ferme ===")
    print(f"  objectifs du domaine refuses : {len(refuses_bon)}")
    print(f"    premier de la liste JUSTE : {justes}/{len(refuses_bon)} "
          f"({justes/len(refuses_bon):.0%}) — hasard 8 % (1 sur 12)")
    for nom, texte, attendu, premier, score in refuses_bon[:6]:
        marque = "ok " if premier == attendu else "   "
        print(f"     [{marque}] attendu {attendu:22} | liste : {premier} ({score:.2f}) "
              f"| {texte[:44]}")
    scores_bon = sorted(s for *_, s in refuses_bon)
    print(f"    score du premier : median {scores_bon[len(scores_bon)//2]:.2f}, "
          f"max {max(scores_bon):.2f}")
    if refuses_faux:
        scores_faux = sorted(s for *_, s in refuses_faux)
        print(f"  hors sujet refuses : {len(refuses_faux)} · score du premier : "
              f"median {scores_faux[len(scores_faux)//2]:.2f}, max {max(scores_faux):.2f}")
        print("    (si les deux distributions se recouvrent, une seconde porte sur le score")
        print("     laisserait entrer les faux positifs avec les faux negatifs)")
    return 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "liste":
        raise SystemExit(second_rapport())
    raise SystemExit(main())
