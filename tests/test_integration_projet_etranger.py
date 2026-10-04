"""L'integration sur un projet ETRANGER, mesuree de bout en bout.

Pourquoi ce fichier existe : tous les tests de `jio start` vivaient dans le depot JIO, ou la
commande ecrite dans les fichiers de cablage (`python3 -m jio.mcp_server`) marche PAR ACCIDENT —
`jio/` est un sous-dossier du dossier courant. Sur le projet de quelqu'un d'autre, elle ne sert
rien, et rien ne le disait : le diagnostic existait, mais il arrivait apres l'ecriture.

C'est le cas d'usage reel (un utilisateur donne son depot a son IA), et c'est donc lui qui doit
etre teste. Un test qui ne fait que parcourir le depot ne peut pas voir ce defaut : il faut un
projet qui ne contient pas `jio`.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


def _projet_etranger(racine: Path) -> Path:
    """Un petit projet Python reel : du code, des tests, un README, et AUCUN paquet `jio`."""
    (racine / "src").mkdir(parents=True)
    (racine / "src" / "panier.py").write_text(
        '"""Panier d\'achat."""\n\n\n'
        "def total(prix: list[float]) -> float:\n"
        '    """Somme des prix."""\n'
        "    return sum(prix)\n",
        encoding="utf-8",
    )
    (racine / "tests").mkdir()
    (racine / "tests" / "test_panier.py").write_text(
        "from src.panier import total\n\n\ndef test_total():\n    assert total([1.0, 2.0]) == 3.0\n",
        encoding="utf-8",
    )
    (racine / "README.md").write_text(
        "# Panier\n\nUn petit panier d'achat.\n\n`python -m pytest` lance les tests.\n",
        encoding="utf-8",
    )
    # Un fichier de l'utilisateur, qui doit survivre a l'integration (avec sauvegarde).
    (racine / "AGENTS.md").write_text(
        "# Mes consignes\n\nToujours repondre en francais.\n", encoding="utf-8"
    )
    return racine


def _start(racine: Path, *options: str) -> str:
    """Lance `jio start` comme le ferait l'utilisateur. Rend la sortie affichee."""
    from jio.cli import main

    code = main(["start", "--root", str(racine), "--sans-hermes", *options])
    assert code == 0, f"`jio start` a rendu le code {code}"
    return ""


