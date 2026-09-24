"""Tests de bout en bout : la boucle centrale sur le banc d'essai reel."""

from __future__ import annotations

import pytest

from jio.audit.panel import DEFAULT_PERSONAS, AuditPanel
from jio.bench.tasks import TASKS, TASKS_BY_ID, build_bank
from jio.core.errors import FailClosed
from jio.core.journal import Journal
from jio.core.types import Mission, MissionStatus, Rule, RuleKind, Spec
from jio.loop.engine import Engine, EngineConfig, WorkItem, _extract_code
from jio.providers.simulated import Persona, SimulatedProvider, make_panel
from jio.spec.compiler import SpecCompiler
from jio.verify.executable import ExecutableProver, Sandbox


# --------------------------------------------------------------------------- #
# Extraction de code
# --------------------------------------------------------------------------- #


def test_extract_code_from_fenced_block():
    text = "voici\n```python\ndef f():\n    return 1\n```\nfin"
    assert "def f()" in _extract_code(text, "f")


def test_extract_code_prefers_entrypoint():
    text = "```python\ndef other():\n    pass\n```\n```python\ndef target():\n    return 2\n```"
    assert "def target()" in _extract_code(text, "target")


def test_extract_code_empty_on_prose():
    assert _extract_code("je ne sais pas", "f") == ""


# --------------------------------------------------------------------------- #
# SPEC grounding
# --------------------------------------------------------------------------- #


def test_spec_compiler_always_emits_boundary_rule():
    spec = SpecCompiler().compile("calculer la somme des nombres pairs d'une liste")
    assert len(spec.rules) >= 2
    assert any(r.kind is RuleKind.BOUNDARY for r in spec.rules)


def test_spec_compiler_declares_under_specified():
    """Un systeme honnete dit ce qu'il ne sait pas verifier."""
    spec = SpecCompiler().compile("court")
    assert spec.under_specified


def test_spec_rejects_empty_rule():
    with pytest.raises(ValueError):
        Rule(id="", statement="x")


# --------------------------------------------------------------------------- #
# Fail-closed
# --------------------------------------------------------------------------- #


def test_prover_refuses_without_any_check():
    """Sans preuve disponible, le mode fail-closed interdit de continuer."""
    spec = Spec(mission="rien", rules=(Rule(id="R-001", statement="une regle"),))
    with pytest.raises(FailClosed):
        ExecutableProver().prove("def f(): pass", spec)


def test_prover_accepts_correct_code():
    task = TASKS_BY_ID["sum_even"]
    res = ExecutableProver(sandbox=Sandbox(timeout=15)).prove(
        task.correct, task.spec(), hidden_checks=task.checks, entrypoint=task.entrypoint
    )
    assert res.passed
    assert res.ratio == 1.0
    assert len(res.witnesses) == len(task.rules)


def test_prover_rejects_wrong_code():
    task = TASKS_BY_ID["sum_even"]
    res = ExecutableProver(sandbox=Sandbox(timeout=15)).prove(
        task.distractors[0], task.spec(),
        hidden_checks=task.checks, entrypoint=task.entrypoint,
    )
    assert not res.passed
    assert res.failures
    assert res.ratio < 1.0


# --------------------------------------------------------------------------- #
# Banc d'essai : oracles caches
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("task", TASKS, ids=[t.id for t in TASKS])
def test_correct_solution_passes_all_oracles(task):
    sb = Sandbox(timeout=15)
    program = task.correct + "\n\n" + "\n".join(task.checks[k] for k in task.checks)
    res = sb.run_python(program)
    assert res.ok, f"{task.id}: la solution de reference echoue — banc invalide"


@pytest.mark.parametrize("task", TASKS, ids=[t.id for t in TASKS])
def test_every_distractor_is_rejected(task):
    """Chaque distracteur doit etre rejete : sinon la specification est trop faible."""
    sb = Sandbox(timeout=15)
    for i, distractor in enumerate(task.distractors):
        program = distractor + "\n\n" + "\n".join(task.checks[k] for k in task.checks)
        assert not sb.run_python(program).ok, (
            f"{task.id}: le distracteur {i} passe tous les tests — spec trop faible"
        )


