"""Un chiffre annonce dans la documentation doit etre VRAI, ou ne pas y etre.

Le README a annonce « 187 tests verts » alors que la suite en comptait 520. Personne ne
recalcule un compteur en lisant une page — et c'est exactement le genre d'affirmation qui
detruit la confiance dans tout le reste du document.

Ce controle a mordu **trois fois**. Les trois fois, la reparation s'est faite a la main :
ouvrir le README, retrouver la ligne, retaper le nombre. Un controle qui punit sans reparer
se fait desactiver — ou pire, contourner. Il vit donc desormais dans `jio/chiffres.py`, avec
sa reparation (`jio chiffres --appliquer`), et ce fichier verifie **les deux** :

  * que la documentation dit vrai (le controle, sur le vrai README) ;
  * que la reparation est sure (sur des documents fabriques, y compris ceux qui piegent).

Le point le plus important est le dernier test : la premiere version de la reparation
reecrivait aussi les mentions **deja justes**, et un garde a refuse l'ecriture (« 5
remplacements pour 1 ecart »). Une reparation qui touche du texte qu'elle n'a pas mesure
abime des phrases saines.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jio.chiffres import CHIFFRES, ecarts, mesurer, reparer

REPO = Path(__file__).resolve().parents[1]
README = REPO / "README.md"


@pytest.fixture(scope="module")
def mesures() -> dict[str, int]:
    """Les valeurs reelles, mesurees UNE fois pour tout le fichier (~2 s de collecte)."""
    return mesurer(REPO)


# --------------------------------------------------------------------------- #
# Le controle, sur la vraie documentation
# --------------------------------------------------------------------------- #


def test_la_documentation_dit_vrai(mesures: dict[str, int]) -> None:
    """Le chiffre publie est confronte a la suite reelle, pas a une memoire."""
    trouves = ecarts(README.read_text(encoding="utf-8"), mesures)
    assert not trouves, "\n".join(str(ecart) for ecart in trouves) + (
        "\n\nCorrection :  jio chiffres --appliquer   (ou retirer le chiffre : un chiffre "
        "faux coute plus cher qu'une absence de chiffre)"
    )


def test_les_mesures_sont_des_entiers_positifs(mesures: dict[str, int]) -> None:
    """Une mesure nulle signalerait que le controle ne mesure plus rien.

    Le cas s'est produit : `pytest --collect-only` peut afficher son total sous deux
    formes, et une lecture trop stricte rendait « 0 test ». Un controle qui vaut zero
    passerait pour vert sur un document qui ne dit rien.
    """
    for nom, valeur in mesures.items():
        assert valeur > 0, f"mesure absente ou nulle pour {nom}"


# --------------------------------------------------------------------------- #
# Le controle, sur des documents fabriques
# --------------------------------------------------------------------------- #


def test_un_chiffre_faux_est_localise_avec_sa_ligne() -> None:
    texte = "Titre\n\n**Statut :** 187 tests verts.\n\nLes 11 compétences et les 7 agents.\n"
    trouves = ecarts(texte, {"tests": 533, "competences": 11, "agents": 7})

    assert len(trouves) == 1
    ecart = trouves[0]
    assert ecart.ligne == 3
    assert ecart.ancien == "187 tests verts"
    assert ecart.nouveau == "533 tests verts"


def test_un_motif_non_ancre_serait_un_faux_positif() -> None:
    """« | 2 agents | » est la taille d'un panel, pas la bibliotheque d'agents.

    Le motif doit donc etre ANCRE (« les N agents »). Sans cela, ce controle signalerait
    une erreur qui n'existe pas — et un faux positif dans un controle de documentation,
    c'est un bug du controle, pas du document.
    """
    texte = "| Panel | 2 agents |\n| Bibliotheque | les 7 agents |\n1 test vert\n"
    trouves = ecarts(texte, {"tests": 1, "competences": 1, "agents": 7})
    sur_les_agents = [ecart for ecart in trouves if ecart.nom == "agents"]
    assert not sur_les_agents, (
        "la taille d'un panel a ete prise pour la bibliotheque d'agents : "
        f"{sur_les_agents}"
    )


def test_un_chiffre_qui_disparait_est_signale(mesures: dict[str, int]) -> None:
    """Un document qui n'annonce plus rien ne doit pas rendre le controle vert.

    Sinon il suffirait d'effacer la phrase pour faire disparaitre le probleme — et le
    controle deviendrait vert en ne verifiant plus rien.
    """
    trouves = ecarts("Un document sans aucun chiffre.\n", mesures)
    assert any(ecart.ligne == 0 for ecart in trouves)
    assert any("ne trouve plus rien a verifier" in str(ecart.contexte) for ecart in trouves)


# --------------------------------------------------------------------------- #
# La reparation
# --------------------------------------------------------------------------- #


def test_la_reparation_corrige_et_sauvegarde(tmp_path: Path) -> None:
    cible = tmp_path / "doc.md"
    # Le document DECLARE les trois grandeurs mesurees : sinon le controle signalerait, a
    # juste titre, que « les 3 agents » n'apparait nulle part — et ce test mesure la
    # reparation, pas le signalement (il a son propre test plus bas).
    original = "**Statut :** 187 tests verts, et les 3 compétences, et les 2 agents.\n"
    cible.write_text(original, encoding="utf-8")
    mesures = {"tests": 533, "competences": 11, "agents": 7}

    code, restants, message = reparer(cible, mesures, ecrire=True)

    assert code == 0, message
    assert not restants
    assert "533 tests verts" in cible.read_text(encoding="utf-8")
    assert "les 11 compétences" in cible.read_text(encoding="utf-8")
    assert "les 7 agents" in cible.read_text(encoding="utf-8")
    sauvegarde = tmp_path / "doc.md.avant-jio"
    assert sauvegarde.read_text(encoding="utf-8") == original


def test_la_reparation_ne_touche_pas_ce_qui_est_deja_vrai(tmp_path: Path) -> None:
    """Le cas qui a fait refuser une ecriture : corriger du vrai n'est pas neutre."""
    cible = tmp_path / "doc.md"
    # Une seule chose est fausse ici : le compteur de tests.
    cible.write_text("Les 11 compétences et les 7 agents.\n187 tests verts\n", encoding="utf-8")
    mesures = {"tests": 533, "competences": 11, "agents": 7}

    code, _, message = reparer(cible, mesures, ecrire=True)

    assert code == 0, message
    resultat = cible.read_text(encoding="utf-8")
    assert "Les 11 compétences et les 7 agents." in resultat, "du texte deja juste a bouge"
    assert "533 tests verts" in resultat


