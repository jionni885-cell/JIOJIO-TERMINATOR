"""TrustRouter — choisir COMBIEN de verification depenser, et l'apprendre.

Le probleme
-----------
Verifier coute. Sur une tache facile, un panel de 5 critiques et 3 candidats par
tour est du gaspillage ; sur une tache ou le modele se trompe souvent, c'est le
minimum vital. Un harness fixe est donc toujours mal regle pour une partie des
taches.

La reponse : un bandit contextuel. Chaque "bras" est une configuration de
verification (nombre de candidats, de tours, taille du panel, risque accepte).
La recompense penalise le cout : `succes - lambda * cout_normalise`. On choisit
par UCB1 (optimisme face a l'incertitude), et on apprend en continu.

Pourquoi UCB1 et pas un reglage manuel
--------------------------------------
Un reglage manuel optimise la tache d'hier. UCB1 garantit un regret logarithmique
et explore automatiquement les configurations qu'on n'aurait pas pense a essayer.
Cout : trois lignes d'arithmetique. Aucune dependance.

Pourquoi pas de modele de ML
----------------------------
Avec quelques dizaines d'observations par classe, un modele appris serait du
bruit deguise en sagesse. Le bandit est le bon outil a cette echelle, et il
s'explique en une phrase — critere decisif pour un composant de confiance.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["Arm", "TrustRouter", "DEFAULT_ARMS", "task_class"]


# --------------------------------------------------------------------------- #
# Bras disponibles
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Arm:
    """Une configuration de verification. `cost` est en unites arbitraires."""

    name: str
    candidates: int          # candidats generes par tour
    rounds: int              # tours maximum
    panel_size: int          # critiques independants
    alpha: float             # risque d'erreur accepte par la porte conforme
    cost: float              # cout relatif (appels + verifications)

    @property
    def budget_calls(self) -> int:
        return self.candidates * self.rounds


#: Echelle croissante. Volontairement grossiere : trois regimes se distinguent
#: en pratique (leger, standard, lourd), et multiplier les bras ralentit
#: l'apprentissage sans rien apporter avant plusieurs centaines d'observations.
DEFAULT_ARMS: tuple[Arm, ...] = (
    Arm("minimal", candidates=1, rounds=1, panel_size=1, alpha=0.20, cost=1.0),
    Arm("standard", candidates=3, rounds=3, panel_size=3, alpha=0.05, cost=4.0),
    Arm("renforce", candidates=3, rounds=5, panel_size=5, alpha=0.01, cost=8.0),
)


def task_class(objective: str, domain: str = "") -> str:
    """Classe de tache : un regroupement grossier mais stable.

    Volontairement base sur des mots-cles et non sur un plongement vectoriel :
    deux taches qui partagent les memes mots-cles partagent presque toujours
    les memes modes d'echec, et ce calcul reste explicable et hors-ligne.
    """
    keywords = {
        "code": ("function", "implement", "code", "bug", "refactor", "test", "script"),
        "math": ("prove", "sum", "median", "prime", "derive", "equation", "calcul"),
        "analysis": ("analy", "compare", "explain", "why", "review", "audit"),
        "writing": ("write", "draft", "document", "report", "summary", "translate"),
        "repo": ("repository", "file", "module", "dependency", "build", "commit"),
        "search": ("find", "search", "source", "reference", "cite"),
    }
    low = f"{domain} {objective}".lower()
    scores = {
        label: sum(1 for word in words if word in low) for label, words in keywords.items()
    }
    # A egalite, l'ordre de priorite tranche — PAS l'ordre alphabetique. Sans cela,
    # « write a function that sums even numbers » tombait dans `writing` parce que
    # « writing » vient apres « code » : un verbe de redaction ne doit jamais
    # l'emporter sur une intention technique.
    priority = ("code", "repo", "math", "analysis", "search", "writing")
    best = max(scores.items(), key=lambda pair: (pair[1], -priority.index(pair[0])))
    return best[0] if best[1] else "generic"


# --------------------------------------------------------------------------- #
# Routeur
# --------------------------------------------------------------------------- #


@dataclass
class TrustRouter:
    """Bandit UCB1 sur (classe de tache x configuration de verification)."""

    arms: tuple[Arm, ...] = DEFAULT_ARMS
    path: Path | None = None
    #: (classe, bras) -> [tirages, recompense cumulee]
    stats: dict[tuple[str, str], list[float]] = field(default_factory=dict)
    observations: int = 0
    #: Poids du cout dans la recompense. A 0, on maximise la reussite sans
    #: regarder la depense ; a 1, on ne depense plus rien.
    cost_weight: float = 0.35
    _loaded: bool = False

    def __post_init__(self) -> None:
        if self.path is not None and not self._loaded:
            self.load()
            self._loaded = True

    # -- decision ----------------------------------------------------------- #

    def choose(self, objective: str, *, domain: str = "", explore: float = 1.0) -> Arm:
        """Choisit un bras par UCB1. `explore` module l'optimisme.

        Un bras jamais essaye est toujours prioritaire : on ne peut rien dire
        d'un bras qu'on n'a pas mesure.
        """
        klass = task_class(objective, domain)
        total = max(1.0, float(self.observations))
        best: tuple[float, Arm] | None = None

        for arm in self.arms:
            pulls, reward = self._get(klass, arm)
            if pulls == 0:
                score = float("inf")  # exploration obligatoire
            else:
                mean = reward / pulls
                bonus = explore * math.sqrt(2.0 * math.log(total) / pulls)
                score = mean + bonus
            if best is None or score > best[0]:
                best = (score, arm)
        assert best is not None
        return best[1]

    def observe(
        self, objective: str, arm: Arm | str, *, success: bool, cost: float | None = None
    ) -> float:
        """Enregistre le resultat d'un essai et renvoie la recompense attribuee."""
        name = arm.name if isinstance(arm, Arm) else arm
        klass = task_class(objective)
        norm_cost = (cost if cost is not None else self._cost_of(name)) / max(
            1.0, max(a.cost for a in self.arms)
        )
        reward = (1.0 if success else 0.0) - self.cost_weight * norm_cost
        cells = self._get(klass, name)
        cells[0] += 1
        cells[1] += reward
        self.observations += 1
        self.save()
        return reward

    # -- etat --------------------------------------------------------------- #

    def _cost_of(self, name: str) -> float:
        for arm in self.arms:
            if arm.name == name:
                return arm.cost
        return 1.0

    def _get(self, klass: str, arm: Arm | str) -> list[float]:
        name = arm.name if isinstance(arm, Arm) else arm
        return self.stats.setdefault((klass, name), [0.0, 0.0])

    def table(self) -> list[tuple[str, str, float, float, float]]:
        """(classe, bras, tirages, recompense moyenne, cout) — pour rapport."""
        rows: list[tuple[str, str, float, float, float]] = []
        for (klass, name), (pulls, reward) in sorted(self.stats.items()):
            if pulls <= 0:
                continue
            rows.append((klass, name, pulls, reward / pulls, self._cost_of(name)))
        return rows

    def best_arm(self, klass: str) -> tuple[str, float] | None:
        rows = [r for r in self.table() if r[0] == klass and r[2] >= 2]
        if not rows:
            return None
        row = max(rows, key=lambda r: r[3])
        return row[1], row[3]

    # -- persistance -------------------------------------------------------- #

    def save(self) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "observations": self.observations,
            "cost_weight": self.cost_weight,
            "stats": {f"{k[0]}|{k[1]}": v for k, v in self.stats.items()},
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def load(self) -> None:
        if self.path is None or not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return  # un etat illisible ne doit jamais bloquer : on repart a zero
        self.observations = int(payload.get("observations", 0))
        self.cost_weight = float(payload.get("cost_weight", self.cost_weight))
        for key, value in (payload.get("stats") or {}).items():
            klass, _, name = key.partition("|")
            self.stats[(klass, name)] = [float(value[0]), float(value[1])]

    def report(self) -> str:
        rows = self.table()
        if not rows:
            return (
                "Aucune observation. Le routeur explore : chaque configuration sera\n"
                "essayee avant d'etre jugee (c'est le principe d'UCB, pas une lacune)."
            )
        out = [f"{'classe':<10} {'bras':<10} {'tirages':>8} {'recompense':>11} {'cout':>6}"]
        out.append("-" * 50)
        for klass, name, pulls, mean, cost in rows:
            out.append(f"{klass:<10} {name:<10} {pulls:>8.0f} {mean:>11.3f} {cost:>6.1f}")
        out.append("")
        out.append(
            f"recompense = succes - {self.cost_weight:.2f} x cout normalise. "
            "Une recompense negative signifie : ce bras coute plus qu'il ne rapporte."
        )
        return "\n".join(out)
