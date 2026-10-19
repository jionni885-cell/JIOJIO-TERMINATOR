"""Agregation prudente des votes, sans pretendre a une garantie byzantine.

`n >= 3f + 1` est une borne issue de protocoles de consensus byzantin sous des
hypotheses precises de communication, d'identites et de fautes. Ici, les avis
LLM ne sont ni des noeuds independants ni des messages authentifies par un
protocole distribue : estimer `f` depuis le desaccord et appliquer cette borne
est donc une HEURISTIQUE CONSERVATRICE, pas une garantie de Lamport. Elle est
utile pour empecher un panel trop petit de donner une fausse impression de
robustesse, mais ne prouve ni l'independance ni la verite d'un verdict.

Les votes restent secrets, collectes avant toute synthese, et ne sont jamais
moyennes. Un desaccord persistant declenche une escalade ; un avis indisponible
(ABSTAIN/ERROR) bloque la certification au lieu d'etre traite comme un vote
minoritaire ordinaire.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ..core.errors import QuorumNotReached
from ..core.types import Severity, Verdict, Vote


@dataclass(frozen=True)
class ConsensusOutcome:
    """Resultat d'un vote."""

    decision: Verdict
    reached: bool
    agreement: float  # part du verdict majoritaire
    quorum_required: int
    panel_size: int
    estimated_faulty: int
    tally: Mapping[str, int]
    dissent: tuple[str, ...]
    confidence: float
    #: Nombre de sources de modele DISTINCTES ayant vote. C'est ce chiffre,
    #: et non la taille du panel ni le nombre de verdicts différents, qui plafonne
    #: la confiance : plusieurs personas du même modèle ne deviennent pas plusieurs
    #: sources indépendantes en divergeant.
    effective_panel: int = 0
    reason: str = ""

    @property
    def unanimous(self) -> bool:
        return self.agreement >= 1.0 and self.reached


@dataclass
class ConsensusEngine:
    """Agrege des votes secrets en une decision defendable."""

    #: Seuil de supermajorite heuristique ; ce n'est pas une garantie byzantine.
    threshold: float = 2.0 / 3.0
    #: En dessous de ce panel, on refuse de conclure quelque chose de fort.
    min_panel: int = 3

    def quorum_for(self, faulty: int) -> int:
        """`n >= 3f + 1` — borne classique de la tolerance byzantine."""
        return 3 * max(0, faulty) + 1

    def decide(self, votes: Sequence[Vote]) -> ConsensusOutcome:
        if not votes:
            raise QuorumNotReached("aucun vote fourni")

        tally: dict[str, int] = {}
        for v in votes:
            tally[v.decision.value] = tally.get(v.decision.value, 0) + 1

        panel = len(votes)
        top = max(tally.items(), key=lambda kv: kv[1])
        runner_up = sorted(tally.values(), reverse=True)
        second = runner_up[1] if len(runner_up) > 1 else 0

        # Estimation du nombre de voix divergentes au sens byzantin : les voix
        # qui ne vont PAS au verdict majoritaire sont traitees comme fautives
        # potentielles. C'est conservateur, et c'est voulu.
        estimated_faulty = max(0, min(second, panel - top[1]))
        quorum = self.quorum_for(estimated_faulty)

        agreement = top[1] / panel
        dissent = tuple(
            f"{v.agent}:{v.decision.value}" for v in votes if v.decision.value != top[0]
        )

        # La decorrelation vient des SOURCES, pas des verdicts : un même modèle qui
        # donne trois PASS et un FAIL reste une seule source, pas deux voix independantes.
        # L'identifiant de provider sert de repli si le modele n'est pas renseigne ;
        # l'agent ne sert qu'en dernier recours pour les votes de test locaux.
        identities = {
            f"model:{v.model}"
            if v.model
            else f"provider:{v.provider}"
            if v.provider
            else f"agent:{v.agent}"
            for v in votes
        }
        effective_panel = len(identities)

        reasons: list[str] = []
        reached = True

        # An abstention/error is missing evidence, not a competing opinion. Treating it
        # as an ordinary minority vote lets a majority PASS mask a reviewer that could
        # not complete its check. Fail closed: the caller can retry or abstain, but this
        # panel cannot certify the artifact.
        unavailable = [
            f"{v.agent}:{v.decision.value}"
            for v in votes
            if v.decision in (Verdict.ABSTAIN, Verdict.ERROR)
        ]
        if unavailable:
            reached = False
            reasons.append(
                "verification indisponible (" + ", ".join(unavailable) + ") : "
                "un avis absent ou en erreur ne compte pas comme un vote PASS"
            )

        if panel < self.min_panel:
            reached = False
            reasons.append(f"panel trop petit ({panel} < {self.min_panel})")

        if agreement < self.threshold:
            reached = False
            reasons.append(
                f"accord {agreement:.0%} < seuil {self.threshold:.0%} — desaccord reel"
            )

        if quorum > panel:
            reached = False
            reasons.append(
                f"quorum byzantin non satisfait : {panel} voix pour f={estimated_faulty} "
                f"(requis n >= {quorum})"
            )

        if effective_panel < 2 and panel >= 2:
            reached = False
            reasons.append(
                "panel non decorrele : tous les agents partagent modele et verdict — "
                "ce n'est pas un consensus, c'est un echo"
            )

        conf = self._confidence(votes, agreement, effective_panel)

        return ConsensusOutcome(
            decision=Verdict(top[0]) if reached else Verdict.ABSTAIN,
            reached=reached,
            agreement=round(agreement, 4),
            quorum_required=quorum,
            panel_size=panel,
            estimated_faulty=estimated_faulty,
            tally=tally,
            dissent=dissent,
            confidence=conf,
            effective_panel=effective_panel,
            reason=" ; ".join(reasons)
            or "accord suffisant et quorum byzantin satisfait",
        )

    @staticmethod
    def _confidence(
        votes: Sequence[Vote], agreement: float, effective_panel: int
    ) -> float:
        """Confiance moyenne ponderee par la taille effective du panel."""
        if not votes:
            return 0.0
        mean = sum(v.confidence for v in votes) / len(votes)
        # Le facteur de decorrelation : 1 voix utile => confiance plafonnee.
        decorrelation = min(1.0, 0.55 + 0.15 * effective_panel)
        return round(min(1.0, agreement * decorrelation * (0.5 + 0.5 * mean)), 4)

    @staticmethod
    def disagreement_severity(outcome: ConsensusOutcome) -> Severity:
        """Un desaccord profond n'est pas anodin : il signale un vrai probleme."""
        if outcome.reached and outcome.unanimous:
            return Severity.INFO
        if outcome.reached:
            return Severity.LOW
        if outcome.agreement >= 0.5:
            return Severity.HIGH
        return Severity.CRITICAL

    @staticmethod
    def entropy_of_votes(votes: Sequence[Vote]) -> float:
        """Entropie normalisee du vote : mesure du desordre du panel."""
        if not votes:
            return 0.0
        tally: dict[str, int] = {}
        for v in votes:
            tally[v.decision.value] = tally.get(v.decision.value, 0) + 1
        n = len(votes)
        raw = -sum((c / n) * math.log(c / n) for c in tally.values())
        return round(raw / math.log(n), 4) if n > 1 else 0.0


__all__ = ["ConsensusEngine", "ConsensusOutcome"]
