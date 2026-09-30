"""Le regime de mesure fait partie du chiffre : la fidelite des temoins doit se regler.

Ce fichier verrouille l'ajout du drapeau `jio ablation --fidelite`, et surtout la RAISON de son
existence.

Le raisonnement, mesure en main : `jio ablation` mesure ce que chaque brique apporte en la
retirant. Mais elle fournissait toujours au moteur des temoins PARFAITS (`fidelite=1.0`), y
compris dans le mode sans oracle — celui ou, dans la vraie vie, personne ne donne les tests et
c'est le modele qui les ecrit. Avec des temoins parfaits, il n'y a rien a rattraper : la
verification ne peut pas montrer mieux que ce qu'elle a. Resultat mesure a cette configuration :
la plupart des leviers ressortaient « NON DISTINGUABLE », y compris ceux dont tout le role est
d'attraper ce qu'un temoin imparfait laisse passer (mutation, red-team, consensus, porte).

Un levier mesure dans un regime ou il ne peut rien faire n'est pas un levier inutile : c'est une
mesure inadaptee. La fidelite est donc devenue un PARAMETRE, annonce dans l'en-tete du rapport,
et borne dans [0, 1] — une valeur hors bornes ferait dire au rapport autre chose que ce qui a
ete mesure.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _lancer(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "jio", "ablation", *args],
        cwd=str(REPO), capture_output=True, text=True, timeout=3000,
    )


def test_la_fidelite_est_annoncee_dans_le_rapport() -> None:
    """Un chiffre sans son regime ne se compare pas : l'en-tete doit dire la fidelite."""
    proc = _lancer("--levers", "preuve", "--missions", "2", "--sans-oracle",
                   "--fidelite", "0.6", "--json")
    assert proc.returncode == 0, proc.stderr[-800:]
    donnees = json.loads(proc.stdout)
    assert donnees["n_missions"] == 2
    # Le rapport humain (sur la sortie d'erreur en mode machine) porte le regime.
    assert "fidelite 60%" in proc.stderr, proc.stderr[-600:]


def test_sans_oracle_et_fidelite_parfaite_n_annonce_rien_de_faux() -> None:
    """A fidelite 1.0, l'en-tete ne doit pas parler de temoins contrefaits : ce serait faux."""
    proc = _lancer("--levers", "preuve", "--missions", "2", "--sans-oracle",
                   "--fidelite", "1.0", "--json")
    assert proc.returncode == 0, proc.stderr[-800:]
    assert "CONTREFaite" not in proc.stderr


def test_une_fidelite_hors_bornes_est_bornee() -> None:
    """2.0 ou -1 ne doivent pas inventer un regime : la valeur est ramenee dans [0, 1].

    Sans ce bornage, `--fidelite 2.0` annoncerait « 200% » et le rapport porterait un regime
    qui n'existe pas.
    """
    proc = _lancer("--levers", "preuve", "--missions", "2", "--sans-oracle",
                   "--fidelite", "2.0", "--json")
    assert proc.returncode == 0, proc.stderr[-800:]
    assert "200%" not in proc.stderr
