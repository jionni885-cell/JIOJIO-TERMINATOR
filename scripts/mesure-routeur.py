"""Mesure APPARIEE avant/apres de la retouche BM25F du routeur.

Un seul parametre change : POIDS_CORPS. 0 = etat livre avant aujourd'hui, 0.75 = etat retenu.
Meme code, memes jeux, memes requetes : la difference ne peut donc pas venir d'ailleurs.

Sortie : un JSON pret a archiver (IC95 par bootstrap apparie sur les cas).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path

import jio.skills.router as R
from jio.skills import banc as B
from jio.skills.controle import CAS

HORS_A = getattr(sys.modules["jio.skills.controle"], "HORS_SUJET", ())


def charger_jeu_b(chemin: Path) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Charge et valide le holdout externe sans faire d'E/S à l'import du module."""
    try:
        contenu = json.loads(chemin.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"holdout B illisible ({chemin}) : {exc}") from exc
    if not isinstance(contenu, dict):
        # Un schéma invalide est une erreur des données lues; main la traite comme telle.
        raise ValueError("le holdout B doit être un objet JSON")

    positifs = contenu.get("cas")
    negatifs = contenu.get("hors_sujet")
    if not isinstance(positifs, list) or not positifs:
        raise ValueError("le holdout B doit contenir une liste 'cas' non vide")
    if not isinstance(negatifs, list) or not negatifs:
        raise ValueError("le holdout B doit contenir une liste 'hors_sujet' non vide")

    cas_valides: list[tuple[str, str, str]] = []
    for numero, cas in enumerate(positifs, start=1):
        if (
            not isinstance(cas, list)
            or len(cas) != 3
            or any(not isinstance(champ, str) or not champ.strip() for champ in cas)
        ):
            raise ValueError(
                f"cas #{numero} invalide : attendu [objectif, competence attendue, langue]"
            )
        cas_valides.append((cas[0], cas[1], cas[2]))
    if any(not isinstance(texte, str) or not texte.strip() for texte in negatifs):
        raise ValueError("chaque entrée de 'hors_sujet' doit être une chaîne non vide")
    return cas_valides, negatifs


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

    def _bm25(self, nom, requete, _m=methode, _p=p):
        tiers0 = nu(
            nom, requete, self._termes, self._longueur, self._moyenne, self._idf
        )
        corps = nu(
            nom,
            requete,
            self._termes_corps,
            self._longueur_corps,
            self._moyenne_corps,
            self._idf_corps,
        )
        return tiers0 + _p * corps

    cat._bm25 = _bm25.__get__(cat)
    return cat


def justesse(cat, cas) -> list[bool]:
    return [
        bool((c := cat.interroger(t, maximum=3)) and c[0].nom == a) for t, a, _ in cas
    ]


