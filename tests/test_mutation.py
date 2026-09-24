"""Tests de la porte de mutation.

Idee verrouillee : « les regles passent » ne vaut que si elles peuvent ECHOUER.
Un mutant survivant n'accuse pas l'artefact, il accuse la specification — c'est
donc une RESERVE, jamais un rejet.

Mesure de reference obtenue pendant le developpement, sur la meme fonction :
  specification forte (deux assertions de VALEUR exacte) -> 3/4 mutants tues
  specification faible (une assertion « is not None »)   -> 0/4 mutant tue
Le score de mutation distingue donc reellement une specification utile d'une
decoration.
"""

from __future__ import annotations

from jio.core.types import Rule, RuleKind, Spec
from jio.verify.executable import ExecutableProver, Sandbox
from jio.verify.mutation import MUTATION_BUDGET, MutationReport, mutate

MEDIAN = """def median(nums):
    s = sorted(nums)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2
"""


def _score(source: str, checks: dict[str, str]) -> MutationReport:
    spec = Spec(
        mission="test",
        rules=tuple(Rule(id=k, statement=k, kind=RuleKind.TEST) for k in checks),
    )
    prover = ExecutableProver(sandbox=Sandbox(timeout=20))
    mutants = mutate(source, budget=4)
    killed, survivors = 0, []
    for mutant in mutants:
        res = prover.prove(mutant.source, spec, hidden_checks=checks)
        if res.passed:
            survivors.append(mutant)
        else:
            killed += 1
    return MutationReport(total=len(mutants), killed=killed, survived=tuple(survivors))


# --------------------------------------------------------------------------- #
# Generation des mutations
# --------------------------------------------------------------------------- #


def test_budget_respecte_et_mutants_distincts():
    mutants = mutate(MEDIAN, budget=4)
    assert len(mutants) <= 4
    assert len({m.source for m in mutants}) == len(mutants), "mutants dupliques"


def test_mutants_compilent():
    import ast

    for mutant in mutate(MEDIAN, budget=4):
        ast.parse(mutant.source)  # leve si le mutant est invalide


def test_mutation_sur_source_invalide_renvoie_vide():
    """Muter du code qui ne compile pas ne teste rien."""
    assert mutate("def f(:\n") == []


def test_le_budget_par_defaut_est_borne():
    """Chaque mutant coute une passe complete : on ne cherche pas l'exhaustivite."""
    assert 1 <= MUTATION_BUDGET <= 8


def test_les_labels_sont_lisibles_par_un_humain():
    labels = " ".join(m.label for m in mutate(MEDIAN, budget=4))
    assert any(word in labels for word in ("comparaison", "constante", "operateur", "booleen"))


# --------------------------------------------------------------------------- #
# Le score discrimine
# --------------------------------------------------------------------------- #


def test_specification_faible_est_detectee():
    """Une assertion « is not None » ne tue aucun mutant : elle ne teste rien."""
    report = _score(MEDIAN, {"R-1": "assert median([1, 2, 3, 4]) is not None"})
    assert report.total >= 3
    assert report.killed == 0
    assert report.weak
    assert report.score == 0.0


def test_specification_forte_tue_des_mutants():
    report = _score(
        MEDIAN,
        {"R-1": "assert median([1, 2, 3, 4]) == 2.5", "R-2": "assert median([3, 1, 2]) == 2"},
    )
    assert report.killed >= 2
    assert report.score > 0.5


# --------------------------------------------------------------------------- #
# Semantique du rapport
# --------------------------------------------------------------------------- #


def test_aucun_mutant_executable_n_est_pas_une_faiblesse():
    """Sans mutant a executer, on ne peut rien affirmer : ce n'est pas un echec."""
    report = MutationReport(total=0, killed=0)
    assert not report.weak
    assert report.score == 0.0
    assert "rien pu tester" in report.summary()


def test_resume_lisible():
    report = MutationReport(total=4, killed=3)
    assert "3/4" in report.summary()
    assert "75%" in report.summary()
