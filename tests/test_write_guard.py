"""Ecrire des artefacts ne doit JAMAIS detruire le travail de quelqu'un d'autre.

Le cas qui a motive ce module : `AGENTS.md` est le fichier ou un projet met ses propres
conventions, editees a la main. Une commande qui l'ecrase fait exactement ce que ce projet
reproche aux agents — modifier ce qu'elle n'a pas cree. Le script d'installation appliquait
deja la bonne regle (« existe deja — non ecrase »), et le cablage MCP aussi (`brancher`
n'est jamais destructif) : deux regles pour un meme risque, c'est une regle qui tombe.

Un fichier absent est ecrit. Un fichier qui PORTE NOTRE MARQUE est a nous : on le met a
jour. Un fichier qui ne la porte pas appartient a l'utilisateur : on ecrit notre version a
cote et on dit exactement ou la prendre.
"""

from __future__ import annotations

from pathlib import Path

from jio.artifacts.write_guard import Decision, ecrire_manifest
from jio.cli import main

NOTRE = "> Genere par `jio artifacts`.\n\ncontenu jio\n"
A_EUX = "# Mes conventions\n\n- ne jamais utiliser `eval`\n"


def _actions(decisions: list[Decision]) -> list[tuple[str, str]]:
    return [(d.chemin, d.action) for d in decisions]


# --------------------------------------------------------------------------- #
# 1. Les trois cas, et aucun autre
# --------------------------------------------------------------------------- #


def test_un_fichier_absent_est_ecrit(tmp_path: Path) -> None:
    decisions = ecrire_manifest(tmp_path, {"GEMINI.md": NOTRE})
    assert _actions(decisions) == [("GEMINI.md", "ecrit")]
    assert (tmp_path / "GEMINI.md").read_text(encoding="utf-8") == NOTRE


def test_un_fichier_a_jour_n_est_pas_reecrit(tmp_path: Path) -> None:
    """Sinon chaque `--write` toucherait 29 dates de modification et bruitrait `git status`."""
    (tmp_path / "CLAUDE.md").write_text(NOTRE, encoding="utf-8")
    avant = (tmp_path / "CLAUDE.md").stat().st_mtime_ns
    decisions = ecrire_manifest(tmp_path, {"CLAUDE.md": NOTRE})
    assert _actions(decisions) == [("CLAUDE.md", "inchange")]
    assert (tmp_path / "CLAUDE.md").stat().st_mtime_ns == avant


def test_un_fichier_genere_par_jio_est_mis_a_jour(tmp_path: Path) -> None:
    (tmp_path / "CLAUDE.md").write_text(
        "> Genere par `jio artifacts`. Source unique : `jio/artifacts/doctrine.py`.\n\nvieux\n",
        encoding="utf-8",
    )
    decisions = ecrire_manifest(tmp_path, {"CLAUDE.md": NOTRE})
    assert _actions(decisions) == [("CLAUDE.md", "remplace")]
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8") == NOTRE


# --------------------------------------------------------------------------- #
# 2. Le cas qui compte : le fichier de l'utilisateur
# --------------------------------------------------------------------------- #


def test_un_fichier_de_l_utilisateur_est_preserve_et_la_version_jio_ecrite_a_cote(
    tmp_path: Path,
) -> None:
    (tmp_path / "AGENTS.md").write_text(A_EUX, encoding="utf-8")

    decisions = ecrire_manifest(tmp_path, {"AGENTS.md": NOTRE})

    assert _actions(decisions) == [("AGENTS.md", "preserve")]
    # Le fichier de l'utilisateur est INTACT, octet pour octet.
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == A_EUX
    # Et la version jio est disponible, la ou le message l'annonce.
    assert (tmp_path / "AGENTS.md.jio").read_text(encoding="utf-8") == NOTRE
    assert "AGENTS.md.jio" in decisions[0].detail


