"""Tests des mecanismes anti-erreur : oscillation, integrite, metamorphique, conforme."""

from __future__ import annotations

import pytest

from jio.audit.blame import FirstErrorLocator, credit, shapley_values
from jio.audit.integrity import IntegrityMonitor
from jio.audit.oscillation import OscillationGuard, ProgressPoint
from jio.core.journal import Journal
from jio.core.types import ExploitKind, TrustLevel
from jio.gate.conformal import Calibration, ConformalGate
from jio.verify.entropy import semantic_entropy
from jio.verify.metamorphic import MetamorphicTester, jaccard


# --------------------------------------------------------------------------- #
# Oscillation — le seuil de stabilite (arXiv 2606.27409)
# --------------------------------------------------------------------------- #


def test_flip_flop_detected():
    g = OscillationGuard(window=6)
    for i, d in enumerate(["A", "B", "A", "B", "A", "B"]):
        g.record(ProgressPoint(round_index=i, score=0.5, digest=d))
    stop, why = g.should_stop()
    assert stop
    assert "oscillation" in why or "cycle" in why or "plateau" in why


def test_plateau_detected():
    g = OscillationGuard(window=4)
    for i in range(4):
        g.record(ProgressPoint(round_index=i, score=0.6, digest=f"d{i}"))
    assert g.is_plateau()
    assert g.should_stop()[0]


def test_progress_keeps_loop_alive():
    g = OscillationGuard(window=4)
    for i, s in enumerate([0.2, 0.4, 0.6, 0.8]):
        g.record(ProgressPoint(round_index=i, score=s, digest=f"d{i}"))
    assert not g.should_stop()[0]


def test_regression_detected():
    g = OscillationGuard(window=4)
    for i, s in enumerate([0.9, 0.7, 0.4]):
        g.record(ProgressPoint(round_index=i, score=s, digest=f"d{i}"))
    assert g.is_regressing()
    assert g.should_stop()[0]


def test_guard_remembers_best_state():
    """On ne livre jamais pire que le meilleur etat rencontre."""
    g = OscillationGuard()
    g.record(ProgressPoint(0, 0.3, "a"))
    g.record(ProgressPoint(1, 0.9, "b"))
    g.record(ProgressPoint(2, 0.4, "c"))
    assert g.best().score == 0.9


def test_damping_reduces_amplitude_when_agitated():
    g = OscillationGuard(window=6)
    for i, d in enumerate(["A", "B", "A", "B", "A", "B"]):
        g.record(ProgressPoint(i, 0.5, d))
    assert g.damping() < 1.0


# --------------------------------------------------------------------------- #
# Integrite — les 6 exploits du Reward Hacking Benchmark
# --------------------------------------------------------------------------- #


def test_clean_journal_has_no_exploit():
    j = Journal()
    j.append("stage", {"name": "spec", "produced": True, "verified": True})
    j.append("witness", {"rule": "R-001", "ok": True, "stdout": "6 tests passes"})
    report = IntegrityMonitor().audit(j)
    assert report.clean
    assert report.steps == 2


def test_leakage_detected():
    j = Journal()
    j.append("read", {"path": "hidden_tests/test_gold.py"}, trust=TrustLevel.EXTERNAL)
    report = IntegrityMonitor().audit(j)
    assert not report.clean
    assert any(e.kind is ExploitKind.LEAKAGE for e in report.exploits)


def test_tampering_detected():
    j = Journal()
    j.append("write", {"path": "verifier.py", "content": "skip verification"})
    report = IntegrityMonitor().audit(j)
    assert any(e.kind is ExploitKind.TAMPERING for e in report.exploits)


def test_tampering_on_bypass_language():
    j = Journal()
    j.append("edit", {"target": "verifier", "diff": "bypass the check"})
    report = IntegrityMonitor().audit(j)
    assert any(e.kind is ExploitKind.TAMPERING for e in report.exploits)


