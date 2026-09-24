"""Consensus tolerant aux fautes byzantines.

Deux regles non negociables, l'une mathematique, l'autre empirique.

**1. Quorum `n >= 3f + 1` (Lamport).** Avec `f` agents fautifs ou menteurs,
il faut au moins `3f + 1` participants pour garantir qu'une majorite honnete
l'emporte. Le moteur estime `f` a partir du desaccord observe et **refuse de
conclure** si le panel est trop petit pour la faute constatee.

**2. Aucune pression sociale.** « Conformity Breaks Conformal Prediction »
(2026) mesure que la conformite en systeme multi-agents fait chuter la
couverture de **90 % a 74 %** et ouvre une attaque ciblee sur les elements
de faible confiance. Donc :

    les votes sont secrets, collectes en parallele, et jamais moyennes.

Un desaccord n'est pas une erreur a lisser : c'est **le signal le plus
informatif du systeme**. Un desaccord persistant declenche une escalade,
jamais une moyenne silencieuse.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..core.errors import QuorumNotReached
from ..core.types import Severity, Verdict, Vote


@dataclass(frozen=True)
class ConsensusOutcome:
    """Resultat d'un vote."""

    decision: Verdict
    reached: bool
    agreement: float                 # part du verdict majoritaire
    quorum_required: int
    panel_size: int
    estimated_faulty: int
    tally: Mapping[str, int]
    dissent: tuple[str, ...]
    confidence: float
    #: Nombre de couples (modele, verdict) DISTINCTS ayant vote. C'est ce chiffre,
    #: et non la taille du panel, qui plafonne la confiance : cinq agents sur un
    #: seul modele ne valent pas cinq agents. Il etait calcule puis jete — donc
    #: invisible pour l'utilisateur qui cherchait pourquoi une mission parfaite
    #: restait « avec reserve ».
    effective_panel: int = 0
    reason: str = ""

    @property
    def unanimous(self) -> bool:
        return self.agreement >= 1.0 and self.reached


@dataclass
class ConsensusEngine:
    """Agrege des votes secrets en une decision defendable."""

    #: Seuil de supermajorite. 2/3 est exactement la borne de Lamport pour f=1.
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

        # Fautes correlees : meme modele + meme decision = une seule voix utile.
        effective_panel = len({(v.model or v.provider, v.decision.value) for v in votes})

        reasons: list[str] = []
        reached = True

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
            reason=" ; ".join(reasons) or "accord suffisant et quorum byzantin satisfait",
        )

    @staticmethod
    def _confidence(votes: Sequence[Vote], agreement: float, effective_panel: int) -> float:
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
