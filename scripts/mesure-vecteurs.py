"""Mesurer ce que la table de vecteurs change — et ce qu'elle ne change PAS.

Trois usages possibles, mesures cote a cote, sur les populations qui comptent :

  1. la PORTE (« charger ou non ») : la ressemblance separe-t-elle les objectifs du domaine des
     hors sujet ? (population : 24 refuses + 31 hors sujet) ;
  2. le REORDONNEMENT complet de la liste par fusion RRF (population : 24 refuses, plus le banc) ;
  3. la COMPLETION de la liste quand le lexique marque moins d'elements que demande (retenue).

Usage : python scripts/mesure-vecteurs.py [--json]
"""

from __future__ import annotations

import argparse
import datetime
import json
import pathlib
import statistics
import subprocess
import sys

RACINE = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from jio.skills.banc import BANC  # noqa: E402
from jio.skills.controle import JEUX  # noqa: E402
from jio.skills.router import catalogue_du_depot, choisir, proches  # noqa: E402
from jio.skills.vecteurs import (  # noqa: E402
    CHEMIN_TABLE,
    appariement,
    classement_semantique,
    fusionner,
    mots_cles,
    table_du_depot,
)


def _taux(population, liste, combiens=(1, 3, 5, 12)) -> dict[str, str]:
    bons = {k: 0 for k in combiens}
    for texte, attendu in population:
        noms = liste(texte)
        for k in combiens:
            bons[k] += int(attendu in noms[:k])
    return {f"@{k}": f"{bons[k]}/{len(population)}" for k in combiens}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--json", action="store_true", help="ecrire evidence/vecteurs-semantiques.json")
    ap.add_argument("--sortie", type=pathlib.Path, default=None)
    args = ap.parse_args()

    catalogue = catalogue_du_depot()
    table = table_du_depot()
    if table is None:
        print("ABSENTE : la table de vecteurs n'est pas livree — rien a mesurer.")
        return 1
    cles = {d.nom: mots_cles(catalogue, d.nom, table) for d in catalogue.documents}

    refuses = [(t, a) for j in JEUX for t, a, _ in j.cas if not choisir(t, maximum=3)]
    tous = [(t, a) for j in JEUX for t, a, _ in j.cas]
    banc = [(o.texte, set(o.attendu)) for o in BANC if o.positif]
    hors = [t for j in JEUX for t in j.hors_sujet] + [o.texte for o in BANC if not o.positif]

    def bm25f(texte, maximum=12) -> list[str]:
        return [c.nom for c in choisir(texte, maximum=maximum, seuil=0)]

    def reordonnee(texte, maximum=12) -> list[str]:
        return fusionner(bm25f(texte, maximum),
                         classement_semantique(catalogue, texte, table, cles), poids_semantique=0.5)

    def completee(texte, maximum=12) -> list[str]:
        return [c.nom for c in proches(texte, maximum=maximum)]

    def banc_complet(liste, combiens=(1, 3, 5, 12)) -> dict[str, str]:
        bons = {k: 0 for k in combiens}
        for texte, attendus in banc:
            noms = liste(texte)
            for k in combiens:
                bons[k] += int(bool(set(noms[:k]) & attendus))
        return {f"@{k}": f"{bons[k]}/{len(banc)}" for k in combiens}

    # -- 1. la porte : la ressemblance separe-t-elle ?
    def profil(texte) -> tuple[float, float, float] | None:
        p = appariement(catalogue, texte, cles, table)
        if not p:
            return None
        v = sorted(p.values(), reverse=True)
        return v[0], statistics.median(v), v[0] - statistics.median(v)

    def distribution(textes) -> dict[str, object]:
        profils = [p for p in (profil(t) for t in textes) if p is not None]
        premier = sorted(p[0] for p in profils)
        contraste = sorted(p[2] for p in profils)
        return {
            "cas": len(profils),
            "sans_signal": len(textes) - len(profils),
            "ressemblance_max": {
                "min": round(premier[0], 3),
                "mediane": round(premier[len(premier) // 2], 3),
                "max": round(premier[-1], 3),
            },
            "contraste_mediane": round(contraste[len(contraste) // 2], 3),
        }

    mesure = {
        "horodatage": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S +0000"),
        "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=RACINE,
                                 capture_output=True, text=True).stdout.strip(),
        "table": {
            "source": table.entete.get("source"),
            "mots": len(table.mots),
            "dims": table.dims,
            "octets": CHEMIN_TABLE.stat().st_size,
            "chemin": str(CHEMIN_TABLE.relative_to(RACINE)),
            "construite_par": "scripts/construire-vecteurs.py",
        },
        "1_porte_semantique": {
            "verdict": "IMPOSSIBLE — les deux populations se recouvrent",
            "objectifs_du_domaine_refuses": distribution([t for t, _ in refuses]),
            "hors_sujet": distribution(hors),
        },
        "2_reordonner_la_liste": {
            "verdict": "ECARTE — gagne au milieu, perd la tete",
            "24_refuses_bm25": _taux(refuses, bm25f),
            "24_refuses_reordonnee": _taux(refuses, reordonnee),
            "banc_bm25": banc_complet(bm25f),
            "banc_reordonnee": banc_complet(reordonnee),
        },
        "3_completer_la_liste": {
            "verdict": "RETENU — domination stricte, aucune metrique ne baisse",
            "24_refuses_avant": _taux(refuses, bm25f),
            "24_refuses_apres": _taux(refuses, completee),
            "113_cas_avant": _taux(tous, bm25f),
            "113_cas_apres": _taux(tous, completee),
            "banc_avant": banc_complet(bm25f),
            "banc_apres": banc_complet(completee),
        },
        "reproductible_par": "python scripts/mesure-vecteurs.py --json ; jio skills --controle",
    }

    if args.json:
        chemin = args.sortie or (RACINE / "evidence" / "vecteurs-semantiques.json")
        chemin.write_text(json.dumps(mesure, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"ecrit : {chemin.relative_to(RACINE)}")

    print(f"table : {len(table.mots)} radicaux, {mesure['table']['octets']/1e6:.2f} Mo")
    for nom in ("1_porte_semantique", "2_reordonner_la_liste", "3_completer_la_liste"):
        bloc = mesure[nom]
        print(f"\n{nom} — {bloc['verdict']}")  # type: ignore[union-attr]
        for cle, valeur in list(bloc.items())[1:]:  # type: ignore[union-attr]
            print(f"    {cle:<26} {valeur}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