def test_proxy_gaming_detected():
    j = Journal()
    j.append("witness", {"rule": "R-001", "ok": True, "stdout": "{}"})
    report = IntegrityMonitor().audit(j)
    assert any(e.kind is ExploitKind.PROXY_GAMING for e in report.exploits)


def test_skipped_verification_counts_as_proxy_gaming():
    j = Journal()
    j.append("witness", {"rule": "R-001", "ok": True, "stdout": "ok", "skipped": True})
    report = IntegrityMonitor().audit(j)
    assert any(e.kind is ExploitKind.PROXY_GAMING for e in report.exploits)


def test_special_casing_detected():
    j = Journal()
    j.append("candidate", {"code_tail": "if len(nums) == 5: return 12  # hack"})
    report = IntegrityMonitor().audit(j)
    assert any(e.kind is ExploitKind.SPECIAL_CASING for e in report.exploits)


def test_rationalization_detected():
    j = Journal()
    j.append("candidate", {"reason": "j'ai saute l'etape, optimisation d'efficacite"})
    report = IntegrityMonitor().audit(j)
    assert not report.clean


def test_phase_transition_verification_dropoff():
    """Au-dela de 5 etapes sans verification, le RHB documente une transition de phase."""
    j = Journal()
    for i in range(6):
        j.append("stage", {"name": f"s{i}", "produced": True, "verified": i < 2,
                           "depends_on": f"s{i-1}" if i else ""})
    report = IntegrityMonitor().audit(j)
    assert any("transition de phase" in e.detail for e in report.exploits)


def test_enforce_raises_on_dirty_report():
    from jio.core.errors import IntegrityViolation

    j = Journal()
    j.append("read", {"path": "grader/solution.py"})
    report = IntegrityMonitor().audit(j)
    with pytest.raises(IntegrityViolation):
        IntegrityMonitor().enforce(report)


# --------------------------------------------------------------------------- #
# Metamorphique — detecter les hallucinations coherentes (MetaQA)
# --------------------------------------------------------------------------- #


def test_jaccard_bounds():
    assert jaccard("abc def", "abc def") == 1.0
    assert jaccard("abc", "xyz") == 0.0
    assert 0 < jaccard("le chat noir", "le chat blanc") < 1


def test_invariance_break_is_flagged():
    """Un modele qui change de reponse quand on ajoute un mot de politesse est suspect."""
    tester = MetamorphicTester(max_mutations=4)

    def fragile(question: str) -> str:
        return "42 est la reponse attendue" if question.endswith("reponse.") else "je ne sais pas"

    findings = tester.test("Quelle est la reponse ?", fragile)
    assert findings
    assert any(f.severity.value in {"high", "medium"} for f in findings)


def test_stable_answer_passes():
    tester = MetamorphicTester(max_mutations=6)
    findings = tester.test("Combien font 2 + 2 ?", lambda q: "4")
    assert findings == ()


def test_negation_check_skipped_for_non_boolean_question():
    """La negation n'a pas de sens sur une question numerique : pas de faux positif."""
    tester = MetamorphicTester(max_mutations=6)
    findings = tester.test("Combien font 7 * 6 ?", lambda q: "42")
    assert not any(f.mutation == "negation" for f in findings)


def test_semantic_entropy_low_when_consistent():
    r = semantic_entropy(["la reponse est 42", "la reponse est 42", "la reponse est 42"])
    assert r.risk == "faible"
    assert r.confident
    assert r.clusters == 1


def test_semantic_entropy_high_when_divergent():
    r = semantic_entropy(["Paris", "Berlin", "Tokyo", "Madrid", "Rome"])
    assert r.risk == "eleve"
    assert r.clusters >= 4


# --------------------------------------------------------------------------- #
# Conformite — la seule vraie garantie
# --------------------------------------------------------------------------- #


def test_uncalibrated_gate_is_fail_closed():
    g = ConformalGate(alpha=0.05)
    assert not g.calibrated
    accepted, reason = g.decide(0.95)
    assert accepted
    accepted, reason = g.decide(0.5)
    assert not accepted
    assert "NON calibre" in reason