# --------------------------------------------------------------------------- #
# Fournisseur simule : determinisme
# --------------------------------------------------------------------------- #


def test_simulated_provider_is_deterministic():
    from jio.providers.base import Message

    bank = build_bank()
    p1 = SimulatedProvider(persona=Persona(name="x", skill=0.5), bank=bank)
    p2 = SimulatedProvider(persona=Persona(name="x", skill=0.5), bank=bank)
    msgs = [Message("user", TASKS[0].objective)]
    assert p1.complete(msgs, seed=7).text == p2.complete(msgs, seed=7).text


def test_correlated_panel_shares_bias():
    bank = build_bank()
    providers = make_panel(["a", "b", "c"], 0.6, bank, correlated=True)
    assert all(p.persona.bias == 0.15 for p in providers)


# --------------------------------------------------------------------------- #
# Boucle complete
# --------------------------------------------------------------------------- #


def _engine(task, skill, seed=0, rounds=4, correlated=False):
    bank = build_bank()
    personas = list(DEFAULT_PERSONAS)
    providers = make_panel([p.name for p in personas], skill, bank, correlated=correlated)
    return Engine(
        generators=providers[:3],
        journal=Journal(),
        panel=AuditPanel.simulated(personas, seed=seed),
        prover=ExecutableProver(sandbox=Sandbox(timeout=15)),
        spec_compiler=SpecCompiler(),
        config=EngineConfig(max_rounds=rounds, candidates_per_round=3),
    )


def test_engine_delivers_on_high_skill():
    task = TASKS_BY_ID["safe_divide"]
    report = _engine(task, skill=0.95).run(
        Mission(objective=task.objective, max_rounds=4),
        WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                 checks=task.checks, spec=task.spec()),
    )
    assert report.status in (
        MissionStatus.DELIVERED, MissionStatus.DELIVERED_WITH_RESERVATION
    )
    assert report.passed == report.total_checks
    assert report.integrity.clean


def test_engine_abstains_rather_than_delivering_an_error():
    """Le point le plus important : une erreur ne part JAMAIS silencieusement."""
    task = TASKS_BY_ID["parse_duration"]
    report = _engine(task, skill=0.0).run(  # modele qui se trompe toujours
        Mission(objective=task.objective, max_rounds=3),
        WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                 checks=task.checks, spec=task.spec()),
    )
    assert report.status is MissionStatus.ABSTAINED
    assert report.abstention_reason
    assert report.passed < report.total_checks


def test_engine_journal_chain_stays_valid():
    task = TASKS_BY_ID["sum_even"]
    engine = _engine(task, skill=0.6)
    report = engine.run(
        Mission(objective=task.objective, max_rounds=3),
        WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                 checks=task.checks, spec=task.spec()),
    )
    ok, bad = engine.journal.verify_chain()
    assert ok, f"chaine cassee a l'index {bad}"
    assert len(engine.journal) > 5
    assert report.journal_digest == engine.journal.head


def test_engine_records_witnesses_for_every_rule():
    task = TASKS_BY_ID["median"]
    report = _engine(task, skill=0.9).run(
        Mission(objective=task.objective, max_rounds=3),
        WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                 checks=task.checks, spec=task.spec()),
    )
    rule_ids = {w.rule_id for w in report.witnesses}
    assert rule_ids == {r.id for r in task.rules}


def test_report_serialises_to_json():
    import json

    task = TASKS_BY_ID["safe_divide"]
    report = _engine(task, skill=0.8).run(
        Mission(objective=task.objective, max_rounds=2),
        WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                 checks=task.checks, spec=task.spec()),
    )
    data = json.loads(report.to_json())
    assert data["objective"] == task.objective
    assert "witnesses" in data and "integrity" in data and "spec" in data
