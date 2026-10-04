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
    """Deuxieme passage : rien de neuf — y compris la fiche d'etat, et jusqu'a sa DATE.

    La deuxieme execution met a jour les dates de modification de 29 fichiers : dans git, cela
    ressemble a un changement. La bonne reponse est « deja a jour », et ce test l'exige.

    CE TEST EXCLUAIT `.jio/ACTIVE.md` DE LA COMPARAISON, avec une justification fausse : « c'est
    un RAPPORT, pas un artefact, donc il change legitimement ». Il ne changeait pas legitimement :
    la fiche portait la DUREE du portail (« COHERENT (9 controles, 1.2s) »), donc deux executions
    identiques produisaient deux fiches differentes — et le README promettait, noir sur blanc,
    « relancee, elle ne reecrit rien ». Le test avait ete ecrit pour convenir au comportement au
    lieu de tenir la promesse, ce qui est la facon la plus discrete de laisser passer un defaut.

    L'exclusion est retiree, et la DATE est comparee aussi : « ne reecrit rien » veut dire que le
    fichier n'est pas touche du tout. Ecrire un contenu identique laisse git propre et fait
    quandt meme bouger la date de modification — donc apparait comme un changement pour tout
    outil qui la regarde (git status ne la voit pas, un cache de build si).
    """
    def contenu() -> dict[Path, str]:
        # TOUS les fichiers, la fiche d'etat comprise : c'est elle qui a menti le plus longtemps.
        return {
            p: p.read_text(encoding="utf-8")
            for p in sorted(tmp_path.rglob("*"))
            if p.is_file()
        }

    cmd_start(_args(tmp_path))
    etat = contenu()
    fiche = tmp_path / ".jio" / "ACTIVE.md"
    date_avant = fiche.stat().st_mtime_ns
    assert cmd_start(_args(tmp_path)) == 0
    assert contenu() == etat, "un deuxieme `jio start` a modifie des fichiers"
    assert fiche.stat().st_mtime_ns == date_avant, (
        "la fiche d'etat a ete REEECRITE a l'identique : la promesse « ne reecrit rien » porte "
        "sur le fichier, pas sur son contenu"
    )


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


def test_la_fiche_active_porte_l_etat_de_COHERENCE_mesure(tmp_path: Path) -> None:
    """`.jio/ACTIVE.md` dit si le depot tient debout, et il le dit APRES l'avoir mesure.

    Une IA qui herite d'un depot doit savoir s'il est sain : sinon elle prendra pour references
    des artefacts perimes, des chiffres faux ou des commandes inexistantes — et ses propres
    travaux partiront de la. La fiche est le premier fichier qu'elle lit, donc l'etat doit y
    etre, mesure a l'instant de l'ecriture.
    """
    import re

    from jio.cli import _fiche_active

    fiche = _fiche_active(
        tmp_path, ["opencode"], ["opencode"], presents=30, total=30, a_jour=30,
        coherence="COHERENT (9 controles)",
    )
    assert "coherence du depot a l'instant de l'ecriture : COHERENT (9 controles)" in fiche
    # Sans mesure, la fiche le DIT au lieu d'affirmer : c'est la meme regle que partout ailleurs.
    assert "non mesuree" in _fiche_active(tmp_path, [], [], 0)
    # AUCUNE DUREE dans la fiche. C'est ce qui la rendait non-idempotente : deux executions
    # identiques ecrivaient « 1.2s » puis « 1.4s ». Une duree n'est pas un fait dont un agent a
    # besoin, et elle transforme un fichier d'etat en fichier qui bat.
    # La verification porte sur la LIGNE du verdict, pas sur toute la fiche : le texte cite
    # « sort en 1 » (le code de sortie de `jio clarify`), et une recherche globale sur « 1 s »
    # y voit une duree. Une recherche trop large est une fausse alerte qui apprend a elargir
    # les exceptions ; une recherche trop etroite ne voit rien. Celle-ci vise la ligne.
    ligne = next(
        l for l in fiche.splitlines()
        if l.startswith("- coherence du depot a l'instant de l'ecriture :")
    )
    assert not re.search(r"\d+([.,]\d+)?\s*(s|ms)\b", ligne), (
        f"la ligne du verdict porte une duree ({ligne!r}) : `jio start` redeviendra "
        "non-idempotent, parce que deux executions identiques produiront deux fiches differentes"
    )


