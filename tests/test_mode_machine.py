"""Un mode machine qui n'est pas lisible par une machine n'est pas un mode machine.

Defaut mesure, et c'est ce qui l'a fait sortir : `jio ablation --json > rapport.json` produisait
un fichier qui COMMENCAIT par le logo ASCII de l'outil, suivi d'un en-tete, puis du JSON. Le
fichier n'etait donc pas un document JSON, et `--json | jq .` echouait. Meme chose pour
`jio coherence --json`.

Ce que ca coute, en clair : celui qui veut un chiffre pour l'exploiter doit le recopier a la
main. C'est-a-dire que la commande n'avait pas de mode machine du tout — elle avait un mode
« humain, mais avec des accolades ».

La correction est MECANIQUE et c'est deliberé : `main()` retourne la sortie standard vers la
sortie d'erreur une fois pour toutes quand la commande demande une sortie machine. Tout ce qui
est ecrit pour l'humain — banniere, en-tete, progression, conseils — part alors sur la sortie
d'erreur ; seule la charge utile, ecrite par `_charge_utile`, reste sur la vraie sortie
standard. Aucun `print` n'a ete patche un par un : le prochain oublie aurait recommence le
defaut.

Ces tests lisent la sortie des VRAIES commandes, dans un processus separe : c'est la seule
facon de verifier ce qu'un appelant verra, et une propriete unitaire ne l'aurait pas vu.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def _lancer(*args: str, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "jio", *args],
        cwd=str(cwd or REPO), capture_output=True, text=True, timeout=900,
    )


def _json_pur(proc: subprocess.CompletedProcess[str]) -> dict:
    """La sortie standard est-elle un document JSON, du premier au dernier octet ?"""
    texte = proc.stdout
    assert texte.strip(), (
        f"aucune charge utile sur la sortie standard.\n"
        f"--- stderr ---\n{proc.stderr[-1500:]}"
    )
    try:
        return json.loads(texte)
    except json.JSONDecodeError as exc:
        debut = texte[:200].replace("\n", "\\n")
        raise AssertionError(
            f"sortie standard NON lisible par une machine ({exc}).\n"
            f"debut : {debut}\n"
            f"--- stderr ---\n{proc.stderr[-800:]}"
        ) from exc


@pytest.mark.parametrize(
    ("args", "cle"),
    [
        (("coherence", "--json"), "constats"),
        (("clarify", "corrige le bug du panier", "--json"), "objectif"),
        (("sorties", "--json"), "blocs"),
        (("skills", "corrige le panier", "--json"), "objectif"),
    ],
)
def test_les_modes_machine_sortent_du_json_pur(args: tuple[str, ...], cle: str) -> None:
    proc = _lancer(*args)
    charge = _json_pur(proc)
    assert cle in charge, f"la charge utile a change de forme : {sorted(charge)[:8]}"


def test_l_ablation_sort_du_json_pur() -> None:
    """`jio ablation --json` : le cas qui a fait trouver le defaut.

    Une seule mission et un seul levier : c'est le mode machine qu'on verifie, pas la mesure.
    """
    proc = _lancer("ablation", "--levers", "preuve", "--missions", "1", "--json")
    charge = _json_pur(proc)
    assert charge["n_missions"] == 1
    assert charge["leviers"][0]["nom"] == "preuve"


def test_l_humain_est_servi_sur_la_sortie_d_erreur() -> None:
    """La contrepartie : la banniere ne disparait pas, elle change de flux.

    Un mode qui se contenterait de SUPPRIMER l'information humaine serait une perte seche :
    celui qui lance la commande a la main doit continuer a voir ou il en est.
    """
    proc = _lancer("coherence", "--json")
    assert "██" in proc.stderr, "le logo doit rester visible pour l'humain, sur la sortie d'erreur"
    assert "█" not in proc.stdout


def test_run_json_reste_un_chemin_de_fichier() -> None:
    """Le piege voisin : `jio run ... --json CHEMIN.json` demande un FICHIER, pas un flux.

    Deux arguments du meme nom, deux sens opposes : pour `coherence`, `--json` est un drapeau ;
    pour `run`, c'est un CHEMIN. Les confondre aurait retourne la sortie du programme pour une
    commande qui n'a rien demande — et le rapport ne serait jamais ecrit.
    """
    import tempfile

    from jio.cli import main

    with tempfile.TemporaryDirectory() as dossier:
        chemin = Path(dossier) / "rapport.json"
        code = main([
            "run", "somme des pairs", "--simulate", "--task", "sum_even",
            "--json", str(chemin),
        ])
        assert code == 0
        assert chemin.is_file(), "le rapport JSON demande par chemin doit etre ecrit"
        assert json.loads(chemin.read_text(encoding="utf-8"))