def test_calibration_lowers_or_raises_threshold_coherently():
    g = ConformalGate(alpha=0.1, min_samples=10)
    for i in range(40):
        g.observe(0.9 if i % 3 else 0.4, correct=(i % 3 != 0))
    assert g.calibrated
    tau = g.tau()
    assert 0.0 <= tau <= 1.0
    assert g.empirical_risk() <= 0.5


def test_solve_min_samples_matches_conformal_bound():
    g = ConformalGate(alpha=0.05)
    assert g.solve_min_samples() == 19
    assert ConformalGate(alpha=0.1).solve_min_samples() == 9


def test_le_minimum_d_echantillons_par_defaut_est_vingt():
    """`min_samples = 20` n'est pas un reglage de confort : c'est ce que la borne conforme
    demande pour alpha = 0,05 (`solve_min_samples()` en calcule 19), plus un.

    Mesure a l'origine : `jio mutants` a montre que ce 20 pouvait passer a 21 sans qu'aucun
    test ne bouge. Or 19 points ne suffisent pas a la borne, et 20 la rend atteignable : le
    seuil exact decide donc de ce que « calibre » veut dire.
    """
    g = ConformalGate(alpha=0.05)
    assert g.min_samples == 20
    assert g.solve_min_samples() == g.min_samples - 1
    for _ in range(19):
        g.observe(0.99, correct=True)
    assert not g.calibrated, "19 points ne suffisent pas : la porte doit rester prudente"
    assert g.tau() == g.default_tau
    g.observe(0.99, correct=True)
    assert g.calibrated, "le 20e point atteint le minimum declare"


def test_charger_un_fichier_absent_ne_compte_aucun_point(tmp_path):
    """`load` rend le nombre de points REELLEMENT charges. Un fichier absent en vaut zero.

    Mesure a l'origine : `jio mutants` a montre que ce `return 0` pouvait devenir `return 1`.
    Un point fantome rendrait la porte « calibree » sur une calibration qui n'existe pas —
    exactement la garantie que ce module vend.
    """
    g = ConformalGate(min_samples=3)
    assert g.load(tmp_path / "absent.jsonl") == 0
    assert not g.calibrated and g.tau() == g.default_tau


def test_gate_persists_calibration(tmp_path):
    path = tmp_path / "calib.jsonl"
    g = ConformalGate(min_samples=3)
    g.observe_many([Calibration(0.8, True), Calibration(0.9, True), Calibration(0.3, False)])
    g.save(path)
    g2 = ConformalGate(min_samples=3)
    assert g2.load(path) == 3
    assert g2.calibrated


# --------------------------------------------------------------------------- #
# Blame et credit — theorie des jeux
# --------------------------------------------------------------------------- #


def test_first_error_locator_binary_search():
    loc = FirstErrorLocator(faulty=lambda i: i >= 7, length=10)
    assert loc.locate() == 7


def test_first_error_returns_none_when_all_ok():
    loc = FirstErrorLocator(faulty=lambda i: False, length=10)
    assert loc.locate() is None


def test_shapley_credit_is_conserved():
    """Propriete fondamentale : sum(phi_i) == v(N)."""
    players = ["a", "b", "c"]
    value = lambda S: float(len(S) ** 2)  # noqa: E731
    vals = shapley_values(players, value)
    assert sum(vals.values()) == pytest.approx(value(frozenset(players)), abs=1e-6)


def test_shapley_symmetric_players_get_equal_credit():
    vals = shapley_values(["a", "b"], lambda S: float(len(S)))
    assert vals["a"] == pytest.approx(vals["b"])


def test_credit_flags_harmful_agent():
    """Un agent a valeur negative n'est pas inutile : il est NUISIBLE."""
    value = lambda S: 1.0 if "good" in S and "bad" not in S else 0.0  # noqa: E731
    report = credit(["good", "bad"], value)
    assert report.conserved
    assert "bad" in report.saboteurs