def test_la_simulation_n_ecrit_rien(tmp_path: Path) -> None:
    cible = tmp_path / "doc.md"
    original = "187 tests verts\n"
    cible.write_text(original, encoding="utf-8")

    code, trouves, message = reparer(cible, {"tests": 533, "competences": 11, "agents": 7})

    assert code == 1, "un ecart non corrige doit se signaler"
    assert trouves and "appliquer" in message
    assert cible.read_text(encoding="utf-8") == original
    assert not (tmp_path / "doc.md.avant-jio").exists()


def test_la_reparation_d_un_document_juste_ne_cree_rien(tmp_path: Path) -> None:
    """Rien a faire n'est pas un echec, et ne doit pas laisser de sauvegarde inutile."""
    cible = tmp_path / "doc.md"
    cible.write_text(
        "533 tests verts, les 11 compétences, les 7 agents.\n", encoding="utf-8"
    )

    code, trouves, message = reparer(cible, {"tests": 533, "competences": 11, "agents": 7},
                                     ecrire=True)

    assert code == 0, message
    assert not trouves
    assert "dit vrai" in message or "aucun ecart" in message
    assert not (tmp_path / "doc.md.avant-jio").exists()


def test_la_reparation_refuse_ce_qu_elle_ne_comprend_pas(tmp_path: Path) -> None:
    """Le garde qui a sauve la mise : le compte des remplacements doit coller aux ecarts.

    Verifie ici sur un document ou le meme motif apparait de nombreuses fois : si la
    reparation en corrigeait plus qu'elle n'en a annonce, elle ecrirait dans des phrases
    qu'elle n'a pas mesurees.
    """
    cible = tmp_path / "doc.md"
    cible.write_text(
        "Les 11 compétences et les 7 agents.\n" * 20 + "187 tests verts\n",
        encoding="utf-8",
    )
    mesures = {"tests": 533, "competences": 11, "agents": 7}

    code, _, message = reparer(cible, mesures, ecrire=True)
    assert code == 0, message
    # Les 20 lignes deja justes sont intactes, seule la derniere a change.
    assert cible.read_text(encoding="utf-8").count("Les 11 compétences et les 7 agents.") == 20


