"""Garde anti-oscillation — empecher la boucle de se mordre la queue.

Resultat de theorie du controle (arXiv 2606.27409) : dans un systeme
multi-agents avec verificateurs, modelise comme un consensus retarde sur un
graphe avec noeuds correcteurs ancres, il existe un **seuil de stabilite
exact**. La correction, lorsqu'elle est trop **forte** ou trop **retardee**,
destabilise la boucle par un **mode oscillatoire**.

Consequence pratique : « boucler plus » n'est pas « corriger mieux ». Le systeme
doit detecter :

  * le **flip-flop** : alternance entre deux etats sans progres ;
  * le **plateau** : plus aucun gain marginal ;
  * la **regression cyclique** : retour a un etat deja visite.

Dans ces cas : **escalade**, pas boucle infinie.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..core.errors import OscillationDetected


@dataclass(frozen=True)
class ProgressPoint:
    """Un tour de boucle resume."""

    round_index: int
    score: float          # 0..1 — part de regles satisfaites
    digest: str           # empreinte de l'artefact
    errors: int = 0


@dataclass
class OscillationGuard:
    """Suit la progression et coupe court aux boucles steriles."""

    window: int = 6
    min_gain: float = 0.01          # gain minimal pour considerer qu'on progresse
    history: list[ProgressPoint] = field(default_factory=list)

    # -- enregistrement ----------------------------------------------------- #

    def record(self, point: ProgressPoint) -> None:
        self.history.append(point)

    # -- diagnostics -------------------------------------------------------- #

    def is_flip_flop(self) -> bool:
        """Deux empreintes alternent : on decore sans avancer."""
        digests = [p.digest for p in self.history[-self.window :]]
        if len(digests) < 4:
            return False
        distinct = list(dict.fromkeys(digests))
        return len(distinct) == 2 and digests[-1] == digests[-3] and digests[-2] == digests[-4]

    def is_plateau(self) -> bool:
        """Aucun gain marginal sur la fenetre."""
        recent = self.history[-self.window :]
        if len(recent) < 3:
            return False
        gains = [
            recent[i + 1].score - recent[i].score for i in range(len(recent) - 1)
        ]
        return all(g < self.min_gain for g in gains)

    def is_cycling(self) -> bool:
        """Retour a un etat deja visite apres l'avoir quitte."""
        digests = [p.digest for p in self.history]
        if len(digests) < 5:
            return False
        return digests[-1] in digests[:-2]

    def is_regressing(self) -> bool:
        """Le score baisse deux fois de suite : la correction nuit."""
        if len(self.history) < 3:
            return False
        a, b, c = (p.score for p in self.history[-3:])
        return b < a - self.min_gain and c < b - self.min_gain

    def best(self) -> ProgressPoint | None:
        """Meilleur etat rencontre — on ne livre jamais pire que le meilleur."""
        return max(self.history, key=lambda p: p.score) if self.history else None

    # -- decision ----------------------------------------------------------- #

    def should_stop(self) -> tuple[bool, str]:
        if self.is_flip_flop():
            return True, "oscillation : alternance entre deux etats sans progres"
        if self.is_regressing():
            return True, "regression : la correction degrade le resultat"
        if self.is_cycling():
            return True, "cycle : retour a un etat deja visite"
        if self.is_plateau():
            return True, "plateau : plus aucun gain marginal"
        return False, ""

    def assert_stable(self) -> None:
        stop, reason = self.should_stop()
        if stop:
            raise OscillationDetected(reason)

    def damping(self) -> float:
        """Facteur d'amortissement recommande pour le tour suivant.

        Quand la boucle s'agite, on reduit l'amplitude de la correction au lieu
        de l'augmenter — c'est exactement ce que dit la theorie de la stabilite.
        """
        recent = self.history[-self.window :]
        if len(recent) < 2:
            return 1.0
        switches = sum(
            1
            for i in range(len(recent) - 1)
            if recent[i].digest != recent[i + 1].digest
            and i > 0
            and recent[i - 1].digest == recent[i + 1].digest
        )
        return max(0.25, 1.0 - 0.2 * switches)

    def summary(self) -> str:
        if not self.history:
            return "aucun tour enregistre"
        pts = " -> ".join(f"{p.score:.2f}" for p in self.history[-6:])
        return f"progression {pts} | amortissement {self.damping():.2f}"


__all__ = ["ProgressPoint", "OscillationGuard"]
