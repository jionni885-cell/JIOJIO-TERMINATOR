"""Attribution du blame — qui est responsable de l'echec, et qui a tente de reparer.

Fondement : « Who Gets the Reward & Who Gets the Blame? » (arXiv 2511.10687).

  * **Succes** -> Shapley. Le credit est reparti equitablement, avec
    conservation exacte : `sum(phi_i) == v(N)`. Aucune inflation de credit.
  * **Echec**  -> localisation du **premier pas fautif**, puis distinction
    entre une **tentative de reparation** et un **pas aligne sur l'echec**.

Cette distinction est cruciale : penaliser un agent qui essaie de rattraper
la situation detruit exactement le comportement qu'on veut encourager.

Implementation pratique :
  * localisation du premier echec par **recherche binaire de prefixe**, en
    `O(log T)` quand la propriete « prefixe » est monotone ;
  * Shapley exact pour de petits panneaux (n <= 6), echantillonne au-dela.
"""

from __future__ import annotations

import itertools
import math
import random
from dataclasses import dataclass, field
from typing import Callable, Sequence

from ..core.types import Blame


# --------------------------------------------------------------------------- #
# Echecs : localisation du premier pas fautif
# --------------------------------------------------------------------------- #


@dataclass
class FirstErrorLocator:
    """Trouve le plus petit index `i` tel que le prefixe `[0..i]` est fautif.

    Suppose la monotonie : une fois le deraillement survenu, il ne disparait
    pas. Repose sur un predicat qu'on peut evaluer sur un prefixe.
    """

    faulty: Callable[[int], bool]
    length: int

    def locate(self) -> int | None:
        if self.length <= 0:
            return None
        if not self.faulty(self.length - 1):
            return None  # rien n'est fautif
        lo, hi = 0, self.length - 1
        while lo < hi:
            mid = (lo + hi) // 2
            if self.faulty(mid):
                hi = mid
            else:
                lo = mid + 1
        return lo

    def steps(self) -> int:
        """Nombre d'evaluations necessaires (utilitaire de diagnostic)."""
        return max(1, math.ceil(math.log2(max(2, self.length))))


@dataclass
class BlameLedger:
    """Registre de blame d'une mission."""

    steps: list[str] = field(default_factory=list)          # agent par etape
    messages: list[str] = field(default_factory=list)
    failure_index: int | None = None
    recovery_indices: tuple[int, ...] = ()

    def mark_recovery(self, index: int) -> None:
        self.recovery_indices = tuple(sorted(set(self.recovery_indices) | {index}))

    def resolve(self, first_faulty: int | None) -> tuple[Blame, ...]:
        """Convertit l'index fautif en blame(s) — en epargnant les reparateurs."""
        if first_faulty is None:
            return ()
        out: list[Blame] = []
        agent = self.steps[first_faulty] if first_faulty < len(self.steps) else "inconnu"
        msg = self.messages[first_faulty] if first_faulty < len(self.messages) else ""
        out.append(Blame(agent=agent, step=first_faulty, message=msg[:300]))
        for idx in self.recovery_indices:
            if idx > first_faulty:
                out.append(
                    Blame(
                        agent=self.steps[idx] if idx < len(self.steps) else "inconnu",
                        step=idx,
                        message=self.messages[idx][:300] if idx < len(self.messages) else "",
                        is_repair_attempt=True,
                    )
                )
        return tuple(out)

    @staticmethod
    def is_repair_attempt(before: float, after: float, tolerance: float = 0.0) -> bool:
        """Un pas qui ameliore le score est une reparation, pas une faute."""
        return after > before + tolerance


# --------------------------------------------------------------------------- #
# Succes : credit de Shapley
# --------------------------------------------------------------------------- #


def shapley_values(
    players: Sequence[str],
    value: Callable[[frozenset[str]], float],
    *,
    exact_limit: int = 6,
    samples: int = 200,
    seed: int = 0,
) -> dict[str, float]:
    """Calcule les valeurs de Shapley d'un jeu cooperatif.

    `value(S)` renvoie le score du systeme quand seule la coalition `S` agit.
    Propriete garantie : `sum(valeurs) == value(tous)` (conservation du credit).
    """
    n = len(players)
    if n == 0:
        return {}

    if n <= exact_limit:
        values = {p: 0.0 for p in players}
        for i, p in enumerate(players):
            for size in range(n):
                weight = math.factorial(size) * math.factorial(n - size - 1) / math.factorial(n)
                for combo in itertools.combinations(
                    [x for x in range(n) if x != i], size
                ):
                    S = frozenset(players[j] for j in combo)
                    values[p] += weight * (value(S | {p}) - value(S))
        return {k: round(v, 6) for k, v in values.items()}

    # Approximation Monte-Carlo : echantillonnage de permutations.
    rng = random.Random(seed)
    acc = {p: 0.0 for p in players}
    for _ in range(samples):
        order = list(players)
        rng.shuffle(order)
        S: frozenset[str] = frozenset()
        prev = value(S)
        for p in order:
            S = S | {p}
            cur = value(S)
            acc[p] += cur - prev
            prev = cur
    return {k: round(v / samples, 6) for k, v in acc.items()}


@dataclass
class CreditReport:
    """Repartition du credit d'un succes."""

    values: dict[str, float]
    total: float
    conserved: bool
    saboteurs: tuple[str, ...] = ()

    def render(self) -> str:
        lines = [f"credit total = {self.total:.3f} (conserve: {self.conserved})"]
        for agent, val in sorted(self.values.items(), key=lambda kv: -kv[1]):
            tag = "  <-- NUISIBLE" if val < 0 else ""
            lines.append(f"  {agent:<24} {val:+.3f}{tag}")
        return "\n".join(lines)


def credit(
    players: Sequence[str],
    value: Callable[[frozenset[str]], float],
    **kwargs: object,
) -> CreditReport:
    """Shapley + verification de conservation.

    Une valeur **negative** identifie un agent qui *diminue* la performance du
    systeme. Ce n'est pas la meme chose qu'un agent inutile : c'est un agent
    nuisible, et il faut le dire.
    """
    vals = shapley_values(players, value, **kwargs)  # type: ignore[arg-type]
    total = value(frozenset(players))
    return CreditReport(
        values=vals,
        total=total,
        conserved=abs(sum(vals.values()) - total) < 1e-6,
        saboteurs=tuple(a for a, v in vals.items() if v < -1e-6),
    )


__all__ = ["FirstErrorLocator", "BlameLedger", "shapley_values", "credit", "CreditReport"]