def test_la_fiche_est_reecrite_quand_l_etat_CHANGE(tmp_path: Path) -> None:
    """L'idempotence ne doit pas etre obtenue en gelant la fiche.

    Le risque d'un « on n'ecrit que si c'est different » : un generateur qui n'ecrit plus jamais
    et laisse une fiche perimee — c'est-a-dire un mensonge de retard, la classe d'erreur que ce
    depot traque partout. Ce test tient l'autre bord : quand l'etat mesurable change, la fiche
    change, et le DIT.
    """
    from jio.cli import _fiche_active

    avant = _fiche_active(tmp_path, [], [], 0, coherence="COHERENT (9 controles)")
    apres = _fiche_active(
        tmp_path, ["opencode"], ["opencode"], presents=12, total=30, a_jour=12,
        coherence="2 controle(s) en echec : sources",
    )
    assert avant != apres
    assert "2 controle(s) en echec : sources" in apres, "le verdict de la porte doit suivre"
    assert "artefacts natifs : 12/30 present(s)" in apres
    assert "cablage MCP : opencode" in apres


def test_la_fiche_enseigne_le_routeur_de_procedures() -> None:
    """Une IA qui arrive doit savoir que les procedures se DEMANDENT, et comment.

    Sans cette section, la bibliotheque de competences reste une ressource que personne
    n'interroge : cinq commandes ecrites dans la fiche valent mieux qu'un fichier de plus a
    charger d'avance — la fiche est lue, elle n'est pas devinee.
    """
    from jio.cli import _fiche_active

    fiche = _fiche_active(Path("/tmp/projet"), ["opencode"], ["opencode"], 30, 30, 30, "COHERENT")
    assert "jio skills" in fiche
    assert "jio sorties" in fiche
    assert "--sans-competences" in fiche
    assert "6424 jetons" in fiche
    # La fiche reste dans la zone ou un agent la LIT (au-dela d'une centaine de lignes, un
    # fichier de contexte est survole) : ce test est le garde-fou du budget.
    assert len(fiche.splitlines()) < 110



def test_start_INSTALLE_les_competences_la_ou_hermes_les_lit(tmp_path, monkeypatch, capsys) -> None:
    """La demande qui a motive cette etape : « quand je donne le depot a mon IA, elle s'integre
    et fait tout ce qu'il faut » — sans `cp -r` a taper a la main.

    Hermes lit `~/.hermes/skills/` ; le depot les ecrivait dans `.hermes/skills/`. Entre les
    deux, une etape manuelle que personne ne fait.
    """
    from jio.cli import main

    projet = tmp_path / "projet"
    projet.mkdir()
    (projet / ".git").mkdir()
    maison = tmp_path / "hermes"
    (maison / "skills").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(maison))
    monkeypatch.chdir(projet)

    code = main(["start"])
    sortie = capsys.readouterr().out

    assert code == 0
    assert "COMPETENCES HERMES" in sortie
    installees = list((maison / "skills").rglob("SKILL.md"))
    assert len(installees) == 12, f"12 procedures attendues, {len(installees)} installees"
    assert "total : 13 copie(s)" in sortie or "copie(s)" in sortie
    # La fiche que lit l'IA porte l'ETAT de cette installation : elle doit pouvoir savoir si
    # son outil a reellement les procedures, sans deviner.
    fiche = (projet / ".jio" / "ACTIVE.md").read_text(encoding="utf-8")
    assert "COMPETENCES HERMES :" in fiche


def test_start_ne_cree_pas_le_dossier_hermes_d_un_utilisateur_qui_ne_l_a_jamais_lance(
    tmp_path, monkeypatch, capsys
) -> None:
    """Une installation surprise dans le dossier personnel n'est pas une integration."""
    from jio.cli import main

    projet = tmp_path / "projet"
    projet.mkdir()
    (projet / ".git").mkdir()
    maison = tmp_path / "jamais-cree"
    monkeypatch.setenv("HERMES_HOME", str(maison))
    monkeypatch.chdir(projet)

    main(["start"])
    sortie = capsys.readouterr().out

    assert not maison.exists()
    assert "n'existe pas encore" in sortie
    assert "mkdir -p" in sortie


def test_start_sans_hermes_n_installe_rien(tmp_path, monkeypatch, capsys) -> None:
    from jio.cli import main

    projet = tmp_path / "projet"
    projet.mkdir()
    (projet / ".git").mkdir()
    maison = tmp_path / "hermes"
    (maison / "skills").mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(maison))
    monkeypatch.chdir(projet)

    main(["start", "--sans-hermes"])
    capsys.readouterr()

    assert list((maison / "skills").rglob("SKILL.md")) == []
