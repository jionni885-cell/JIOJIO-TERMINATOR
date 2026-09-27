"""Le parcours reel de l'utilisateur : « je donne le depot a mon IA, elle s'integre seule ».

Ce fichier teste le chemin COMPLET sur un depot ETRANGER — pas sur celui de JIO. C'est la seule
facon de repondre a la question posee : *est-ce que ca marche ailleurs que chez moi, sur un
projet qui n'a jamais entendu parler de JIO ?*

Le parcours, tel qu'une IA le suivrait :

    git clone <depot>            (un projet reel : du code, des tests, un README)
    jio start                    artefacts natifs + cablage MCP + preuve + fiche d'etat
    jio coherence                le depot est-il coherent APRES l'integration ?
    jio scan .                   l'audit du projet lui-meme
    jio auto "<objectif>"        travailler seul, une preuve par etape

Trois exigences que ce fichier tient, et qui sont celles de l'utilisateur :

  * **rien n'est casse** : le README et le code du projet appartiennent a l'utilisateur ; JIO
    ecrit SES artefacts et laisse le reste intact ;
  * **rien n'est invente** : sur une racine etrangere, les controles qui ne s'appliquent pas
    sont declares HORS PORTEE, jamais rendus « propres » (defaut trouve et corrige dans
    `jio/verify/coherence.py`) ;
  * **l'etat est lisible par la machine suivante** : la fiche `.jio/ACTIVE.md` dit ce qui a ete
    fait, avec le verdict de coherence mesure a l'instant de l'ecriture, et le plan autonome
    laisse un etat JSON avec la revision git.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from jio.cli import main


def _git(racine: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", *args],
        cwd=racine, check=True, capture_output=True,
    )


@pytest.fixture()
def depot_tiers(tmp_path: Path) -> Path:
    """Un petit projet REEL : du code, un test, un README qui parle de lui-meme."""
    racine = tmp_path / "projet-tiers"
    (racine / "src").mkdir(parents=True)
    (racine / "src" / "calcul.py").write_text(
        "def ajoute(a, b):\n    return a + b\n", encoding="utf-8"
    )
    (racine / "test_calcul.py").write_text(
        "from src.calcul import ajoute\n\n\ndef test_ajoute():\n    assert ajoute(1, 2) == 3\n",
        encoding="utf-8",
    )
    (racine / "README.md").write_text(
        "# Projet tiers\n\nUn petit projet sans aucun rapport avec JIO.\n"
        "\n```sh\npython -m pytest\n```\n",
        encoding="utf-8",
    )
    _git(racine, "init", "-q")
    _git(racine, "add", "-A")
    _git(racine, "commit", "-qm", "projet tiers")
    return racine


def _lire(chemin: Path) -> str:
    return chemin.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# 1. `jio start` sur un depot qui n'a jamais entendu parler de JIO
# --------------------------------------------------------------------------- #


def test_start_integre_un_depot_ETRANGER_sans_rien_casser(
    depot_tiers: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Artefacts natifs ecrits, cablage prouve, fiche d'etat — et le projet intact.

    C'est la promesse de `jio start` : « ton IA s'integre toute seule ». Elle ne tient que si
    trois choses sont vraies en meme temps, et ce test exige les trois :

      * les artefacts natifs existent (AGENTS.md, CLAUDE.md, opencode, Hermes, MCP) ;
      * les fichiers de l'UTILISATEUR n'ont pas bouge — un README reecrit serait une trahison ;
      * la fiche `.jio/ACTIVE.md` porte l'etat MESURE, pas une promesse.
    """
    avant_lecture = _lire(depot_tiers / "README.md")
    avant_code = _lire(depot_tiers / "src" / "calcul.py")

    code = main(["start", "--root", str(depot_tiers)])
    sortie = capsys.readouterr().out
    assert code == 0, sortie

    # 1. les artefacts natifs, pour chaque famille d'outil
    for attendu in (
        "AGENTS.md", "CLAUDE.md", "GEMINI.md",
        ".cursor/rules/jio.mdc", ".github/copilot-instructions.md",
        ".mcp.json", ".mcp.README.md", "opencode.json",
        ".opencode/agents/jio-verifier.md",
        ".opencode/agents/jio-redteam.md",
        ".hermes/skills/verification/executable-proof/SKILL.md",
        ".hermes/mcp-fragment.yaml",
    ):
        assert (depot_tiers / attendu).is_file(), attendu

    # 2. le projet appartient a l'utilisateur : rien de lui n'a change
    assert _lire(depot_tiers / "README.md") == avant_lecture
    assert _lire(depot_tiers / "src" / "calcul.py") == avant_code
    assert (depot_tiers / "test_calcul.py").is_file()

    # 3. la fiche d'etat dit ce qui a ete fait, et sur QUOI elle porte
    fiche = _lire(depot_tiers / ".jio" / "ACTIVE.md")
    assert "artefacts natifs ecrits ou mis a jour" in fiche
    assert "coherence du depot a l'instant de l'ecriture" in fiche
    assert str(depot_tiers) in fiche

    # Le cablage est PROUVE par demarrage reel du serveur, pas affirme.
    assert "PREUVE DU CABLAGE" in sortie
    assert "outil(s)" in sortie


