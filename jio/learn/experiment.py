"""Experience A/B/C : la memoire des echecs apporte-t-elle un gain ATTRIBUABLE ?

Le piege que ce module evite
----------------------------
Comparer « sans memoire » et « avec memoire » ne mesure rien de propre : quand la
memoire ajoute un bloc au prompt, le modele — meme simule — change de tirage. Le
gain observe melange alors trois choses : la mecanique, la loterie de graine, et
l'effet reel. Presenter ce total comme « le gain de la memoire » serait malhonnete.

Protocole a trois bras, dont un contraste propre
------------------------------------------------
  A. FROID   : memoire vide.
  B. TEMOIN  : memoire remplie, mais effet d'avertissement DESACTIVE
               (`warning_gain = 0`). Le prompt change, la probabilite non.
  C. CHAUD   : memoire remplie, effet d'avertissement ACTIF.

  A -> B  isole l'artefact de loterie de graine. Sa valeur attendue est nulle ;
          l'afficher telle quelle est le seul moyen d'etre credible si elle ne
          l'est pas.
  B -> C  est un contraste CAUSALEMENT PROPRE : les deux bras envoient des
          prompts IDENTIQUES (donc des tirages identiques) et ne different que
          par la probabilite de repondre correctement. C'est la seule mesure qui
          attribue le gain a la mecanique et non au hasard.

Ce que le chiffre est, et ce qu'il n'est pas
--------------------------------------------
Le modele est SIMULE. Un modele reel n'apprend pas davantage parce qu'un fichier
JSON a change : l'effet d'avertissement est une MODELISATION explicite du
mecanisme documente (retour d'echec structure : +5 a +10 points ; AHE : +7,3).
Le chiffre mesure donc la MECANIQUE — memoriser, rappeler, injecter, et l'effet
que la litterature attribue a cette injection — pas la performance d'un modele
reel. Un resultat nul est un resultat valide, et il sera affiche tel quel.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from ..bench.tasks import TASKS
from ..core.types import Mission
from .memory import FailureMemory

__all__ = ["ABCResult", "run_abc"]


def _set_warning_gain(engine: object, gain: float) -> None:
    """Regle l'effet d'avertissement sur tous les generateurs simules."""
    for provider in getattr(engine, "generators", ()):
        if hasattr(provider, "warning_gain"):
            provider.warning_gain = gain


@dataclass
class ABCResult:
    """Resultats des trois bras. `isolated_gain` est la seule mesure causale."""

    cold_success: int = 0
    control_success: int = 0
    warm_success: int = 0
    total: int = 0
    recorded: int = 0
    missions_with_recall: int = 0
    per_task: dict[str, tuple[int, int, int]] = field(default_factory=dict)

    def _rate(self, wins: int) -> float:
        return wins / self.total if self.total else 0.0

    @property
    def cold_rate(self) -> float:
        return self._rate(self.cold_success)

    @property
    def control_rate(self) -> float:
        return self._rate(self.control_success)

    @property
    def warm_rate(self) -> float:
        return self._rate(self.warm_success)

    @property
    def lottery_artifact(self) -> float:
        """A -> B : effet du seul changement de prompt. Attendu : ~0."""
        return self.control_rate - self.cold_rate

    @property
    def isolated_gain(self) -> float:
        """B -> C : effet du mecanisme, tirages identiques. La mesure qui compte."""
        return self.warm_rate - self.control_rate

    def intervalle(self, bras_gauche: int, bras_droite: int) -> tuple[float, float, bool]:
        """IC95 et significativite de la difference entre deux bras.

        Le banc de code affichait un ecart sans barre d'erreur et tirait une conclusion
        que 15 essais ne portaient pas. Ce banc-la a exactement le meme probleme, avec un
        `total` encore plus petit : il rend donc, lui aussi, son intervalle et son
        verdict, au lieu d'un chiffre nu.
        """
        from ..bench.incertitude import ecart_a_la_une

        gauche = [1.0] * bras_gauche + [0.0] * (self.total - bras_gauche)
        droite = [1.0] * bras_droite + [0.0] * (self.total - bras_droite)
        return ecart_a_la_une(gauche, droite)

    def budget_de_mesure(self) -> int:
        """Combien d'essais par bras pour demontrer le gain attribuable observe."""
        from ..bench.incertitude import essais_necessaires

        return essais_necessaires(self.control_rate, self.warm_rate)

    def budget_du_bruit(self) -> int:
        """Combien d'essais pour demontrer l'artefact de loterie (qui ne devrait pas exister).

        Symetrique du precedent, et plus utile qu'il n'y parait : si le bruit exige peu
        d'essais a se demontrer, c'est que le banc est trop petit pour attribuer quoi que
        ce soit a la memoire.
        """
        from ..bench.incertitude import essais_necessaires

        return essais_necessaires(self.cold_rate, self.control_rate)


def run_abc(
    *,
    skill: float = 0.12,
    runs: int = 3,
    rounds: int = 4,
    seed_base: int = 0,
    warning_gain: float = 0.20,
    task_ids: tuple[str, ...] | None = None,
) -> ABCResult:
    """Execute les trois bras. La memoire vit sur disque, comme en usage reel."""
    from ..cli import _check, _simulated_engine
    from ..loop.engine import WorkItem

    result = ABCResult()
    tasks = [t for t in TASKS if not task_ids or t.id in task_ids]

    def _mission(task, seed: int, memory: FailureMemory | None, gain: float | None, phase: str) -> bool:
        engine = _simulated_engine(task, skill=skill, seed=seed, max_rounds=rounds)
        engine.memory = memory
        if gain is not None:
            _set_warning_gain(engine, gain)
        report = engine.run(
            Mission(objective=task.objective, id=f"{task.id}-{phase}-{seed}", max_rounds=rounds),
            WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                     checks=dict(task.checks), spec=task.spec()),
        )
        return bool(_check(report.subject, task))

    with tempfile.TemporaryDirectory(prefix="jio-learn-") as tmp:
        memory_path = Path(tmp) / "failures.jsonl"

        # --- A. FROID ------------------------------------------------------ #
        cold_memory = FailureMemory(path=memory_path)
        for task in tasks:
            wins = sum(
                _mission(task, seed_base + run, cold_memory, None, "cold")
                for run in range(runs)
            )
            result.per_task[task.id] = (wins, 0, 0)
        result.cold_success = sum(c for c, _, _ in result.per_task.values())
        result.recorded = cold_memory.size

        # --- B. TEMOIN (memoire presente, aucun effet) --------------------- #
        control_memory = FailureMemory(path=memory_path)
        for task in tasks:
            wins = 0
            for run in range(runs):
                if control_memory.recall(task.objective):
                    result.missions_with_recall += 1
                wins += _mission(task, seed_base + run, control_memory, 0.0, "control")
            cold, _, _ = result.per_task[task.id]
            result.per_task[task.id] = (cold, wins, 0)
        result.control_success = sum(control for _, control, _ in result.per_task.values())

        # --- C. CHAUD (meme prompt, probabilite differente) ---------------- #
        warm_memory = FailureMemory(path=memory_path)
        for task in tasks:
            wins = sum(
                _mission(task, seed_base + run, warm_memory, warning_gain, "warm")
                for run in range(runs)
            )
            cold, control, _ = result.per_task[task.id]
            result.per_task[task.id] = (cold, control, wins)
        result.warm_success = sum(w for _, _, w in result.per_task.values())

    result.total = len(tasks) * runs
    return result