def test_une_marque_en_plein_milieu_du_fichier_ne_suffit_pas(tmp_path: Path) -> None:
    """La marque se lit en TETE. Un document qui PARLE de jio n'est pas un fichier de jio."""
    (tmp_path / "NOTES.md").write_text(
        "# Notes\n\n" + "blabla\n" * 200 + "\nLe fichier est genere par `jio artifacts`.\n",
        encoding="utf-8",
    )
    decisions = ecrire_manifest(tmp_path, {"NOTES.md": NOTRE})
    assert _actions(decisions) == [("NOTES.md", "preserve")]


# --------------------------------------------------------------------------- #
# 3. La commande, de bout en bout
# --------------------------------------------------------------------------- #


def test_jio_sync_ecrit_tout_et_preserve_le_fichier_de_l_utilisateur(
    tmp_path: Path, capsys
) -> None:
    """`jio sync` : la promesse des documents, verifiee sur un projet reel."""
    (tmp_path / "AGENTS.md").write_text(A_EUX, encoding="utf-8")

    code = main(["sync", "--root", str(tmp_path)])
    sortie = capsys.readouterr().out

    # Un fichier PRESERVE n'est pas un succes : un appelant doit pouvoir s'en apercevoir.
    assert code == 1, sortie
    assert "PRESERVE" in sortie
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == A_EUX
    assert (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".opencode/agents/jio.md").exists()
    assert (tmp_path / ".hermes/skills").is_dir()


def test_jio_sync_dry_run_n_ecrit_rien(tmp_path: Path, capsys) -> None:
    code = main(["sync", "--root", str(tmp_path), "--dry-run"])
    assert code == 0
    assert "[simulation]" in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


def test_jio_sync_est_idempotent(tmp_path: Path) -> None:
    """Deuxieme passage : rien a faire, et aucun fichier de plus."""
    assert main(["sync", "--root", str(tmp_path)]) == 0
    avant = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    assert main(["sync", "--root", str(tmp_path)]) == 0
    apres = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    assert avant == apres


def test_la_fenetre_de_marque_est_bornnee_au_byte_pres(tmp_path: Path) -> None:
    """La marque ne compte que dans les 600 PREMIERS octets — ni 599, ni 601.

    Mesure a l'origine : `jio mutants` a montre que `FENETRE_MARQUE = 600` pouvait passer a
    601 sans qu'aucun test ne bouge. Le test qui existait visait une marque a 1 400 octets,
    donc largement hors des deux bornes : il ne disait rien sur la limite elle-meme. Or la
    limite est exactement ce qui separe « ce fichier est a nous » de « ce fichier est a
    l'utilisateur », et une fenetre qui s'elargit en silence finit par adopter un document
    qui ne fait que PARLER de jio.
    """
    from jio.artifacts.write_guard import FENETRE_MARQUE, MARQUE, _porte_la_marque

    assert FENETRE_MARQUE == 600
    # La longueur du motif REELLEMENT reconnu, mesuree par le motif lui-meme : ecrire la
    # borne a la main (« 16 ») la ferait mentir le jour ou le motif change.
    motif = "genere par `jio`"
    reconnu = MARQUE.search(motif).end()
    assert _porte_la_marque("x" * (FENETRE_MARQUE - reconnu) + motif), "juste DANS la fenetre"
    assert not _porte_la_marque(
        "x" * (FENETRE_MARQUE - reconnu + 1) + motif
    ), "juste AU-DELA de la fenetre"
    # Et le comportement complet suit : un fichier dont la marque tombe juste au-dela de la
    # fenetre n'est PAS a nous, donc il est preserve.
    dehors = "x" * (FENETRE_MARQUE - reconnu + 1) + motif + "\nautre chose\n"
    (tmp_path / "DOC.md").write_text(dehors, encoding="utf-8")
    assert _actions(ecrire_manifest(tmp_path, {"DOC.md": NOTRE})) == [("DOC.md", "preserve")]