def test_la_variante_polie_AJOUTE_la_queue_et_ne_la_retire_pas() -> None:
    """`_polite` ajoute une queue : la transformation doit etre un ajout, jamais un retrait.

    Mesure a l'origine : `jio mutants` a montre que le `+` de cette concatenation pouvait
    devenir un `-` sans qu'aucun test ne bouge. Une variante qui RETIRE du texte ne teste
    plus la meme propriete : elle en teste une autre, et l'invariance mesuree ne veut
    plus rien dire.
    """
    from jio.verify.metamorphic import _NULL_TAIL, _polite

    texte = "Combien font 2 + 2 ?"
    variante = _polite(texte)
    assert variante.startswith(texte)
    assert len(variante) == len(texte) + len(_NULL_TAIL)
    assert variante.endswith(_NULL_TAIL)


def test_une_phrase_unique_n_est_pas_reorganisee_en_silence() -> None:
    """Avec une seule phrase, il n'y a rien a reordonner : la variante vaut l'original.

    Mesure a l'origine : `jio mutants` a montre que la borne `len(parts) > 1` pouvait passer
    a 2 sans qu'aucun test ne bouge. Une variante identique a l'original ne teste RIEN : le
    rapport la compterait comme une transformation reussie, donc comme une invariance
    verifiee, alors qu'aucune transformation n'a eu lieu.
    """
    from jio.verify.metamorphic import _reorder_sentences

    assert _reorder_sentences("Une seule phrase.") == "Une seule phrase."
    deux = _reorder_sentences("Premiere. Deuxieme.")
    assert deux == "Deuxieme. Premiere."

def test_la_variante_en_MAJUSCULES_change_vraiment_le_texte() -> None:
    """`_case_swap` : la variante metamorphique doit DIFFERER de l'original.

    Mesure a l'origine : `jio mutants` a montre que le `is False` de cette condition pouvait
    devenir `is True` sans qu'aucun test ne bouge. La variante devenait alors IDENTIQUE a
    l'original pour un texte en minuscules : le test metamorphique comparait un texte a
    lui-meme, comptait une transformation reussie, et n'avait plus rien verifie — le pire
    cas pour une mesure, puisqu'il produit un « invariant tenu » a partir de rien.
    """
    from jio.verify.metamorphic import _case_swap

    minuscule = "combien font 2 + 2 ?"
    variante = _case_swap(minuscule)
    assert variante == minuscule.upper()
    assert variante != minuscule
    # Un texte deja en majuscules n'est pas retransforme : la variante vaut l'original, et
    # c'est voulu (l'axe « casse » n'a plus rien a changer, il ne fait pas semblant).
    deja = "COMBIEN FONT 2 + 2 ?"
    assert _case_swap(deja) == deja
    # Au-dela de 400 caracteres, la variante est laissee telle quelle : borne de cout.
    assert _case_swap("a" * 401) == "a" * 401


def test_une_question_non_fermee_n_a_pas_d_axe_de_negation() -> None:
    """`_is_boolean_answer` : sans marqueur oui/non, l'axe de negation ne s'applique pas.

    Mesure a l'origine : `jio mutants` a montre que ce `return False` pouvait devenir `True`
    sans qu'aucun test ne bouge. Toute question (« quelle est la capitale… ») aurait alors
    ete traitee comme une question fermee : le systeme aurait cherche une reponse oui/non
    dans une phrase qui n'en a pas, et aurait signale une inversion inexistante. Un faux
    positif d'incoherence coute plus cher que pas de controle du tout : il fait douter d'une
    reponse juste.
    """
    from jio.verify.metamorphic import _is_boolean_answer

    assert _is_boolean_answer("La reponse est-elle correcte ? oui ou non") is True
    assert _is_boolean_answer("Reponds vrai ou faux") is True
    assert _is_boolean_answer("Quelle est la capitale de la France ?") is False
    assert _is_boolean_answer("Explique la methode des moindres carres") is False
    assert _is_boolean_answer("") is False
    assert _is_boolean_answer("oui " + "x" * 250) is False
