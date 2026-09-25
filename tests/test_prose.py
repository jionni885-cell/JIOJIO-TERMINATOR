"""Missions de DOCUMENT : la boucle entiere, avec des temoins de prose.

Trois choses sont verrouillees ici, dans l'ordre d'importance :

  1. AUCUN FAUX DOCUMENT N'EST LIVRE COMME PROUVE. C'est le seul chiffre qui doit
     rester a zero, et c'est ce que la mission de prose apporte : une affirmation
     refutee ne devient jamais une livraison ;
  2. le document CORRECT est reconnu par le moteur sans oracle — le verificateur
     retrouve la selection qu'un oracle ferait, et c'est mesurable ;
  3. la GRAINE de la mission entre dans chaque generation. Sans cela, toutes les
     repetitions du banc rejouaient le meme tirage : c'etait vrai, et invisible.
"""

from __future__ import annotations

import pathlib

import pytest

from jio.bench.prose import PROSE_TASKS, PROSE_BY_ID, prose_bank
from jio.verify.prose_prover import R_VERIFIABLE, ProseProver, spec_prose

REPO = pathlib.Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# 1. Le verificateur de prose se comporte comme un prouveur
# --------------------------------------------------------------------------- #


def test_le_document_correct_est_prouve() -> None:
    tache = PROSE_BY_ID["rapport_latence"]
    resultat = ProseProver(racine=REPO).prove(tache.correct, spec_prose(tache.objective))

    assert resultat.passed
    assert resultat.ratio == 1.0
    assert not resultat.hard_failures
    assert R_VERIFIABLE in {w.rule_id for w in resultat.witnesses}


def test_un_calcul_faux_est_refute_avec_la_valeur_reelle() -> None:
    tache = PROSE_BY_ID["rapport_latence"]
    fautif = tache.distractors[0]
    resultat = ProseProver(racine=REPO).prove(fautif, spec_prose(tache.objective))

    assert not resultat.passed
    refus = " | ".join(w.stderr for w in resultat.hard_failures)
    assert "43" in refus and "42" in refus, refus


def test_un_bloc_annonce_python_et_casse_est_refute() -> None:
    tache = PROSE_BY_ID["rapport_latence"]
    resultat = ProseProver(racine=REPO).prove(tache.distractors[1],
                                              spec_prose(tache.objective))
    assert not resultat.passed
    assert any("NE COMPILE PAS" in w.stderr for w in resultat.hard_failures)


def test_un_chemin_introuvable_est_une_reserve_pas_un_rejet() -> None:
    """La retenue est une DECISION : un document decrit parfois un fichier a creer."""
    tache = PROSE_BY_ID["rapport_latence"]
    resultat = ProseProver(racine=REPO).prove(tache.distractors[2],
                                              spec_prose(tache.objective))
    assert resultat.passed, "un chemin manquant ne doit pas condamner le document"
    assert resultat.reservations, "il doit etre SIGNALE"
    assert not resultat.hard_failures


def test_un_document_sans_affirmation_verifiable_ne_passe_pas() -> None:
    """Rien a verifier n'est pas un quitus — la regle P-000 le dit a voix haute."""
    resultat = ProseProver(racine=None).prove(
        "# Note\n\nUne intention, sans aucun fait verifiable.\n", spec_prose("note"))
    assert not resultat.passed
    assert [w.rule_id for w in resultat.hard_failures] == [R_VERIFIABLE]
    assert "PAS un quitus" in resultat.hard_failures[0].stderr


def test_la_specification_de_prose_declare_hors_domaine() -> None:
    """La frontiere doit etre ECRITE, pas devinee."""
    spec = spec_prose("rapport")
    assert [r.id for r in spec.rules] == [R_VERIFIABLE]
    assert spec.under_specified, "ce qui n'est pas prouvable doit etre declare"
    assert any("style" in u for u in spec.under_specified)


# --------------------------------------------------------------------------- #
# 2. La boucle complete, sur un document
# --------------------------------------------------------------------------- #


def _moteur(skill: float, seed: int, max_rounds: int = 3):
    from jio.cli import _simulated_engine

    tache = PROSE_TASKS[0]
    return _simulated_engine(
        None, skill=skill, seed=seed, max_rounds=max_rounds,
        famille="prose", banque=prose_bank(tache), racine=REPO,
    ), tache


def test_la_boucle_livre_le_document_correct() -> None:
    from jio.core.types import Mission
    from jio.loop.engine import WorkItem

    moteur, tache = _moteur(skill=0.5, seed=3)
    rapport = moteur.run(
        Mission(objective=tache.objective, id="prose-3", max_rounds=3),
        WorkItem(objective=tache.objective, spec=spec_prose(tache.objective)),
    )
    assert rapport.subject.strip() == tache.correct.strip()
    assert rapport.status.value in {"delivered", "delivered_with_reservation"}