def test_les_motifs_portent_exactement_un_groupe() -> None:
    """La reparation remplace UNIQUEMENT le groupe capte : le reste de la phrase survit.

    Un motif a deux groupes ferait dependre la reecriture d'une convention non ecrite.
    """
    import re

    for chiffre in CHIFFRES:
        assert re.compile(chiffre.motif).groups == 1, f"motif ambigu : {chiffre.motif}"


# --------------------------------------------------------------------------- #
# Les zones declarees hors controle
# --------------------------------------------------------------------------- #


def test_une_zone_declaree_est_hors_controle(tmp_path: Path) -> None:
    """Un document doit pouvoir RACONTER une erreur passee.

    Sans issue de secours, ce controle interdisait de documenter ses propres defauts : la
    phrase « il annoncait 187 tests verts pour 520 » etait prise pour une affirmation du
    jour. L'exemption est declaree, et elle porte sa raison.
    """
    from jio.chiffres import zones_hors_controle

    texte = (
        "<!-- chiffres:hors-controle: recit d'un defaut passe -->\n"
        "187 tests verts autrefois\n"
        "<!-- /chiffres:hors-controle -->\n"
        "533 tests verts aujourd'hui\n"
    )
    mesures = {"tests": 533, "competences": 11, "agents": 7}
    lignes_masquees, raisons = zones_hors_controle(texte)

    assert lignes_masquees == {1, 2, 3}
    assert raisons and "recit d'un defaut passe" in raisons[0]

    # Le recit echappe au controle, l'affirmation du jour non.
    trouves = [e for e in ecarts(texte, mesures) if e.reparable]
    assert not trouves, [str(e) for e in trouves]


def test_la_reparation_n_ecrit_jamais_dans_une_zone(tmp_path: Path) -> None:
    """Si le controle ne regarde pas une ligne, la reparation ne doit pas y ecrire.

    Deux implementations separees auraient fini par diverger : l'ecriture se serait glissee
    la ou la verification ne regardait plus — un trou invisible dans le controle.
    """
    cible = tmp_path / "doc.md"
    cible.write_text(
        "<!-- chiffres:hors-controle: histoire -->\n"
        "187 tests verts (autrefois)\n"
        "<!-- /chiffres:hors-controle -->\n"
        "530 tests verts\n"
        "les 11 compétences, les 7 agents\n",
        encoding="utf-8",
    )
    mesures = {"tests": 533, "competences": 11, "agents": 7}

    code, _, message = reparer(cible, mesures, ecrire=True)

    assert code == 0, message
    resultat = cible.read_text(encoding="utf-8")
    assert "187 tests verts (autrefois)" in resultat, "le recit a ete reecrit"
    assert "533 tests verts\n" in resultat, "l'affirmation du jour n'a pas ete corrigee"
    assert "zone(s) hors controle" in message, "l'exemption n'est pas citee dans le rapport"


def test_mesurer_couvre_TOUS_les_chiffres_surveilles() -> None:
    """Le saut de `ecarts` doit rester MESURE, sinon il devient le silence qu'on combat.

    `ecarts` et `reparer` sautent un chiffre qui n'est pas dans le dictionnaire de mesures :
    les tests de reparation travaillent sur un document de trois lignes et n'ont pas a
    mesurer le banc d'objectifs. Mais ce saut ouvre une porte : un chiffre SURVEILLE que
    `mesurer()` n'alimente pas serait saute dans le depot REEL, et le controle de
    documentation deviendrait vert sans rien verifier — précisement le defaut que ce module
    existe pour supprimer (« un controle qui ne trouve plus rien a verifier devient vert
    sans rien prouver »).

    Ce test ferme cette porte : il compare l'ENSEMBLE des noms surveilles a l'ensemble
    reellement mesure sur le depot. Ajouter un chiffre a `CHIFFRES` sans l'ajouter a
    `mesurer()` casse ici, pas six mois plus tard dans un README faux.
    """
    surveilles = {c.nom for c in CHIFFRES}
    mesures = set(mesurer(Path(__file__).resolve().parents[1]))

    assert surveilles <= mesures, (
        "ces chiffres sont surveilles dans les documents mais AUCUNE mesure ne les alimente : "
        f"{sorted(surveilles - mesures)} — `jio chiffres` sauterait leur controle en silence."
    )
    # Et dans l'autre sens : une mesure que personne ne surveille est du travail mort.
    assert mesures <= surveilles, (
        f"mesures sans chiffre surveille : {sorted(mesures - surveilles)}"
    )


