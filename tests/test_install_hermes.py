"""Installer les compétences là où Hermes les lit — sans jamais écraser les tiennes.

POURQUOI CE FICHIER. `jio artifacts --write` posait les compétences dans le projet, sous
`.hermes/skills/`. **Hermes lit `~/.hermes/skills/`.** Entre les deux il y avait un `cp -r` à
taper à la main, écrit dans le README : autrement dit, une étape que personne ne fait, et douze
procédures qui dorment sur le disque sans jamais entrer dans la boucle de l'agent. L'intégration
en une commande s'arrêtait juste avant l'endroit qui compte.

L'INSTALLATION DOIT ÊTRE SÛRE, et c'est là que se joue la difficulté : elle écrit dans le dossier
PERSONNEL de quelqu'un. Trois règles, chacune payée par un essai :

  1. **Copie enregistrée par empreinte, pas lien symbolique.** Essai fait : `echo x >
     ~/.hermes/skills/.../SKILL.md` sur un lien écrit DANS le fichier du projet, puis
     `jio artifacts --write` l'écrase. L'utilisateur croit modifier sa copie, il détruit une
     source générée — en silence, dans son dossier personnel ;
  2. **une ancienne version de jio se met à jour** (empreinte enregistrée == contenu) ;
     **un fichier écrit par l'utilisateur se préserve** (empreinte différente), toujours ;
  3. **rien n'est créé dans le dossier personnel** si Hermes n'y est pas déjà : une installation
     surprise n'est pas une intégration.
"""

from __future__ import annotations

import json
from pathlib import Path

from jio.artifacts.install_hermes import REGISTRE, desinstaller, dossier_hermes, installer


def _projet(tmp_path: Path) -> Path:
    """Un projet minimal avec deux compétences générées, comme `jio artifacts --write` en pose."""
    racine = tmp_path / "projet"
    for categorie, nom in (("anti-error", "failure-memory"), ("harness", "context-budget")):
        dossier = racine / ".hermes" / "skills" / categorie / nom
        dossier.mkdir(parents=True)
        (dossier / "SKILL.md").write_text(
            f"---\nname: {nom}\n---\n\n# {nom}\nProcedure v1.\n", encoding="utf-8"
        )
    return racine