def ic95_apparie(
    gauche: list[bool], droite: list[bool], n: int = 20000
) -> tuple[float, float]:
    if not gauche or len(gauche) != len(droite):
        raise ValueError(
            "le bootstrap apparié exige deux séries non vides de même longueur"
        )
    if n < 1:
        raise ValueError("le nombre de réplications bootstrap doit être positif")
    rng = random.Random(20261001)
    differences = [int(d) - int(g) for g, d in zip(gauche, droite)]
    tirages = []
    for _ in range(n):
        tirages.append(
            sum(rng.choice(differences) for _ in differences) / len(differences)
        )
    tirages.sort()
    return tirages[int(0.025 * n)], tirages[int(0.975 * n)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--holdout",
        type=Path,
        default=Path(os.environ.get("JIO_ROUTEUR_HOLDOUT", "/tmp/holdout-b.json")),
        help="jeu B pré-enregistré (défaut : JIO_ROUTEUR_HOLDOUT ou /tmp/holdout-b.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("/tmp/mesure-routeur-bm25f.json"),
        help="destination du rapport JSON",
    )
    args = parser.parse_args(argv)
    try:
        pos_b, hors_b = charger_jeu_b(args.holdout)
    except ValueError as exc:
        print(f"ERREUR : {exc}", file=sys.stderr)
        return 2

    avant, apres = catalogue(0.0), catalogue(R.POIDS_CORPS)
    jeux = [
        (
            "banc (celui du reglage)",
            [(o.texte, min(o.attendu), "") for o in B.BANC if o.attendu],
            [o.texte for o in B.BANC if not o.attendu],
        ),
        ("controle A (jamais vu)", CAS, list(HORS_A)),
        ("jeu B (jamais vu, ecrit avant la retouche)", pos_b, hors_b),
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
        abst_a = sum(1 for t in negatifs if not avant.interroger(t, maximum=3)) / len(
            negatifs
        )
        abst_p = sum(1 for t in negatifs if not apres.interroger(t, maximum=3)) / len(
            negatifs
        )
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
        print(
            f"  {nom:44} {ta:.1%} -> {tp:.1%}  ({100 * (tp - ta):+.1f} pts "
            f"IC95 [{100 * bas:+.1f} ; {100 * haut:+.1f}])  abstention {abst_a:.0%} -> {abst_p:.0%}"
        )
    # Les DEUX jeux jamais vus, regroupes : plus de cas, donc un intervalle plus serre. Le banc
    # n'y entre pas : il a regle le routeur, sa presence flatterait les deux colonnes.
    ja = justesse(avant, CAS) + justesse(avant, pos_b)
    jap = justesse(apres, CAS) + justesse(apres, pos_b)
    bas, haut = ic95_apparie(ja, jap)
    resultat["jeux_jamais_vus_regroupes"] = {
        "cas": len(ja),
        "avant": round(sum(ja) / len(ja), 4),
        "apres": round(sum(jap) / len(jap), 4),
        "gain_points": round(100 * (sum(jap) - sum(ja)) / len(ja), 1),
        "ic95_gain_points": [round(100 * bas, 1), round(100 * haut, 1)],
        "note": "deux jeux ecrits AVANT la retouche ; borne basse a zero = direction, pas preuve a 95 %",
    }
    print(
        f"  {'JEUX JAMAIS VUS regroupes':44} {sum(ja) / len(ja):.1%} -> {sum(jap) / len(jap):.1%} "
        f"({100 * (sum(jap) - sum(ja)) / len(ja):+.1f} pts IC95 [{100 * bas:+.1f} ; {100 * haut:+.1f}]) sur {len(ja)} cas"
    )

    charge_avant = sum(1 for t, _ in PRATIQUE if avant.interroger(t, maximum=3))
    charge_apres = sum(1 for t, _ in PRATIQUE if apres.interroger(t, maximum=3))
    justes_avant = sum(
        1
        for t, a in PRATIQUE
        if (c := avant.interroger(t, maximum=3)) and c[0].nom == a
    )
    justes_apres = sum(
        1
        for t, a in PRATIQUE
        if (c := apres.interroger(t, maximum=3)) and c[0].nom == a
    )
    resultat["objectifs_reels"] = {
        "cas": len(PRATIQUE),
        "chargent_avant": charge_avant,
        "chargent_apres": charge_apres,
        "bien_routes_avant": justes_avant,
        "bien_routes_apres": justes_apres,
        "note": "l'abstention reste : c'est la DECOUVERTE qui est reparee (inventaire tier 0 rendu)",
    }
    print(
        f"\n  objectifs reels de l'utilisateur : {charge_avant}/6 chargent (avant) -> "
        f"{charge_apres}/6 (apres) ; bien routes {justes_avant}/6 -> {justes_apres}/6"
    )
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(resultat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    except OSError as exc:
        print(
            f"ERREUR : impossible d'écrire le rapport {args.output} : {exc}",
            file=sys.stderr,
        )
        return 2
    print(f"\n  écrit : {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
