"""Tests du consensus : quorum byzantin, decorrelation, anti-conformisme."""

from __future__ import annotations

import pytest

from jio.audit.consensus import ConsensusEngine
from jio.core.errors import QuorumNotReached
from jio.core.types import Verdict, Vote


def _votes(decisions, model="m1"):
    return [
        Vote(agent=f"a{i}", decision=Verdict(d), confidence=0.8, model=model)
        for i, d in enumerate(decisions)
    ]


def test_quorum_follows_byzantine_bound():
    """n >= 3f + 1 — borne de Lamport."""
    eng = ConsensusEngine()
    assert eng.quorum_for(0) == 1
    assert eng.quorum_for(1) == 4
    assert eng.quorum_for(2) == 7


def test_unanimous_with_heterogeneous_models_reaches_consensus():
    eng = ConsensusEngine()
    votes = [
        Vote(agent="a", decision=Verdict.PASS, confidence=0.9, model="m1"),
        Vote(agent="b", decision=Verdict.PASS, confidence=0.85, model="m2"),
        Vote(agent="c", decision=Verdict.PASS, confidence=0.8, model="m3"),
        Vote(agent="d", decision=Verdict.PASS, confidence=0.75, model="m4"),
    ]
    out = eng.decide(votes)
    assert out.reached
    assert out.decision is Verdict.PASS
    assert out.unanimous


def test_split_panel_refuses_to_conclude():
    """Un desaccord reel ne se moyenne pas : il escalade."""
    eng = ConsensusEngine()
    votes = _votes(["pass", "pass", "fail", "fail"])
    out = eng.decide(votes)
    assert not out.reached
    assert out.decision is Verdict.ABSTAIN
    assert "accord" in out.reason
    assert out.dissent


def test_correlated_panel_is_an_echo_not_a_consensus():
    """Meme modele + meme verdict = une seule voix utile, pas quatre."""
    eng = ConsensusEngine()
    votes = [
        Vote(agent=f"a{i}", decision=Verdict.PASS, confidence=0.9, model="same-model")
        for i in range(4)
    ]
    out = eng.decide(votes)
    assert not out.reached
    assert "echo" in out.reason


def test_small_panel_refused():
    eng = ConsensusEngine(min_panel=3)
    out = eng.decide(_votes(["pass", "pass"]))
    assert not out.reached
    assert "trop petit" in out.reason


def test_no_votes_raises():
    with pytest.raises(QuorumNotReached):
        ConsensusEngine().decide([])


def test_entropy_of_votes_is_zero_when_unanimous():
    eng = ConsensusEngine()
    assert eng.entropy_of_votes(_votes(["pass", "pass", "pass"])) == pytest.approx(0.0, abs=1e-9)


def test_entropy_of_votes_when_split():
    """Entropie normalisee par log(n) : deux classes a 50/50 sur 4 votes valent 0.5."""
    eng = ConsensusEngine()
    ent = eng.entropy_of_votes(_votes(["pass", "fail", "pass", "fail"]))
    assert ent == pytest.approx(0.5, abs=1e-6)
    # Maximum uniquement quand TOUS les votes sont distincts.
    four = _votes(["pass", "fail", "abstain", "error"])
    assert eng.entropy_of_votes(four) == pytest.approx(1.0, abs=1e-6)


def test_severity_reflects_dissent():
    eng = ConsensusEngine()
    assert eng.disagreement_severity(eng.decide(_votes(["pass"] * 4))) is not None
    split = eng.decide(_votes(["pass", "fail", "fail", "pass"]))
    assert split.agreement == 0.5


# --------------------------------------------------------------------------- #
# Le motif dit ce qui s'est REELLEMENT passe
# --------------------------------------------------------------------------- #


def test_un_consensus_ATTEINT_sur_FAIL_n_est_pas_un_consensus_non_atteint() -> None:
    """Defaut trouve en branchant deux modeles sur une mission reelle.

    Le rapport affichait « preuve complete mais consensus non atteint : accord suffisant et
    quorum byzantin satisfait » : la phrase du SUCCES dans un message d'echec. La cause est
    un raccourci — la condition exige un verdict PASS, mais le message etait ecrit pour le
    seul cas « quorum non atteint ». Or le panel a parfaitement le droit de conclure FAIL :
    c'est meme son travail. Un motif faux envoie chercher au mauvais endroit.
    """
    from jio.audit.consensus import ConsensusOutcome
    from jio.core.types import Verdict
    from jio.loop.engine import _motif_consensus

    outcome = ConsensusOutcome(
        decision=Verdict.FAIL, reached=True, agreement=1.0, quorum_required=4,
        panel_size=5, estimated_faulty=0, tally={"fail": 5}, dissent=(),
        confidence=0.9, effective_panel=5, reason="accord suffisant et quorum byzantin satisfait",
    )

    motif = _motif_consensus(outcome)

    assert "non atteint" not in motif, motif
    assert "FAIL" in motif
    assert "100%" in motif and "5 voix" in motif


def test_un_quorum_non_atteint_dit_la_raison_du_quorum() -> None:
    from jio.audit.consensus import ConsensusOutcome
    from jio.core.types import Verdict
    from jio.loop.engine import _motif_consensus

    outcome = ConsensusOutcome(
        decision=Verdict.ABSTAIN, reached=False, agreement=0.6, quorum_required=5,
        panel_size=3, estimated_faulty=1, tally={"pass": 2, "fail": 1}, dissent=("a:fail",),
        confidence=0.4, effective_panel=2,
        reason="quorum byzantin non satisfait : 3 voix pour f=1 (requis n >= 5)",
    )

    motif = _motif_consensus(outcome)

    assert "non atteint" in motif
    assert "quorum byzantin non satisfait" in motif


def test_aucun_panel_est_dit_comme_tel() -> None:
    from jio.loop.engine import _motif_consensus

    assert "aucun panel" in _motif_consensus(None)


def test_le_panel_effectif_par_defaut_est_zero() -> None:
    """Mesure par mutation : le defaut `effective_panel = 0` n'etait protege par rien.

    Ce chiffre existe parce qu'un panel de cinq agents sur un seul modele ne vaut pas cinq
    agents : le compter comme tel est la faute qui rend un consensus decoratif. Un defaut a 1
    ferait dire « panel decorrele » a un resultat qui n'a jamais ete calcule — le genre de
    mensonge silencieux que ce champ a justement ete ajoute pour rendre visible.
    """
    from jio.audit.consensus import ConsensusOutcome
    from jio.core.types import Verdict

    resultat = ConsensusOutcome(
        decision=Verdict.ABSTAIN, reached=False, agreement=0.0, quorum_required=3,
        panel_size=0, estimated_faulty=0, tally={}, dissent=(), confidence=0.0,
    )
    assert resultat.effective_panel == 0
    assert resultat.unanimous is False
