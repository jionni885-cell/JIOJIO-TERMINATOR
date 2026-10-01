"""Mesure APPARIEE avant/apres de la retouche BM25F du routeur.

Un seul parametre change : POIDS_CORPS. 0 = etat livre avant aujourd'hui, 0.75 = etat retenu.
Meme code, memes jeux, memes requetes : la difference ne peut donc pas venir d'ailleurs.

Sortie : un JSON pret a archiver (IC95 par bootstrap apparie sur les cas).
"""
from __future__ import annotations

import json
import random
import sys

import jio.skills.router as R
from jio.skills import banc as B
from jio.skills.controle import CAS

HORS_A = getattr(sys.modules["jio.skills.controle"], "HORS_SUJET", ())
JEUB = json.load(open("/tmp/holdout-b.json"))
HORS_B = JEUB["hors_sujet"]
POS_B = [(t, a, l) for t, a, l in JEUB["cas"]]

PRATIQUE = [
    ("ecrire des tests pour la fonction de remise", "executable-proof"),
    ("corriger un bug de division par zero", "structured-failure"),
    ("documenter l'API publique du module", "prose-witnesses"),
    ("la remise de 10% n'est pas appliquee au bon moment", "executable-proof"),
    ("null pointer quand le panier est vide", "structured-failure"),
    ("auditer la securite du projet", "hostile-content"),
]


def catalogue(poids: float):
    # on rejoue la fonction de score avec le poids demande, sans toucher au depot.
    # COPIE PROFONDE obligatoire : `catalogue_du_depot` est memoise, et patcher l'objet partage
    # ferait mesurer deux fois la meme chose (defaut de cette sonde, corrige apres l'avoir vu).
    import copy

    nu = R.Catalogue._bm25_champ
    cat = copy.deepcopy(R.catalogue_du_depot())
    p = poids
    methode = cat._bm25

    def _bm25(self, nom, requete, _m=methode, _p=p):  # noqa: ANN001
        tiers0 = nu(nom, requete, self._termes, self._longueur, self._moyenne, self._idf)
        corps = nu(nom, requete, self._termes_corps, self._longueur_corps,
                   self._moyenne_corps, self._idf_corps)
        return tiers0 + _p * corps

    cat._bm25 = _bm25.__get__(cat)
    return cat


def justesse(cat, cas) -> list[bool]:
    return [bool((c := cat.interroger(t, maximum=3)) and c[0].nom == a) for t, a, _ in cas]


def ic95_apparie(gauche: list[bool], droite: list[bool], n: int = 20000) -> tuple[float, float]:
    rng = random.Random(20261001)
    differences = [int(d) - int(g) for g, d in zip(gauche, droite)]
    tirages = []
    for _ in range(n):
        tirages.append(sum(rng.choice(differences) for _ in differences) / len(differences))
    tirages.sort()
    return tirages[int(0.025 * n)], tirages[int(0.975 * n)]


def main() -> int:
    avant, apres = catalogue(0.0), catalogue(R.POIDS_CORPS)
    jeux = [
        ("banc (celui du reglage)", [(o.texte, sorted(o.attendu)[0], "") for o in B.BANC if o.attendu],
         [o.texte for o in B.BANC if not o.attendu]),
        ("controle A (jamais vu)", CAS, list(HORS_A)),
        ("jeu B (jamais vu, ecrit avant la retouche)", POS_B, HORS_B),
    ]
    resultat: dict[str, object] = {
        "retouche": "BM25F : le corps des competences entre dans l'index comme second champ",
        "parametre": {"nom": "POIDS_CORPS", "avant": 0.0, "apres": R.POIDS_CORPS},
        "jeux": {},
    }
    for nom, positifs, negatifs in jeux:
        ja, jap = justesse(avant, positifs), justesse(apres, positifs)
        ta, tp = sum(ja) / len(ja), sum(jap) / len(jap)
        bas, haut = ic95_apparie(ja, jap)
        abst_a = sum(1 for t in negatifs if not avant.interroger(t, maximum=3)) / len(negatifs)
        abst_p = sum(1 for t in negatifs if not apres.interroger(t, maximum=3)) / len(negatifs)
        resultat["jeux"][nom] = {
            "cas": len(positifs),
            "hors_sujet": len(negatifs),
            "avant": round(ta, 4),
            "apres": round(tp, 4),
            "gain_points": round(100 * (tp - ta), 1),
            "ic95_gain_points": [round(100 * bas, 1), round(100 * haut, 1)],
            "abstention_avant": round(abst_a, 4),
            "abstention_apres": round(abst_p, 4),
            "echecs_apres": [t for (t, _, _), ok in zip(positifs, jap) if not ok],
        }
        print(f"  {nom:44} {ta:.1%} -> {tp:.1%}  ({100*(tp-ta):+.1f} pts "
              f"IC95 [{100*bas:+.1f} ; {100*haut:+.1f}])  abstention {abst_a:.0%} -> {abst_p:.0%}")
    # Les DEUX jeux jamais vus, regroupes : plus de cas, donc un intervalle plus serre. Le banc
    # n'y entre pas : il a regle le routeur, sa presence flatterait les deux colonnes.
    ja = justesse(avant, CAS) + justesse(avant, POS_B)
    jap = justesse(apres, CAS) + justesse(apres, POS_B)
    bas, haut = ic95_apparie(ja, jap)
    resultat["jeux_jamais_vus_regroupes"] = {
        "cas": len(ja),
        "avant": round(sum(ja) / len(ja), 4),
        "apres": round(sum(jap) / len(jap), 4),
        "gain_points": round(100 * (sum(jap) - sum(ja)) / len(ja), 1),
        "ic95_gain_points": [round(100 * bas, 1), round(100 * haut, 1)],
        "note": "deux jeux ecrits AVANT la retouche ; borne basse a zero = direction, pas preuve a 95 %",
    }
    print(f"  {'JEUX JAMAIS VUS regroupes':44} {sum(ja)/len(ja):.1%} -> {sum(jap)/len(jap):.1%} "
          f"({100*(sum(jap)-sum(ja))/len(ja):+.1f} pts IC95 [{100*bas:+.1f} ; {100*haut:+.1f}]) sur {len(ja)} cas")

    charge_avant = sum(1 for t, _ in PRATIQUE if avant.interroger(t, maximum=3))
    charge_apres = sum(1 for t, _ in PRATIQUE if apres.interroger(t, maximum=3))
    justes_avant = sum(1 for t, a in PRATIQUE
                       if (c := avant.interroger(t, maximum=3)) and c[0].nom == a)
    justes_apres = sum(1 for t, a in PRATIQUE
                       if (c := apres.interroger(t, maximum=3)) and c[0].nom == a)
    resultat["objectifs_reels"] = {
        "cas": len(PRATIQUE), "chargent_avant": charge_avant, "chargent_apres": charge_apres,
        "bien_routes_avant": justes_avant, "bien_routes_apres": justes_apres,
        "note": "l'abstention reste : c'est la DECOUVERTE qui est reparee (inventaire tier 0 rendu)",
    }
    print(f"\n  objectifs reels de l'utilisateur : {charge_avant}/6 chargent (avant) -> "
          f"{charge_apres}/6 (apres) ; bien routes {justes_avant}/6 -> {justes_apres}/6")
    with open("/tmp/mesure-routeur-bm25f.json", "w", encoding="utf-8") as f:
        json.dump(resultat, f, ensure_ascii=False, indent=2)
    print("\n  ecrit : /tmp/mesure-routeur-bm25f.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
