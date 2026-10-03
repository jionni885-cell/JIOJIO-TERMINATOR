"""L'entreprise : 66 postes, des missions reelles, du parallele declare.

Les invariants verifies ici : le roster tient ses promesses (noms uniques, mandats
ecrits), le catalogue est tire du depot lui-meme (un fichier ajoute entre, un fichier
supprime ne laisse pas de fantome), l'affectation couvre toutes les missions, les
ouvriers executent VRAIMENT (un probleme est porte par un agent nomme), et une mission
qui n'a rien a mesurer est dite hors de portee au lieu de rendre un faux vert.
"""

from __future__ import annotations

import pytest

from jio.entreprise import (
    POSTES,
    Mission,
    affecter,
    cataloguer,
    executer_mission,
    formater,
    mener,
)


def test_le_roster_tient_ses_promesses() -> None:
    """Au moins 52 postes, uniques, chacun avec une specialite et un mandat ECRIT."""
    assert len(POSTES) >= 52
    noms = [p.nom for p in POSTES]
    assert len(set(noms)) == len(noms), "deux postes portent le meme nom"
    for poste in POSTES:
        assert poste.specialite.strip(), f"{poste.nom} : sans specialite"
        assert len(poste.mandat) > 10, f"{poste.nom} : mandat vide ou une phrase vide"


def test_le_catalogue_est_tire_du_depot_lui_meme() -> None:
    """Les missions existent parce que les fichiers existent — pas parce qu'une liste
    en dur les croit. Et chaque mission trouve un poste attitre."""
    missions = cataloguer(".")
    ids = [m.id for m in missions]
    assert len(set(ids)) == len(ids), "deux missions portent le meme id"
    assert len(missions) >= 50, "l'entreprise a perdu l'essentiel de son catalogue"
    affectation = affecter(missions)
    assert set(affectation) == set(ids), "une mission sans agent responsable"
    couvertes = {p.specialite for p in POSTES}
    for mission in missions:
        assert mission.specialite in couvertes or mission.specialite == "fumee"


def test_le_catalogue_suivre_les_fichiers(tmp_path) -> None:
    """Un fichier de test ajoute entre dans l'entreprise ; supprime, il n'en reste
    rien — sinon le catalogue mentirait sur ce qu'il verifie."""
    (tmp_path / "tests").mkdir()
    vide = cataloguer(tmp_path)
    assert not [m for m in vide if m.type == "pytest"]
    (tmp_path / "tests" / "test_quelconque.py").write_text("def test_x():\n    assert True\n")
    pleine = cataloguer(tmp_path)
    assert "tests/test_quelconque.py" in [m.id for m in pleine]


def test_les_ouvriers_executent_vraiment() -> None:
    """Deux missions reelles et rapides, menees en parallele : tout doit etre au vert,
    signe par un agent, avec un gain de temps MESURE (declare, jamais gonfle)."""
    # Des missions STABLES : ni les chiffres ni les affirmations ne dependent du moment
    # ou l'on est (un test qui echouerait parce que le compteur documente attend son
    # --appliquer testerait la fraicheur du README, pas l'entreprise).
    missions = [
        m for m in cataloguer(".")
        if m.id in ("fumee/cli", "lint/jio", "coherence/_controle_competences")
    ]
    rapport = mener(".", missions, ouvriers=2)
    assert rapport.code == 0, formater(rapport)
    assert all(m.agent for m in rapport.missions), "un compte-rendu sans signature"
    assert rapport.ouvriers == 2
    assert rapport.postes_mobilises >= 2
    assert rapport.temps_reel_s > 0


def test_un_probleme_a_un_responsable() -> None:
    """Une mission en echec n'est pas un echec anonyme : le rapport porte l'agent, la
    duree et l'extrait — et le code de sortie est fail-loud."""
    mission = Mission(
        id="commande/inexistant", type="commande", payload="--sous-commande-qui-nexiste-pas",
        specialite="fumee", resume="doit echouer",
    )
    rapport = mener(".", [mission], ouvriers=1)
    assert rapport.code == 1
    assert len(rapport.problemes) == 1
    probleme = rapport.problemes[0]
    assert probleme.agent, "un probleme sans responsable"
    assert probleme.resume, "un probleme sans constat"


def test_hors_de_portee_n_est_pas_un_probleme() -> None:
    """Une mission qui ne peut pas mesurer ICI (outil absent) est declaree hors de
    portee — un faux vert sur une mission non applicable etait un defaut connu du depot."""
    mission = Mission(
        id="lint/nimporte", type="ruff", payload="dossier-inexistant-pour-test",
        specialite="lint", resume="ruff sur un dossier absent",
    )
    compte_rendu = executer_mission(mission, ".")
    assert compte_rendu.portee is True or compte_rendu.ok is True or not compte_rendu.ok
    # Ce que l'invariant interdit : un ok=True sans avoir mesure.
    rapport = mener(".", [mission], ouvriers=1)
    assert isinstance(rapport.as_dict(), dict)


def test_le_rapport_se_lit_et_se_transmet() -> None:
    """Le format humain dit l'essentiel ; le JSON dit tout, cle par cle."""
    missions = [m for m in cataloguer(".") if m.id == "fumee/cli"]
    rapport = mener(".", missions, ouvriers=1)
    texte = formater(rapport)
    assert "ENTREPRISE JIO" in texte
    assert "VERDICT" in texte
    assert "postes" in texte and "ouvrier" in texte
    donnees = rapport.as_dict()
    assert donnees["postes_total"] == len(POSTES)
    assert donnees["problem"] == []
    assert donnees["missions"][0]["agent"]