def test_un_modele_incapable_ne_livre_jamais_un_faux_prouve() -> None:
    """Competence 0.0 : tous les tirages sont des distracteurs.

    La garantie n'est pas « il ne livre rien » : c'est **il ne livre jamais rien
    SANS LE DIRE**. Un document non correct livre `DELIVERED_WITH_RESERVATION` n'est
    pas un silence : le signalement est nomme et consultable. Un document non correct
    livre `DELIVERED` serait exactement le silence que ce projet refuse.

    C'est la definition du banc de code (« ERREURS LIVREES SANS RESERVE »), et elle
    est plus severe qu'une comparaison de contenu — donc c'est celle-la qu'on teste.
    """
    from jio.core.types import Mission, MissionStatus
    from jio.loop.engine import WorkItem

    moteur, tache = _moteur(skill=0.0, seed=0, max_rounds=2)
    rapport = moteur.run(
        Mission(objective=tache.objective, id="prose-0", max_rounds=2),
        WorkItem(objective=tache.objective, spec=spec_prose(tache.objective)),
    )
    if rapport.status is MissionStatus.DELIVERED:
        assert rapport.subject.strip() == tache.correct.strip(), (
            "un document NON correct a ete livre sans aucun signalement"
        )
    assert rapport.status in {
        MissionStatus.DELIVERED, MissionStatus.DELIVERED_WITH_RESERVATION,
        MissionStatus.ABSTAINED, MissionStatus.FAILED,
    }


def test_un_distracteur_a_calcul_faux_ne_passe_jamais_le_statut_delivered() -> None:
    """Le coeur de la garantie, isole du reste : une affirmation refutee bloque."""
    from jio.verify.prose_prover import ProseProver

    tache = PROSE_TASKS[0]
    faux = tache.distractors[0]
    resultat = ProseProver(racine=REPO).prove(faux, spec_prose(tache.objective))
    assert not resultat.passed, "ratio < 1 : le moteur ne peut pas conclure `delivered`"


def test_les_etages_de_code_sont_desactives_en_prose() -> None:
    """Sinon la mission s'abstiendrait pour de mauvaises raisons."""
    moteur, _ = _moteur(skill=1.0, seed=0)
    assert moteur.config.famille == "prose"
    assert moteur.config.self_check is False
    assert moteur.config.mutation_gate is False
    assert moteur.config.temoins is False


# --------------------------------------------------------------------------- #
# 3. La graine de mission : le bug de mesure corrige
# --------------------------------------------------------------------------- #


def _empreintes(skill: float, seed: int) -> list[str]:
    from jio.core.types import Mission
    from jio.loop.engine import WorkItem

    moteur, tache = _moteur(skill=skill, seed=seed, max_rounds=1)
    moteur.run(
        Mission(objective=tache.objective, id=f"g{seed}", max_rounds=1),
        WorkItem(objective=tache.objective, spec=spec_prose(tache.objective)),
    )
    return [e.payload["digest"] for e in moteur.journal.events("candidate")]


def test_deux_graines_produisent_des_candidats_differents() -> None:
    """Sans cela, les `runs` du banc repetent UN SEUL tirage.

    C'etait le cas : la generation utilisait `1000 * tour + i`, sans la graine de la
    mission. Trois graines donnaient exactement les memes empreintes, et l'ecart
    mesure entre le harness et le modele brut n'etait pas une moyenne. Une mesure
    dont la variance est nulle par construction ne peut pas etre presentee comme un
    resultat.
    """
    a, b = _empreintes(0.35, 0), _empreintes(0.35, 1)
    assert a and b
    assert a != b, "deux graines de mission doivent produire des tirages differents"


def test_la_meme_graine_reproduit_exactement_la_meme_mission() -> None:
    """Corriger le tirage ne doit pas casser la reproductibilite."""
    assert _empreintes(0.35, 7) == _empreintes(0.35, 7)


def test_le_banc_de_prose_ne_livre_aucun_faux() -> None:
    """Le chiffre qui doit rester a zero, verifie par le banc lui-meme."""
    from jio.bench.prose import mesurer_prose

    mesure = mesurer_prose(skill=0.35, runs=3, max_rounds=2, racine=REPO)
    assert mesure.erreurs_silencieuses == 0, "un document faux a ete livre sans rien dire"
    assert mesure.jio == 1.0, "le verificateur doit retrouver la selection de l'oracle"


@pytest.mark.parametrize("skill", [0.0, 0.35])
def test_le_banc_de_prose_ne_silence_rien(skill: float) -> None:
    """A competence NULLE comme a competence moyenne : aucune erreur silencieuse."""
    from jio.bench.prose import mesurer_prose

    mesure = mesurer_prose(skill=skill, runs=2, max_rounds=2, racine=REPO)
    assert mesure.erreurs_silencieuses == 0
    assert mesure.essais == 2 * len(PROSE_TASKS)
    # Chaque essai finit dans UNE et une seule categorie : rien ne disparait.
    assert (mesure.jio * mesure.essais) + mesure.erreurs_silencieuses \
        + mesure.sous_reserve + mesure.abstentions == mesure.essais