def test_un_chiffre_qui_n_apparait_PLUS_NULLE_PART_nest_pas_un_succes(tmp_path: Path) -> None:
    """Un controle qui ne trouve plus rien a verifier devient vert sans rien prouver.

    Mesure a l'origine : un chiffre surveille qui disparaissait entierement du document
    faisait sortir `jio chiffres` en **0** — « tout va bien » — alors que `jio coherence`
    traite exactement le meme constat comme une incoherence et sort en **1**. Deux commandes
    qui mesurent la meme chose ne peuvent pas rendre deux verdicts opposes : celle qu'on met
    dans un pre-commit serait justement celle qui se tait.
    """
    mesures = {"tests": 533, "competences": 11, "agents": 7}

    # 1. Un chiffre mesure dont le document ne parle PLUS : ce n'est pas « rien a faire ».
    cible = tmp_path / "doc.md"
    cible.write_text("les 11 compétences, les 7 agents\n", encoding="utf-8")
    code, trouves, message = reparer(cible, mesures)
    assert code == 1, message
    assert [e.nom for e in trouves] == ["tests"]
    assert "n'apparait" in message or "n'apparaisse" in message
    # Rien n'a ete ecrit : il n'y avait rien de mecanique a corriger.
    assert not (tmp_path / "doc.md.avant-jio").exists()

    # 2. Une valeur PERIMEE et une mention MANQUANTE dans le meme document : la partie
    #    mecanique doit avoir lieu, et le code doit quand meme dire que le document reste
    #    incomplet — les deux informations sont distinctes, et les confondre ferait perdre
    #    l'une ou l'autre.
    cible.write_text("187 tests verts\nles 11 compétences\n", encoding="utf-8")
    code, restants, message = reparer(cible, mesures, ecrire=True)
    assert "533 tests verts" in cible.read_text(encoding="utf-8"), "la valeur perimee n'a pas ete ecrite"
    assert [e.nom for e in restants] == ["agents"], [str(e) for e in restants]
    assert code == 1, message
    assert "a bien ete ECRIT" in message, message


def test_chiffres_et_coherence_rendent_le_MEME_verdict_sur_le_meme_document(
    tmp_path: Path,
) -> None:
    """L'invariant qui manquait, verifie sur les deux commandes a la fois.

    `jio chiffres` et le controle `nombres` de `jio coherence` mesurent la MEME chose. Tant
    qu'ils peuvent diverger, l'un des deux ment — et c'est celui qu'on met dans un pre-commit
    qui decide lequel. On verifie donc l'equivalence, dans les trois etats d'un document :
    juste, perime, et ampute d'une mention.

    Le depot de test est CONSTRUIT pour etre mesurable : un fichier de test reel (sinon
    `mesurer` refuse de rendre un chiffre qu'il n'a pas su lire) et un README qui annonce
    exactement les valeurs mesurees. Un banc qui n'est pas mesurable ne mesure rien.
    """
    from jio.verify.coherence import controler

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_rien.py").write_text("def test_ok():\n    assert True\n",
                                                     encoding="utf-8")
    mesures = mesurer(tmp_path)
    juste = (f"{mesures['tests']} tests verts, les {mesures['competences']} compétences, "
             f"les {mesures['agents']} agents, {mesures['objectifs']} objectifs\n")

    perime = juste.replace(f"{mesures['tests']} tests", f"{mesures['tests'] + 7} tests", 1)
    ampute = juste.replace(f"{mesures['tests']} tests verts, ", "", 1)   # mention disparue
    assert perime != juste and ampute != juste, "les deux cas doivent DIFFERER du document juste"

    cible = tmp_path / "README.md"
    for contenu, coherent in ((juste, True), (perime, False), (ampute, False)):
        cible.write_text(contenu, encoding="utf-8")
        code = reparer(cible, mesures)[0]
        constat = next(c for c in controler(tmp_path).constats if c.controle == "nombres")
        assert constat.portee, "le controle doit etre DANS sa portee, sinon il ne juge rien"
        assert (code == 0) == bool(constat.ok) == coherent, (
            f"desaccord sur {contenu!r} : `jio chiffres` code={code}, "
            f"coherence nombres ok={constat.ok} ({constat.resume[:80]})"
        )
