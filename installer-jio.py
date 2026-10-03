#!/usr/bin/env python3
"""L'installateur de JIO — UNE commande, tout se fait tout seul.

Deux usages, selon ou tu es :

  1. DANS le dossier JIOJIO-TERMINATOR (apres l'avoir telecharge/decompresse) :
         python installer-jio.py
     -> cree l'environnement, installe jio, verifie, et te dit la commande a taper.

  2. DANS TON projet (n'importe ou) :
         python installer-jio.py --projet .
     -> installe jio si besoin (depuis GitHub, sans rien telecharger a la main),
        puis integre JIO a ce projet (equivalent de `jio start`) et te dit la suite.

Ce script ne telecharge rien d'autre que JIO lui-meme, ne touche a rien hors du
dossier que tu lui donnes, et peut etre relu avant d'etre execute — c'est la
regle du depot, appliquee au depot lui-meme.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import urllib.request
from pathlib import Path

BRANCHE = "arena/01a0d44e-jiojio-terminator"
URL_DEPOT = "https://github.com/jionni885-cell/JIOJIO-TERMINATOR.git"


def _lancer(commande: list[str], ou: Path | None = None) -> tuple[int, str]:
    resultat = subprocess.run(
        commande, cwd=ou, capture_output=True, text=True,
    )
    sortie = (resultat.stdout or "") + (resultat.stderr or "")
    return resultat.returncode, sortie


def _python_disponible() -> str | None:
    for candidat in (sys.executable, "python3", "python"):
        try:
            code, _ = _lancer([candidat, "--version"])
        except OSError:
            continue
        if code == 0:
            return candidat
    return None


def _installer_depuis_github(destination: Path) -> tuple[bool, str]:
    """Installe jio dans un venv, directement depuis GitHub — sans clone a la main."""
    python = _python_disponible()
    if python is None:
        return False, "Python n'est pas installe. Telecharge-le sur python.org (coche 'Add to PATH')."
    code, sortie = _lancer([python, "-m", "venv", str(destination)])
    if code != 0:
        return False, f"creation de l'environnement impossible : {sortie[-200:]}"
    pip = destination / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
    # SANS fragment de nom : le paquet s'appelle jiojio-terminator, et `jio @ git+...`
    # entrait en conflit avec un paquet PyPI homonyme (defaut constate au test reel).
    code, sortie = _lancer([str(pip), "install", "-q", f"git+{URL_DEPOT}@{BRANCHE}"])
    if code != 0:
        return False, f"installation impossible : {sortie[-300:]}"
    return True, str(destination / ("Scripts" if sys.platform == "win32" else "bin") / "jio")


def main() -> int:
    parseur = argparse.ArgumentParser(
        description="Installe JIO et l'integre a ton projet — une commande.",
    )
    parseur.add_argument(
        "--projet", default=None, metavar="CHEMIN",
        help="le dossier de TON projet : installe jio (depuis GitHub si besoin), "
             "puis lance l'integration (`jio start`) dans ce dossier",
    )
    args = parseur.parse_args()

    ici = Path(__file__).resolve().parent
    depot_local = (ici / "jio" / "cli.py").is_file()

    if args.projet is None:
        # Usage 1 : installation depuis le dossier du depot.
        if not depot_local:
            print("Ce script doit rester dans le dossier JIOJIO-TERMINATOR,")
            print("ou s'utiliser avec --projet <ton dossier>.")
            return 2
        venv = ici / ".venv"
        pip = venv / ("Scripts" if sys.platform == "win32" else "bin") / "pip"
        jio = venv / ("Scripts" if sys.platform == "win32" else "bin") / "jio"
        print("[1/3] environnement Python...")
        code, sortie = _lancer([sys.executable, "-m", "venv", str(venv)])
        if code != 0:
            print(f"  echec : {sortie[-300:]}")
            return 1
        print("[2/3] installation de jio (pip install -e .)...")
        code, sortie = _lancer([str(pip), "install", "-q", "-e", "."])
        if code != 0:
            print(f"  echec : {sortie[-300:]}")
            return 1
        print("[3/3] verification...")
        code, sortie = _lancer([str(jio), "--version"])
        if code != 0:
            print(f"  echec : {sortie[-300:]}")
            return 1
        print(f"\nOK — jio est installe ({sortie.strip()}).")
        print("\nPour l'utiliser dans un projet, DEUX choix :")
        print(f"  a) {jio} start   (depuis le dossier de ton projet)")
        print("  b) la VOIE RAPIDE, sans ce dossier :")
        print(f"       python {Path(__file__).name} --projet C:\\chemin\\vers\\ton\\projet")
        return 0

    # Usage 2 : tout-en-un dans le projet donne.
    projet = Path(args.projet).expanduser().resolve()
    if not projet.is_dir():
        print(f"dossier introuvable : {projet}")
        return 2
    print(f"[1/2] installation de jio (depuis GitHub, {BRANCHE[:20]}...)...")
    ok, message = _installer_depuis_github(projet / ".venv-jio")
    if not ok:
        print(f"  echec : {message}")
        return 1
    jio = Path(message)
    print(f"      jio installe : {jio}")
    print("[2/2] integration au projet (jio start)...")
    code, sortie = _lancer([str(jio), "start"], ou=projet)
    print(sortie[-1500:] if sortie.strip() else "(aucune sortie)")
    if code != 0:
        print(f"jio start a echoue (code {code}) — lis le message ci-dessus, il dit quoi faire.")
        return code
    print(f"\nTERMINE. JIO est integre a {projet}.")
    print(f"Pour travailler : {jio} run \"ton objectif\"   (depuis ce dossier)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
