"""ConformalGate — la seule vraie garantie du systeme.

Tout le reste est heuristique. Ceci est **statistiquement valide**.

Objectif : garantir, sur les reponses **acceptees**, que
`Pr[erreur AND non-abstention] <= alpha`, **sans aucune hypothese sur la
distribution des donnees**, et avec peu d'exemples etiquetes.

Mise en oeuvre : controle de risque conforme (Angelopoulos et al.), applique a
une decision d'acceptation/abstention.

    Etant donne n exemples de calibration (score de confiance, correct ?),
    choisir le seuil tau le plus permissif tel que

        ( #{accepte ET faux} + 1 ) / ( #{accepte} + 1 )  <=  alpha

    L'acceptation est alors : accepte <=> score >= tau.

Trois avertissements, tires de la litterature, qu'il faut connaitre :

1. **La garantie est marginale, pas conditionnelle.** Elle borne le taux
   d'erreur *en moyenne*, pas sur chaque exemple.
2. **La conformite sociale casse la garantie.** « Conformity Breaks Conformal
   Prediction » (2026) : la pression sociale entre agents fait chuter la
   couverture de 90 % a 74 %. D'ou le vote en aveugle, non negociable.
3. **L'echangeabilite est requise.** Si la distribution derive, la garantie
   tient tant que calibration et test restent echangeables. On surveille
   donc la derive et on recalibre.

Sans donnees de calibration, le garde reste **fail-closed** : seuil eleve,
donc beaucoup d'abstentions — jamais d'acceptation optimiste.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Calibration:
    """Un point de calibration."""

    score: float      # confiance dans [0, 1]
    correct: bool


@dataclass
class ConformalGate:
    """Seuil d'acceptation calibre par controle de risque conforme."""

    alpha: float = 0.05
    #: Seuil par defaut sans calibration : volontairement severe (fail-closed).
    default_tau: float = 0.90
    min_samples: int = 20
    calibration: list[Calibration] = field(default_factory=list)
    _tau: float | None = None

    # -- alimentation -------------------------------------------------------- #

    def observe(self, score: float, correct: bool) -> None:
        self.calibration.append(Calibration(score=max(0.0, min(1.0, score)), correct=correct))
        self._tau = None  # invalider le cache

    def observe_many(self, points: Iterable[Calibration]) -> None:
        for p in points:
            self.observe(p.score, p.correct)

    def load(self, path: str | Path) -> int:
        p = Path(path)
        if not p.exists():
            return 0
        n = 0
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
                self.observe(float(obj["score"]), bool(obj["correct"]))
                n += 1
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
        return n

    def save(self, path: str | Path) -> None:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            for c in self.calibration:
                fh.write(json.dumps({"score": c.score, "correct": c.correct}) + "\n")

    # -- seuil --------------------------------------------------------------- #

    @property
    def calibrated(self) -> bool:
        return len(self.calibration) >= self.min_samples

    def tau(self) -> float:
        """Seuil d'acceptation calibre, ou seuil par defaut fail-closed."""
        if self._tau is not None:
            return self._tau
        if not self.calibrated:
            self._tau = self.default_tau
            return self._tau

        n = len(self.calibration)
        candidates = sorted({c.score for c in self.calibration})
        best = 1.0
        for tau in candidates:
            accepted = [c for c in self.calibration if c.score >= tau]
            wrong = sum(1 for c in accepted if not c.correct)
            # Borne superieure conforme : (erreurs + 1) / (acceptes + 1)
            risk = (wrong + 1) / (len(accepted) + 1)
            if risk <= self.alpha:
                best = min(best, tau)
        self._tau = best if best < 1.0 else 1.0
        return self._tau

    # -- decision ------------------------------------------------------------ #

    def decide(self, score: float) -> tuple[bool, str]:
        """Accepte ou s'abstient. Fail-closed : l'abstention est le defaut."""
        tau = self.tau()
        if score >= tau:
            return True, f"score {score:.3f} >= seuil calibre {tau:.3f}"
        return (
            False,
            f"score {score:.3f} < seuil {tau:.3f} "
            f"({'calibre sur ' + str(len(self.calibration)) + ' exemples' if self.calibrated else 'par defaut, NON calibre'})",
        )

    # -- diagnostics --------------------------------------------------------- #

    def empirical_risk(self) -> float:
        """Risque empirique mesure sur la calibration."""
        if not self.calibration:
            return float("nan")
        accepted = [c for c in self.calibration if c.score >= self.tau()]
        if not accepted:
            return 0.0
        wrong = sum(1 for c in accepted if not c.correct)
        return wrong / len(accepted)

    def solve_min_samples(self) -> int:
        """Nombre d'exemples necessaires pour que la borne soit atteignable.

        Avec `n` exemples, la borne conforme optimale est `1/(n+1)`.
        Pour garantir `alpha`, il faut donc `n >= 1/alpha - 1`.
        """
        return max(1, math.ceil(1 / self.alpha) - 1)

    def summary(self) -> str:
        return (
            f"alpha={self.alpha} tau={self.tau():.3f} "
            f"n={len(self.calibration)} (min {self.min_samples}, "
            f"theorique {self.solve_min_samples()}) "
            f"risque empirique={self.empirical_risk():.3f}"
            if self.calibration
            else f"alpha={self.alpha} tau={self.tau():.3f} NON CALIBRE (seuil par defaut)"
        )


__all__ = ["Calibration", "ConformalGate"]
