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
    """Une memoire editable est la chose la plus facile a reecrire discretement.

    Deux niveaux sont verifies, et le second est nouveau :
      * la chaine de hashes DETECTE la reecriture (`verify_chain`) ;
      * une memoire dont la chaine ne tient pas n'est JAMAIS APPLIQUEE : elle est
        mise en quarantaine (renommee, jamais supprimee) et le systeme repart d'une
        memoire vide, en le disant. C'est ce qui empeche un fichier edite a la main
        de faire entrer des instructions dans les prompts (`prompt_block`).
    """
    path = tmp_path / "m.jsonl"
    memory = FailureMemory(path=path)
    _record(memory, "objectif A")
    _record(memory, "objectif B")
    assert memory.verify()[0]

    text = path.read_text(encoding="utf-8").replace("cause reelle", "cause falsifiee")
    path.write_text(text, encoding="utf-8")

    # Niveau 1 : la reecriture casse la chaine, et on sait OU.
    from jio.core.journal import Journal

    brut = Journal.from_jsonl(text)
    ok, bad = brut.verify_chain()
    assert not ok, "une reecriture doit casser la chaine"
    assert bad >= 0

    # Niveau 2 : et elle n'est jamais appliquee.
    reborn = FailureMemory(path=path)
    assert reborn.size == 0, "une memoire incoherente ne doit pas etre appliquee"
    assert reborn.verify()[0], "la memoire repart d'une chaine neuve et saine"
    assert any("incoherente" in n for n in reborn.journal.notices), reborn.journal.notices
    assert list(tmp_path.glob("m.jsonl.corrompu-*")), "le fichier est conserve, jamais supprime"


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


def test_le_budget_d_un_bras_est_candidats_fois_tours() -> None:
    """`candidates * rounds` est le nombre d'appels qu'un bras peut depenser.

    Mesure a l'origine : `jio mutants` a montre que la multiplication pouvait devenir une
    division ENTIERE sans qu'aucun test ne bouge (`3 x 2 = 6` contre `3 // 2 = 1`). Le bandit
    aurait alors cru qu'un bras coute six fois moins qu'il ne coute, et il l'aurait choisi
    pour cette raison — un reglage faux, invisible, qui decide du budget de verification.
    """
    from jio.trust.router import DEFAULT_ARMS, Arm

    assert Arm("x", candidates=3, rounds=2, panel_size=1, alpha=0.05, cost=1.0).budget_calls == 6
    assert Arm("x", candidates=1, rounds=1, panel_size=1, alpha=0.05, cost=1.0).budget_calls == 1
    for bras in DEFAULT_ARMS:
        assert bras.budget_calls == bras.candidates * bras.rounds


def test_le_bras_minimal_est_un_seul_appel_et_un_seul_tour() -> None:
    """Le bras le plus leger est la REFERENCE : « un appel, un tour ».

    Mesure a l'origine : `jio mutants` a montre que ses deux constantes pouvaient passer de
    1 a 2 sans qu'aucun test ne bouge. Un bras minimal a 2 candidats n'est plus le minimum,
    et le bandit n'aurait plus de point de comparaison bas.
    """
    from jio.trust.router import DEFAULT_ARMS

    minimal = DEFAULT_ARMS[0]
    assert minimal.name == "minimal"
    assert (minimal.candidates, minimal.rounds) == (1, 1)
    assert minimal.budget_calls == 1
    # Et l'echelle reste croissante : trois regimes distincts, volontairement grossiers.
    assert [a.budget_calls for a in DEFAULT_ARMS] == sorted(
        a.budget_calls for a in DEFAULT_ARMS
    )

def test_l_empreinte_d_un_echec_regarde_douze_tokens_de_symptome() -> None:
    """La fenetre est de 12 tokens trie : au-dela, le bruit du symptome ne change pas l'empreinte.

    Mesure a l'origine : `jio mutants` a montre que ce `12` pouvait devenir `13` sans qu'aucun
    test ne bouge. Une fenetre trop large rendrait l'empreinte sensible a des mots sans
    rapport, et le meme echec cesserait d'etre reconnu — donc la memoire cesserait de servir.
    """
    from jio.learn.memory import fingerprint

    base = " ".join(f"t{i:02d}" for i in range(1, 13))
    a = fingerprint("objectif", base + " zzz")
    b = fingerprint("objectif", base + " yyy")
    assert a == b, "au-dela du 12e token, le symptome ne doit plus compter"
    # ... et DANS la fenetre, il compte : sinon l'empreinte serait constante.
    c = fingerprint("objectif", base.replace("t01", "t99") + " zzz")
    assert c != a
    assert len(a) == 16 and a != fingerprint("autre objectif", base + " zzz")
