"""Un chiffre annonce dans la documentation doit etre VRAI, ou ne pas y etre.

Le README annoncait « 187 tests verts » alors que la suite en comptait 520. Personne ne
recalcule un compteur en lisant une page — et c'est exactement le genre d'affirmation qui
detruit la confiance dans tout le reste du document. `jio claims` ne peut pas l'attraper :
un compteur de tests n'est ni un calcul, ni un bloc de code, ni un chemin.

Ce fichier est la version verifiable de ces chiffres. Il ne fait pas confiance a la
documentation, il la CONFRONTE a la realite :

  * le nombre de tests est collecte par un vrai `pytest --collect-only` (aucun test n'est
    execute dans le sous-processus, donc pas de recursion) ;
  * le nombre de competences et d'agents vient des definitions qui les generent.

La regle appliquee est celle du projet : soit le chiffre est verifiable, soit il n'est pas
ecrit. Un test qui echoue ici dit exactement quoi corriger dans le README.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from jio.artifacts.definitions import AGENTS, SKILLS

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"


def _collecte() -> int:
    """Le nombre de tests reellement collectes, mesure par pytest lui-meme.

    Deux formes de sortie, et il faut les deux : `pytest -q --collect-only` affiche un
    TOTAL (« N tests collected ») sur certaines versions, et un compte PAR FICHIER
    (`tests/test_x.py: 8`) sur d'autres. Le premier jet ne lisait que la premiere forme et
    echouait ici — un test qui ne sait pas lire sa propre mesure n'en est pas une.
    """
    resultat = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    texte = resultat.stdout

    for ligne in reversed(texte.splitlines()):
        correspondance = re.search(r"(\d+) tests? collected", ligne)
        if correspondance:
            return int(correspondance.group(1))

    # Forme « par fichier » : on somme, et on verifie qu'on a bien trouve quelque chose.
    par_fichier = re.findall(r"^\S+\.py: (\d+)$", texte, re.MULTILINE)
    if par_fichier:
        return sum(int(x) for x in par_fichier)

    pytest.fail(f"impossible de lire le nombre de tests :\n{texte[-500:]}")


def test_le_nombre_de_tests_annonce_est_le_vrai() -> None:
    """Le compteur du README est confronte a la suite reelle, pas a une memoire."""
    texte = README.read_text(encoding="utf-8")
    annonces = re.findall(r"(\d+) tests? verts?", texte)
    assert annonces, "le README n'annonce plus de nombre de tests : supprimer ce test ou l'ecrire"

    reel = _collecte()
    for annonce in annonces:
        assert int(annonce) == reel, (
            f"le README annonce {annonce} tests verts, la suite en collecte {reel}. "
            f"Ecrire {reel} dans README.md (ou retirer le chiffre : un chiffre faux coute "
            "plus cher qu'une absence de chiffre)."
        )


def test_le_nombre_de_competences_et_d_agents_annonce_est_le_vrai() -> None:
    """Memes chiffres verifies pour la bibliotheque de competences et les agents.

    Ils sont ecrits en clair a deux endroits du README (le budget de contexte et le
    paragraphe de l'ecosysteme), parce qu'un lecteur a besoin de les voir la ou il lit.
    """
    texte = README.read_text(encoding="utf-8")
    attendu_competences = len(SKILLS)
    attendu_agents = len(AGENTS)

    # Motif ANCRE : « les N competences » / « les N agents ». Sans l'ancre, la phrase
    # « | 2 agents | » d'un tableau (la taille d'un panel, pas la bibliotheque d'agents)
    # etait prise pour une annonce — un faux positif dans un controle de documentation,
    # c'est-a-dire exactement ce que ce projet passe son temps a retirer.
    for motif, attendu, quoi in (
        (r"[Ll]es (\d+) compétences", attendu_competences, "competences"),
        (r"[Ll]es (\d+) agents", attendu_agents, "agents"),
    ):
        trouvees = re.findall(motif, texte)
        assert trouvees, f"le README n'annonce plus le nombre de {quoi}"
        for annonce in trouvees:
            assert int(annonce) == attendu, (
                f"le README annonce {annonce} {quoi}, il y en a {attendu} "
                "(jio/artifacts/definitions.py)"
            )
