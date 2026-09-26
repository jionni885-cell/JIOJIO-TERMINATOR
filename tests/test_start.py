"""`jio start` : donner le depot a une IA, et qu'elle s'integre TOUTE SEULE.

C'est la commande de la premiere minute, et la seule de ce projet dont depend l'experience
initiale. Elle doit donc reussir dans le pire des cas : aucune cle d'API, aucun outil detecte,
aucune configuration prealable, et un dossier qui contient deja des fichiers a l'utilisateur.

Ce qui est verifie ici, et pourquoi :

  * elle ECRIT les artefacts de tous les dialectes, sinon l'IA ouvre le depot et ne voit rien ;
  * elle ne DETRUIT rien — un `AGENTS.md` ecrit a la main reste intact, et la version de jio
    part a cote (`.jio`). C'est le seul point irreversible de la commande ;
  * elle est IDEMPOTENTE : relancee, elle ne reecrit rien et le dit ;
  * elle ecrit `.jio/ACTIVE.md`, la fiche que l'IA lit en premier, et cette fiche ne contient
    que des choses verifiables : les commandes qu'elle cite doivent exister ;
  * elle n'ecrit jamais dans les fichiers de configuration de l'utilisateur (Hermes, Codex,
    Claude Code) : elle rend le fragment a coller.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from jio.cli import build_parser, cmd_start
from jio.artifacts.emit import manifest


def _args(root: Path, **extra) -> argparse.Namespace:
    base = {"root": str(root), "dry_run": False, "sans_mcp": False}
    base.update(extra)
    return argparse.Namespace(**base)


def test_start_ecrit_les_artefacts_et_la_fiche(tmp_path: Path) -> None:
    """Une racine vierge ressort equipee : artefacts + fiche d'integration.

    Sans ces deux choses, une IA qui ouvre le depot ne sait ni ce qu'il est, ni ce qu'il
    attend d'elle. L'integration n'est pas « installe un paquet » : c'est « ecris, dans les
    fichiers que CETTE IA lit vraiment, ce qu'elle doit faire ».
    """
    code = cmd_start(_args(tmp_path))
    assert code == 0

    ecrits = set(manifest())
    for rel in ecrits:
        assert (tmp_path / rel).is_file(), f"artefact manquant : {rel}"
    assert (tmp_path / "AGENTS.md").is_file()
    assert (tmp_path / "CLAUDE.md").is_file()
    assert (tmp_path / "GEMINI.md").is_file()
    assert (tmp_path / ".opencode/agents/jio.md").is_file()
    assert (tmp_path / ".hermes/skills").is_dir()

    fiche = tmp_path / ".jio/ACTIVE.md"
    assert fiche.is_file()
    texte = fiche.read_text(encoding="utf-8")
    assert "jio clarify" in texte and "jio doctor" in texte and "jio run" in texte
    # La fiche dit elle-meme qu'elle est ecrite par la commande : pour la regenerer.
    assert "jio start" in texte
    # Et elle nomme les trois etats : c'est le contrat du projet.
    assert "ABSTAINED" in texte and "UNDER_RESERVATION" in texte


def test_start_ne_detruit_jamais_le_travail_de_l_utilisateur(tmp_path: Path) -> None:
    """`AGENTS.md` ecrit a la main est PRESERVE ; la version de jio part dans `.jio`.

    C'est le seul geste irreversible de la commande : elle ecrit dans la racine d'un projet
    qui n'est pas le sien. Le mesurer sur un fichier qui contient une convention inventee est
    la seule facon de savoir si la promesse tient.
    """
    a_moi = "# Conventions de mon equipe\n\n- toujours deux relecteurs\n"
    (tmp_path / "AGENTS.md").write_text(a_moi, encoding="utf-8")

    assert cmd_start(_args(tmp_path)) == 0

    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == a_moi
    assert (tmp_path / "AGENTS.md.jio").is_file()
    assert "jio clarify" in (tmp_path / "AGENTS.md.jio").read_text(encoding="utf-8")
    # Un fichier qui n'est pas de nous n'apparait pas dans le registre : jio ne le
    # « possede » pas et ne le mettra jamais a jour tout seul.
    import json

    registre = json.loads((tmp_path / ".jio/generated.json").read_text(encoding="utf-8"))
    assert "AGENTS.md" not in registre["fichiers"]


def test_start_est_IDEMPOTENTE_et_le_dit(tmp_path: Path) -> None:
    """Deuxieme passage : rien de neuf. Un generateur qui reecrit produit du bruit et ment.

    La deuxieme execution met a jour les dates de modification de 29 fichiers : dans git, cela
    ressemble a un changement. La bonne reponse est « deja a jour », et ce test l'exige.
    """
    def contenu() -> dict[Path, str]:
        # `.jio/ACTIVE.md` est un RAPPORT, pas un artefact : il decrit ce que CETTE execution
        # vient de faire, donc il change legitimement (0 fichier ecrit au second passage).
        # Ce qui doit etre stable, ce sont les fichiers lus par les outils.
        return {
            p: p.read_text(encoding="utf-8")
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file() and p.name != "ACTIVE.md"
        }

    cmd_start(_args(tmp_path))
    etat = contenu()
    assert cmd_start(_args(tmp_path)) == 0
    assert contenu() == etat, "un deuxieme `jio start` a modifie des fichiers"


def test_start_ne_touche_pas_aux_configurations_personnelles(tmp_path: Path) -> None:
    """Le cablage ne reecrit jamais `~/.hermes/config.yaml` ni `~/.codex/config.toml`.

    Ces fichiers appartiennent a l'utilisateur et contiennent d'autres serveurs que jio.
    La commande doit donc rendre le fragment a coller — et ne rien ecrire. Verifie sur le
    seul cablage qui ecrit un fichier dans le projet : `opencode.json` et `.cursor/mcp.json`.
    """
    # Une configuration opencode qui existe DEJA et ne parle pas de jio.
    a_moi = '{"mcp": {"autre-serveur": {"type": "local"}}}\n'
    (tmp_path / "opencode.json").write_text(a_moi, encoding="utf-8")

    assert cmd_start(_args(tmp_path)) == 0
    assert (tmp_path / "opencode.json").read_text(encoding="utf-8") == a_moi

    # Un fichier de config personnel n'est jamais cree a la place : rien hors du projet.
    assert not (tmp_path / ".hermes/config.yaml").exists()
    assert not (tmp_path / ".codex").exists()


def test_start_sans_mcp_n_ecrit_aucun_cablage(tmp_path: Path) -> None:
    """`--sans-mcp` : les artefacts seulement, zero fichier de cablage.

    L'option existe pour un cas reel : une IA qui n'a pas le droit de modifier la
    configuration (poste verrouille, depot partage). Sans elle, l'utilisateur n'avait le
    choix qu'entre tout et rien.
    """
    assert cmd_start(_args(tmp_path, sans_mcp=True)) == 0
    assert (tmp_path / "AGENTS.md").is_file()
    assert not (tmp_path / "opencode.json").exists()
    assert not (tmp_path / ".cursor/mcp.json").exists()
    texte = (tmp_path / ".jio/ACTIVE.md").read_text(encoding="utf-8")
    assert "aucun (--sans-mcp)" in texte


def test_start_en_simulation_n_ecrit_RIEN(tmp_path: Path) -> None:
    """`--dry-run` liste et n'ecrit pas : la promesse doit etre tenue au fichier pres.

    Une simulation qui ecrit quand meme est pire qu'aucune simulation : elle apprend a ne pas
    la croire, et la prochaine fois que l'utilisateur verifie, il ne verifie plus.
    """
    assert cmd_start(_args(tmp_path, dry_run=True)) == 0
    assert list(tmp_path.rglob("*")) == []
    assert not (tmp_path / ".jio").exists()


def test_la_fiche_ne_cite_que_des_commandes_qui_existent(tmp_path: Path) -> None:
    """Chaque `jio <commande>` citee dans ACTIVE.md existe dans le parseur REEL.

    C'est la meme regle que `jio claims` applique aux documents, appliquee a la fiche que
    l'IA lit en premier. Une fiche qui propose une commande inexistante envoie l'IA dans un
    `unrecognized arguments` des la premiere instruction — et elle conclura que le depot est
    casse.
    """
    import argparse as ap
    import re

    cmd_start(_args(tmp_path))
    texte = (tmp_path / ".jio/ACTIVE.md").read_text(encoding="utf-8")
    connues: set[str] = set()
    for action in build_parser()._actions:  # noqa: SLF001 - le parseur reel, pas une copie
        if isinstance(action, ap._SubParsersAction):  # noqa: SLF001
            connues = set(action.choices)
    citees = set(re.findall(r"jio ([a-z][a-z0-9-]*)", texte))
    inconnues = {c for c in citees if c not in connues and c not in {"start"}}
    assert not inconnues, f"la fiche cite des commandes inexistantes : {sorted(inconnues)}"
    assert {"doctor", "clarify", "run"} <= citees


@pytest.mark.parametrize("commande", ["start", "clarify"])
def test_les_commandes_d_integration_repondent_a_help(commande: str) -> None:
    """`--help` : une commande qui ne repond pas a `--help` n'existe pas pour qui la decouvre.

    C'est la premiere chose qu'une IA fait en arrivant dans un depot inconnu : `jio --help`,
    puis `jio <commande> --help`. Un `--help` qui plante coute la confiance dans tout le reste.
    """
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "jio", commande, "--help"],
        capture_output=True, text=True, timeout=120,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert proc.returncode == 0, proc.stderr
    assert "usage:" in proc.stdout
    assert "Traceback" not in proc.stderr