def test_HERMES_SKILLS_choisit_le_dossier_que_hermes_lit(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("HERMES_SKILLS", str(tmp_path / "exact"))
    assert dossier_hermes() == tmp_path / "exact"
    monkeypatch.delenv("HERMES_SKILLS")
    monkeypatch.setenv("HERMES_HOME", str(tmp_path / "maison"))
    assert dossier_hermes() == tmp_path / "maison" / "skills"


def test_sans_dossier_hermes_RIEN_n_est_ecrit_et_c_est_DIT(tmp_path, monkeypatch) -> None:
    """Une installation surprise dans le dossier personnel n'est pas une intégration."""
    racine = _projet(tmp_path)
    cible = tmp_path / "pas-la" / "skills"

    rapport = installer(racine, dossier=cible)

    assert rapport.ignores is True
    assert not cible.exists()
    assert "n'existe pas" in rapport.resume()


def test_les_competences_arrivent_DANS_le_dossier_de_hermes(tmp_path) -> None:
    racine = _projet(tmp_path)
    cible = tmp_path / "hermes" / "skills"
    cible.mkdir(parents=True)

    rapport = installer(racine, dossier=cible)

    assert rapport.installes == 2
    assert (cible / "anti-error" / "failure-memory" / "SKILL.md").is_file()
    assert "Procedure v1" in (cible / "harness" / "context-budget" / "SKILL.md").read_text("utf-8")
    # Une COPIE, pas un lien : editer la copie ne doit pas toucher la source du projet.
    assert not (cible / "anti-error" / "failure-memory" / "SKILL.md").is_symlink()
    registre = json.loads((racine / REGISTRE).read_text("utf-8"))
    assert len(registre) == 2


def test_editer_SA_copie_ne_touche_PAS_la_source_du_projet(tmp_path) -> None:
    """L'essai qui a fait abandonner le lien symbolique comme defaut.

    Avec un lien, `echo x > ~/.hermes/.../SKILL.md` ecrivait dans le fichier du PROJET, et le
    prochain `jio artifacts --write` effacait l'edition. Une copie isole les deux mondes.
    """
    racine = _projet(tmp_path)
    cible = tmp_path / "hermes" / "skills"
    cible.mkdir(parents=True)
    installer(racine, dossier=cible)

    copie = cible / "anti-error" / "failure-memory" / "SKILL.md"
    source = racine / ".hermes" / "skills" / "anti-error" / "failure-memory" / "SKILL.md"
    copie.write_text("MES PROPRES REGLES\n", encoding="utf-8")

    assert source.read_text("utf-8").startswith("---"), "la source du projet doit etre intacte"

    # Et le reinstaller ne l'ecrase pas : c'est le fichier de l'utilisateur.
    rapport = installer(racine, dossier=cible)
    assert str(copie) in rapport.preserves
    assert copie.read_text("utf-8") == "MES PROPRES REGLES\n"


def test_une_ancienne_version_de_jio_est_MISE_A_JOUR(tmp_path) -> None:
    """L'autre cas, et il ne doit pas etre confondu avec le precedent : la copie a change, mais
    l'empreinte enregistree correspond au contenu => c'est NOUS qui l'avons ecrite, dans une
    version precedente. La laisser perimee, c'est servir une procedure corrigee a l'ancienne."""
    racine = _projet(tmp_path)
    cible = tmp_path / "hermes" / "skills"
    cible.mkdir(parents=True)
    installer(racine, dossier=cible)

    # L'utilisateur met a jour le PROJET (nouvelle version de la doctrine, puis regeneration).
    (racine / ".hermes" / "skills" / "anti-error" / "failure-memory" / "SKILL.md").write_text(
        "---\nname: failure-memory\n---\n\n# failure-memory\nProcedure v2.\n", encoding="utf-8"
    )

    rapport = installer(racine, dossier=cible)

    assert len(rapport.mises_a_jour) == 1
    copie = cible / "anti-error" / "failure-memory" / "SKILL.md"
    assert "Procedure v2" in copie.read_text("utf-8")
    assert not rapport.preserves


def test_relancer_ne_reecrit_rien(tmp_path) -> None:
    """L'idempotence, mesuree sur la DECISION et pas sur un compteur qui bouge."""
    racine = _projet(tmp_path)
    cible = tmp_path / "hermes" / "skills"
    cible.mkdir(parents=True)
    installer(racine, dossier=cible)

    rapport = installer(racine, dossier=cible)

    assert rapport.installes == 0
    assert len(rapport.deja) == 2
    assert rapport.resume().startswith("2 deja en place")


def test_le_mode_LIEN_reste_disponible_et_est_declare(tmp_path) -> None:
    """Qui veut la synchronisation permanente le demande explicitement — et le lien pointe bien
    sur la source, donc une regeneration du projet met la copie a jour."""
    racine = _projet(tmp_path)
    cible = tmp_path / "hermes" / "skills"
    cible.mkdir(parents=True)

    rapport = installer(racine, dossier=cible, lier=True)

    lien = cible / "harness" / "context-budget" / "SKILL.md"
    assert lien.is_symlink()
    assert lien.resolve() == (
        racine / ".hermes" / "skills" / "harness" / "context-budget" / "SKILL.md"
    ).resolve()
    assert len(rapport.liens) == 2


def test_la_desinstallation_retire_CE_QUE_JIO_A_POSE_et_rien_d_autre(tmp_path) -> None:
    """Sans cette fonction, la seule facon de defaire serait de supprimer le dossier a la main —
    et un utilisateur qui a SES competences dans `~/.hermes/skills` perdrait tout."""
    racine = _projet(tmp_path)
    cible = tmp_path / "hermes" / "skills"
    cible.mkdir(parents=True)
    installer(racine, dossier=cible)

    mienne = cible / "perso" / "ma-competence" / "SKILL.md"
    mienne.parent.mkdir(parents=True)
    mienne.write_text("mes regles\n", encoding="utf-8")
    # Et une copie que l'utilisateur a editee : elle doit survivre elle aussi.
    editee = cible / "anti-error" / "failure-memory" / "SKILL.md"
    editee.write_text("mes regles de memoire\n", encoding="utf-8")

    rapport = desinstaller(racine, dossier=cible)

    assert mienne.is_file(), "une competence de l'utilisateur ne doit jamais etre retiree"
    assert editee.is_file(), "un fichier edite par l'utilisateur non plus"
    assert str(editee) in rapport.preserves
    assert not (cible / "harness" / "context-budget" / "SKILL.md").exists()
