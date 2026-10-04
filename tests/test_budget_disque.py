"""Le budget de contexte doit mesurer ce que l'outil CHARGE, pas ce que jio écrirait.

DÉFAUT MESURÉ, corrigé ici : `jio artifacts --budget` mesurait le **manifeste** — le texte que
jio regénérerait — et jamais le fichier posé sur le disque. Un `AGENTS.md` édité à la main (donc
PRÉSERVÉ par le garde-fou d'écriture, et chargé par l'outil) était mesuré à la place d'un autre :
le rapport annonçait « 150 lignes », et le verdict « aucun fichier ne dépasse », d'un fichier qui
en faisait 300.

C'est le seul chiffre qui décide si le harness aide ou nuit : un fichier de contexte au-delà
d'environ 150 lignes est **survolé, pas lu**. Un chiffre qui porte sur un autre fichier que le
sien est un chiffre faux, même s'il est exact.

Deuxième règle du même mouvement, aussi importante que la première : **ce qui a été mesuré est
DIT**. Un fichier qui diverge de la doctrine, un fichier qui n'existe pas encore — les deux
changent ce que le chiffre signifie, donc les deux s'affichent.
"""

from __future__ import annotations

from pathlib import Path

from jio.artifacts.budget import sur_disque


def test_le_fichier_du_disque_GAGNE_sur_le_texte_genere(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("ligne 1\nligne 2\n", encoding="utf-8")
    etat = sur_disque(tmp_path, {"AGENTS.md": "genere\n"})
    assert etat.fichiers["AGENTS.md"] == "ligne 1\nligne 2\n"
    assert etat.divergents == ("AGENTS.md",)
    assert etat.absents == ()


def test_un_fichier_identique_n_est_pas_signale(tmp_path: Path) -> None:
    """Signaler une divergence inexistante ferait douter de toutes les autres."""
    (tmp_path / "AGENTS.md").write_text("identique\n", encoding="utf-8")
    etat = sur_disque(tmp_path, {"AGENTS.md": "identique\n"})
    assert etat.divergents == ()
    assert etat.absents == ()


def test_un_fichier_absent_est_DECLARE_absent(tmp_path: Path) -> None:
    """Mesurer ce que jio écrira est légitime — à condition de le dire : c'est un futur, pas un
    présent."""
    etat = sur_disque(tmp_path, {"CLAUDE.md": "a ecrire\n"})
    assert etat.fichiers["CLAUDE.md"] == "a ecrire\n"
    assert etat.absents == ("CLAUDE.md",)
    assert etat.divergents == ()


def test_un_chemin_illisible_ne_fait_pas_planter_la_mesure(tmp_path: Path) -> None:
    """Un dossier à la place du fichier, un lien cassé : le rapport ne doit pas mourir sur une
    entrée hostile ou abîmée — il doit se rabattre et continuer."""
    (tmp_path / "AGENTS.md").mkdir()
    etat = sur_disque(tmp_path, {"AGENTS.md": "genere\n"})
    assert etat.fichiers["AGENTS.md"] == "genere\n"
    assert etat.absents == ("AGENTS.md",)


def test_le_budget_SIGNALE_et_CHIFFRE_un_fichier_edite_a_la_main(tmp_path, monkeypatch, capsys):
    """Le contrôle de bout en bout : un fichier de contexte de 200 lignes sur le disque.

    Il doit être (1) mesuré à sa vraie taille, (2) déclaré au-dessus du budget, (3) déclaré
    comme VOTRE fichier, avec les deux nombres — le sien et celui de la doctrine — parce que
    `jio artifacts --write` peut le PRÉSERVER : recommander une régénération qui ne peut pas
    réparer serait une boucle.
    """
    from jio.cli import main

    mon_fichier = "\n".join(f"ligne {i}" for i in range(200)) + "\n"
    (tmp_path / "AGENTS.md").write_text(mon_fichier, encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    code = main(["artifacts", "--budget"])
    sortie = capsys.readouterr().out

    assert code == 0
    assert "200 ligne(s)" in sortie, "la taille mesuree doit etre celle du fichier, pas celle du manifeste"
    assert "DEPASSENT" in sortie
    assert "MESURE SUR VOS FICHIERS" in sortie
    assert "AGENTS.md : 200 ligne(s) ici" in sortie
    assert "dans la doctrine" in sortie