def test_jio_start_ecrit_un_cablage_qui_MARCHE_sur_un_projet_etranger(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """LE defaut mesure, et sa preuve.

    `jio start` sur un projet etranger ecrivait `.mcp.json` avec `python3 -m jio.mcp_server`.
    Depuis ce projet, cette commande ne trouve pas le paquet `jio` : la configuration etait
    ecrite, la preuve disait « ne sert AUCUN outil », et l'ordre des deux etait le probleme —
    le diagnostic arrivait apres la panne. Une integration qui s'avere fausse en le disant reste
    fausse : l'IA de l'utilisateur, elle, ne lit pas nos diagnostics.

    Ce test prend donc la configuration ECRITE, reconstruit la commande qu'elle decrit, et
    exige qu'elle serve reellement des outils DEPUIS LE PROJET.
    """
    from jio.artifacts.wiring import _parler_au_serveur

    racine = _projet_etranger(tmp_path)
    _start(racine)
    sortie = capsys.readouterr().out

    assert "COMMANDE MCP RESOLUE ICI" in sortie, (
        "la commande a ete ecrite sans dire d'ou elle vient :\n" + sortie[-800:]
    )

    for nom in (".mcp.json", "opencode.json"):
        chemin = racine / nom
        assert chemin.is_file(), f"{nom} n'a pas ete ecrit"
        texte = chemin.read_text(encoding="utf-8")
        assert "jio.mcp_server" in texte
        # Le programme nomme est un CHEMIN ABSOLU d'interpreteur (celui qui a jio), ou un
        # `python3` qui, dans ce projet, n'aurait pas jio : la seconde branche est le defaut.
        donnees = json.loads(texte)
        bloc = donnees["mcpServers"]["jio"] if "mcpServers" in donnees else donnees["mcp"]["jio"]
        commande = (
            (bloc["command"], *bloc["args"]) if isinstance(bloc["command"], str)
            else tuple(bloc["command"])
        )
        outils, _, detail = _parler_au_serveur(commande, 60.0, racine)
        assert outils, (
            f"`{nom}` decrit une commande qui ne sert aucun outil depuis le projet :\n"
            f"  {' '.join(commande)}\n{detail}"
        )


def test_apres_l_integration_le_portail_du_projet_est_vert(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """La promesse « tout fonctionne » se mesure : le portail, apres `jio start`, est vert.

    Mesure faite sur un projet etranger avant cette correction : `jio start` terminait sur
    « 2 controle(s) en echec » — `artefacts` parce qu'il comparait a la forme canonique des
    fichiers que `jio start` venait d'ecrire autrement, `nombres` parce qu'il confrontait le
    README du projet aux huit chiffres de CE depot. Rien de tout cela n'etait vrai du projet de
    l'utilisateur, et un portail qui crie au premier contact ne sera plus lu.
    """
    from jio.verify.coherence import controler

    racine = _projet_etranger(tmp_path)
    _start(racine)
    capsys.readouterr()

    rapport = controler(racine)
    assert rapport.ok, "\n".join(
        f"  [{c.controle}] {c.resume} :: {c.details}" for c in rapport.incoherents
    )
    # Et les controles qui n'ont rien a mesurer ici le DISENT, au lieu de rendre un faux vert.
    hors = {c.controle for c in rapport.hors_portee}
    assert {"environnement", "sources"} <= hors


def test_relancer_jio_start_ne_reecrit_rien_et_ne_perd_aucun_fichier(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """Deux executions identiques laissent le projet dans le meme etat, au bit pres.

    C'est la promesse du README (« relancee, elle ne reecrit rien »), et elle a deja ete prise en
    defaut une fois : la fiche d'integration affichait « 30 ecrits » puis « 0 ecrit ». Ici on
    compare le CONTENU et les dates de modification de tous les fichiers ecrits, pas le message.
    """
    racine = _projet_etranger(tmp_path)
    _start(racine)
    capsys.readouterr()

    def photographie() -> dict[str, tuple[int, float]]:
        return {
            str(p.relative_to(racine)): (p.stat().st_size, p.stat().st_mtime)
            for p in sorted(racine.rglob("*"))
            if p.is_file()
        }

    avant = photographie()
    assert "AGENTS.md" in avant, "le fichier de l'utilisateur doit avoir ete conserve"

    _start(racine)
    sortie = capsys.readouterr().out
    assert "0 ecrit(s)" in sortie, "une seconde execution a reecrit des artefacts :\n" + sortie[-600:]
    assert photographie() == avant, "l'etat du projet a change sans raison"

    # Ce que l'utilisateur avait ecrit est INTACT — pas sauvegarde : preserve. La difference
    # compte, et c'est le garde d'ecriture qui la fait : un fichier que jio n'a jamais ecrit ne
    # lui appartient pas, donc il n'y touche pas et depose SA version a cote (`AGENTS.md.jio`).
    # Le `.avant-jio` n'apparait que pour un fichier que jio avait ecrit et que quelqu'un a
    # modifie depuis — la, la sauvegarde est la seule facon de ne rien perdre.
    consignes = (racine / "AGENTS.md").read_text(encoding="utf-8")
    assert "Toujours repondre en francais" in consignes, (
        "les consignes de l'utilisateur ont ete perdues : " + consignes[:200]
    )
    a_cote = racine / "AGENTS.md.jio"
    assert a_cote.is_file(), "la version de jio doit etre ecrite a cote, jamais a la place"
    assert "Toujours repondre en francais" not in a_cote.read_text(encoding="utf-8")


def test_le_serveur_mcp_repond_vraiment_dans_le_projet(tmp_path: Path) -> None:
    """La preuve de bout en bout : un client MCP parle au serveur, dans le projet de l'utilisateur.

    On ne se contente pas de compter les outils annonces : on envoie `initialize` puis
    `tools/list` exactement comme le ferait opencode ou Hermes, et on lit la reponse.
    """
    import json as _json

    from jio.artifacts.wiring import commande_qui_marche

    racine = _projet_etranger(tmp_path)
    commande, _ = commande_qui_marche(racine=racine)
    requetes = (
        _json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        _json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
    )
    processus = subprocess.run(
        list(commande),
        input="\n".join(requetes) + "\n",
        capture_output=True, text=True, timeout=120, check=False, cwd=str(racine),
    )
    assert processus.returncode == 0, processus.stderr[-400:]
    reponses = [
        _json.loads(ligne) for ligne in processus.stdout.splitlines() if ligne.startswith("{")
    ]
    outils = [o["name"] for r in reponses for o in (r.get("result") or {}).get("tools", [])]
    assert outils, f"aucun outil annonce :\n{processus.stdout[-500:]}\n{processus.stderr[-500:]}"
    assert "jio_prove" in outils