def test_start_est_idempotent_sur_un_depot_etranger(
    depot_tiers: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Deux `jio start` d'affilee : le second n'ecrit RIEN de neuf.

    Un integrateur qu'on ne peut pas relancer sans bruit n'est pas relancable : git afficherait
    des modifications a chaque fois, et l'agent croirait que quelque chose a change. Le second
    passage doit donc rendre « deja a jour » partout.
    """
    assert main(["start", "--root", str(depot_tiers)]) == 0
    capsys.readouterr()
    empreintes = {
        rel: (depot_tiers / rel).stat().st_mtime_ns
        for rel in ("AGENTS.md", "CLAUDE.md", "opencode.json", ".mcp.json")
    }

    assert main(["start", "--root", str(depot_tiers)]) == 0
    sortie = capsys.readouterr().out
    assert "0 ecrit(s)" in sortie or "deja a jour" in sortie
    for rel, mtime in empreintes.items():
        assert (depot_tiers / rel).stat().st_mtime_ns == mtime, f"{rel} a ete reecrit"


# --------------------------------------------------------------------------- #
# 2. Le portail, sur une racine etrangere : ni faux vert, ni faux rouge
# --------------------------------------------------------------------------- #


def test_coherence_est_VERTE_apres_integration_et_le_DIT(
    depot_tiers: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Apres `jio start`, le depot est coherent — et les controles inapplicables sont declares.

    Un faux vert (rendre « propre » un controle qui n'a rien mesure) ferait croire a une
    verification qui n'a pas eu lieu ; un faux rouge (accuser un projet de ne pas avoir de
    paquet `jio/`) ferait perdre confiance dans l'outil. Le contrat est donc explicite en trois
    etats : `ok`, `KO`, `--` hors portee.
    """
    assert main(["start", "--root", str(depot_tiers)]) == 0
    capsys.readouterr()

    code = main(["coherence", "--root", str(depot_tiers)])
    sortie = capsys.readouterr().out
    assert code == 0, sortie
    assert "COHERENT" in sortie
    assert "[ok] artefacts" in sortie
    # Les trois controles qui ne s'appliquent pas ici sont declares, un par un.
    for controle in ("nombres", "environnement", "sources"):
        ligne = next(l for l in sortie.splitlines() if f"] {controle}" in l)
        assert ligne.strip().startswith("[--]"), ligne
        assert "hors de portee" in ligne
    assert "HORS PORTEE" in sortie


def test_coherence_JSON_est_exploitable_par_une_machine(
    depot_tiers: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--json` : un appelant automatise decide sur les champs, sans lire la prose."""
    assert main(["start", "--root", str(depot_tiers)]) == 0
    capsys.readouterr()
    assert main(["coherence", "--root", str(depot_tiers), "--json"]) == 0
    sortie = capsys.readouterr().out
    donnees = json.loads(sortie[sortie.index("{"):])
    assert donnees["coherent"] is True
    assert set(donnees["hors_portee"]) == {"nombres", "environnement", "sources"}
    assert {c["controle"] for c in donnees["constats"] if c["ok"]} >= {"artefacts", "plan"}


def test_un_artefact_modifie_a_la_main_rend_le_depot_INCOHERENT(
    depot_tiers: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le cas que le portail existe pour attraper : quelqu'un edite un fichier genere.

    C'est l'incoherence la plus frequente d'un depot integre — un agent « ameliore » AGENTS.md
    a la main, et la prochaine regeneration effacera son travail, ou pire, la doctrine et le
    fichier divergeront en silence.
    """
    assert main(["start", "--root", str(depot_tiers)]) == 0
    capsys.readouterr()
    (depot_tiers / "AGENTS.md").write_text("# edite a la main\n", encoding="utf-8")

    code = main(["coherence", "--root", str(depot_tiers)])
    sortie = capsys.readouterr().out
    assert code == 1
    assert "INCOHERENT" in sortie
    assert "AGENTS.md" in sortie
    assert "jio artifacts --write" in sortie

    # La reparation est celle qui est indiquee, et elle remet le depot d'aplomb.
    assert main(["artifacts", "--root", str(depot_tiers), "--write"]) == 0
    capsys.readouterr()
    assert main(["coherence", "--root", str(depot_tiers)]) == 0


# --------------------------------------------------------------------------- #
# 3. L'audit et le mode autonome, sur le projet de l'utilisateur
# --------------------------------------------------------------------------- #


def test_scan_travaille_sur_le_code_de_l_utilisateur(
    depot_tiers: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`jio scan .` sur un projet tiers : il analyse SON code, sans exiger de dependance.

    Le contrat : aucun plantage, un verdict rendu, et les documents du projet verifies comme le
    reste (un README qui annonce une commande fausse est un defaut du projet, pas de JIO).
    """
    code = main(["scan", str(depot_tiers), "--no-learn"])
    sortie = capsys.readouterr().out
    assert code in (0, 1), sortie
    assert "SCAN" in sortie
    assert str(depot_tiers) in sortie


def test_auto_laisse_un_etat_RELISIBLE_avec_la_revision_git(
    depot_tiers: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Le plan autonome sur un depot tiers : etat JSON, revision git, et rien d'invente.

    La revision n'est pas decorative : reprendre un plan apres un changement de revision, c'est
    changer de monde (arXiv 2608.29381). Le fichier doit permettre de le SAVOIR — meme si la
    decision reste humaine.
    """
    assert main(["start", "--root", str(depot_tiers)]) == 0
    capsys.readouterr()

    code = main([
        "auto", "corriger le calcul de src/calcul.py", "--root", str(depot_tiers),
        "--budget", "1", "--json",
    ])
    sortie = capsys.readouterr().out
    assert code in (0, 1, 2), sortie
    etat = json.loads((depot_tiers / ".jio" / "plan.json").read_text(encoding="utf-8"))
    assert etat["revision"], "la revision git doit etre enregistree"
    assert etat["etat"] in {"termine", "bloque", "budget", "refuse"}
    assert etat["etapes"], "chaque etape doit etre listee, meme non tentee"
    assert all(e["preuve"] for e in etat["etapes"]), "aucune etape sans preuve"
    # Le fichier de l'utilisateur est intact, MOT POUR MOT : c'est la promesse de `jio start`.
    assert _lire(depot_tiers / "README.md") == (
        "# Projet tiers\n\nUn petit projet sans aucun rapport avec JIO.\n"
        "\n```sh\npython -m pytest\n```\n"
    )
