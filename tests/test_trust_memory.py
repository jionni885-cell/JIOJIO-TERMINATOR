"""Tests du routeur de confiance et de la memoire des echecs.

Deux composants d'auto-amelioration, donc deux risques :
  * le routeur peut apprendre un optimum local et ne plus explorer ;
  * la memoire peut oublier (bug reel : `Journal(path=...)` n'ouvre le fichier
    qu'en ecriture, donc un nouveau processus repartait vide), ou retenir un
    souvenir sans garde — c'est-a-dire une histoire au lieu d'une protection.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jio.learn import FailureMemory, fingerprint
from jio.trust import DEFAULT_ARMS, TrustRouter, task_class

# --------------------------------------------------------------------------- #
# Memoire des echecs
# --------------------------------------------------------------------------- #


def _record(memory: FailureMemory, objective: str, symptom: str = "symptome") -> None:
    memory.record(
        objective=objective,
        symptom=symptom,
        root_cause="cause reelle",
        wrong_fix="piste tentee",
        correct_fix="correctif retenu",
        guard="test_de_ Garde",
    )


def test_un_echec_sans_garde_est_refuse():
    """Sans garde, un souvenir est un journal intime, pas une protection."""
    memory = FailureMemory()
    with pytest.raises(ValueError):
        memory.record(
            objective="x", symptom="y", root_cause="z", correct_fix="c", guard="   "
        )


def test_memoire_persiste_entre_deux_processus(tmp_path: Path):
    """Regression : la memoire ecrivait sur disque mais repartait vide."""
    path = tmp_path / "failures.jsonl"
    first = FailureMemory(path=path)
    _record(first, "median of a list", "even length returned upper middle")
    assert first.size == 1

    second = FailureMemory(path=path)  # nouveau processus / nouvelle instance
    assert second.size == 1, "la memoire n'a pas relu son propre journal"
    assert second.verify()[0], "la chaine d'integrite doit rester valide"


def test_recall_trouve_le_souvenir_pertinent(tmp_path: Path):
    memory = FailureMemory(path=tmp_path / "m.jsonl")
    _record(memory, "sum even numbers", "odd numbers were summed")
    _record(memory, "parse ISO duration", "hours were dropped")
    found = memory.recall("sum the even numbers of a list")
    assert found
    # Le souvenir pertinent est celui de l'objectif proche, pas celui du parsing.
    assert "even" in found[0].objective
    assert all("duration" not in rec.objective for rec in found)


def test_recall_ne_trouve_rien_quand_rien_ne_correspond():
    memory = FailureMemory()
    _record(memory, "sum even numbers", "odd numbers were summed")
    assert memory.recall("translate this text to spanish") == []


def test_bloc_de_prompt_dit_qu_un_souvenir_est_un_prior():
    """Sans cet avertissement, le modele traite d'anciennes conclusions comme des faits."""
    memory = FailureMemory()
    _record(memory, "sum even numbers", "odd numbers were summed")
    block = memory.prompt_block("sum even numbers")
    assert "prior" in block.lower()
    assert "GUARD" in block


def test_bloc_de_prompt_vide_sans_souvenir():
    assert FailureMemory().prompt_block("n'importe quoi") == ""


def test_chaine_detecte_une_reecriture(tmp_path: Path):
    """Une memoire editable est la chose la plus facile a reecrire discretement."""
    path = tmp_path / "m.jsonl"
    memory = FailureMemory(path=path)
    _record(memory, "objectif A")
    _record(memory, "objectif B")
    assert memory.verify()[0]

    text = path.read_text(encoding="utf-8").replace("cause reelle", "cause falsifiee")
    path.write_text(text, encoding="utf-8")
    reborn = FailureMemory(path=path)
    ok, bad = reborn.verify()
    assert not ok, "une reecriture doit casser la chaine"
    assert bad >= 0


def test_empreinte_stable_et_sensible():
    assert fingerprint("sum even numbers") == fingerprint("sum even numbers")
    assert fingerprint("sum even numbers") != fingerprint("sum odd numbers")


# --------------------------------------------------------------------------- #
# Routeur de confiance
# --------------------------------------------------------------------------- #


def test_ucb_essaye_tous_les_bras_avant_de_juger():
    """On ne peut rien dire d'un bras qu'on n'a pas mesure.

    UCB explore parce qu'un bras jamais tire a un score infini : il faut donc
    CHOISIR puis OBSERVER. Choisir sans jamais mesurer ne fait rien avancer, et
    c'est le comportement correct — pas une lacune.
    """
    router = TrustRouter()
    seen = []
    for _ in range(len(DEFAULT_ARMS)):
        arm = router.choose("write a function")
        seen.append(arm.name)
        router.observe("write a function", arm, success=True)
    assert set(seen) == {a.name for a in DEFAULT_ARMS}


def test_recompense_penalise_le_cout():
    router = TrustRouter()
    cheap = next(a for a in DEFAULT_ARMS if a.name == "minimal")
    dear = next(a for a in DEFAULT_ARMS if a.name == "renforce")
    r_cheap = router.observe("write a function", cheap, success=True)
    r_dear = router.observe("write a function", dear, success=True)
    assert r_cheap > r_dear, "a succes egal, la configuration legere doit mieux noter"


def test_echec_penalise_plus_que_le_cout():
    router = TrustRouter()
    arm = DEFAULT_ARMS[0]
    assert router.observe("prove a theorem", arm, success=False) < 0


def test_etat_persiste_entre_instances(tmp_path: Path):
    path = tmp_path / "trust.json"
    first = TrustRouter(path=path)
    first.observe("write a function", first.choose("write a function"), success=True)
    second = TrustRouter(path=path)
    assert second.observations == 1
    assert second.table()


def test_table_et_rapport_exploitables():
    router = TrustRouter()
    arm = router.choose("write a function")
    router.observe("write a function", arm, success=True)
    rows = router.table()
    assert rows and rows[0][2] == 1
    assert "recompense" in router.report()


def test_rapport_vide_explique_l_exploration():
    report = TrustRouter().report()
    assert "explore" in report.lower()


def test_classification_des_taches():
    assert task_class("write a function that sums even numbers") == "code"
    assert task_class("analyze this repository") == "repo"
    assert task_class("prove the median property") == "math"
    assert task_class("draft a report") == "writing"
    assert task_class("bonjour") == "generic"


def test_une_intention_technique_prime_sur_un_verbe_de_redaction():
    """Bug reel : « write a function… » tombait dans `writing` par ordre alphabetique."""
    assert task_class("write a script that sorts a list") == "code"
    assert task_class("write a report") == "writing"
