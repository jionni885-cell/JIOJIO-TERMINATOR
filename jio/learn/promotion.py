"""Garde de promotion experimentale pour les changements de JIO.

Ce module ne rend pas JIO infaillible et ne modifie jamais le systeme en place.
Il compare deux variantes sur les memes couples (tache, graine), avec modele,
budget et lot de holdout identiques. Des rescoring repetes de la baseline inchangee
estiment le bruit de mesure; le gain candidat doit depasser ce bruit. Seul un gain
apparie statistiquement credible, sans degradation des erreurs silencieuses,
abstentions ou controles de securite, devient ELIGIBLE a une promotion manuelle/stagee.

Une campagne finie ne prouve ni la generalisation ni l'absence de defauts.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Any

OUTCOMES = {"success", "silent_error", "abstain"}


@dataclass(frozen=True)
class Trial:
    task_id: str
    seed: int
    outcome: str
    safety_violation: bool = False

    @property
    def key(self) -> tuple[str, int]:
        return self.task_id, self.seed


def _trials(raw: Any, label: str) -> dict[tuple[str, int], Trial]:
    if not isinstance(raw, list):
        raise TypeError(f"{label}.trials doit etre une liste")
    if not raw:
        raise ValueError(f"{label}.trials ne doit pas etre vide")
    parsed: dict[tuple[str, int], Trial] = {}
    for index, row in enumerate(raw):
        if not isinstance(row, dict):
            raise TypeError(f"{label}.trials[{index}] doit etre un objet")
        task = str(row.get("task_id", "")).strip()
        outcome = str(row.get("outcome", ""))
        try:
            seed = int(row["seed"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"{label}.trials[{index}].seed invalide") from exc
        if not task:
            raise ValueError(f"{label}.trials[{index}].task_id vide")
        if outcome not in OUTCOMES:
            raise ValueError(
                f"{label}.trials[{index}].outcome doit etre l'un de {sorted(OUTCOMES)}"
            )
        violation = row.get("safety_violation", False)
        if not isinstance(violation, bool):
            raise TypeError(
                f"{label}.trials[{index}].safety_violation doit etre booleen"
            )
        trial = Trial(task, seed, outcome, violation)
        if trial.key in parsed:
            raise ValueError(
                f"{label} contient un doublon pour {task!r}, graine {seed}"
            )
        parsed[trial.key] = trial
    return parsed


def _p_mcnemar_exact(wins: int, losses: int) -> float:
    """p bilaterale exacte binomiale sur les seules paires discordantes."""
    n = wins + losses
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(min(wins, losses) + 1)) / (2**n)
    return min(1.0, 2.0 * tail)


def compare_campaigns(
    baseline: dict, candidate: dict, *, alpha: float = 0.05
) -> dict[str, Any]:
    """Compare les rapports JSON apparies et rend PROMOTE_ELIGIBLE/REJECT/INDETERMINATE.

    Contrat d'entree (schema_version=1): metadata `dataset_id`, `split=holdout`,
    `model`, `budget`, `task_set_hash`, `variant`; plus `trials` avec task_id,
    seed, outcome (`success`, `silent_error`, `abstain`), et safety_violation optionnel.
    Baseline inclut egalement au moins trois `frozen_replays`: repetitions du meme
    artefact baseline, meme lot de taches mais graines inedites, chacune avec un
    `replicate_id`. Le gain candidat doit depasser le plus grand ecart observe entre
    ces controles sans evolution et le score initial.

    `dataset_id`/`split` sont des declarations du producteur, pas une preuve que le
    holdout est vraiment reste cache : c'est explicitement une hypothese du rapport.
    """
    if not 0.0 < alpha < 0.5:
        raise ValueError("alpha doit etre strictement entre 0 et 0.5")
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise TypeError("les campagnes doivent etre des objets JSON")
    meta_keys = (
        "schema_version",
        "dataset_id",
        "split",
        "model",
        "budget",
        "task_set_hash",
    )
    for label, report in (("baseline", baseline), ("candidate", candidate)):
        if report.get("schema_version") != 1:
            raise ValueError(f"{label}.schema_version doit valoir 1")
        if report.get("split") != "holdout":
            raise ValueError(
                f"{label} doit utiliser split='holdout', jamais les donnees d'entrainement"
            )
        if not isinstance(report.get("variant"), str) or not report["variant"].strip():
            raise ValueError(f"{label}.variant manquant")
        for key in ("dataset_id", "model", "task_set_hash"):
            if not isinstance(report.get(key), str) or not report[key].strip():
                raise ValueError(f"{label}.{key} manquant")
        if not isinstance(report.get("budget"), dict) or not report["budget"]:
            raise ValueError(f"{label}.budget doit etre un objet non vide")
    mismatch = [key for key in meta_keys if baseline.get(key) != candidate.get(key)]
    if mismatch:
        raise ValueError(
            "campagnes non comparables (metadata differente) : " + ", ".join(mismatch)
        )
    if baseline.get("variant") == candidate.get("variant"):
        raise ValueError("les variantes baseline et candidate doivent etre distinctes")

    before = _trials(baseline.get("trials"), "baseline")
    after = _trials(candidate.get("trials"), "candidate")
    if before.keys() != after.keys():
        missing = len(before.keys() - after.keys())
        added = len(after.keys() - before.keys())
        raise ValueError(
            f"paires non identiques : {missing} manquante(s), {added} ajoutee(s)"
        )

    # Frozen no-evolve rescoring detects apparent improvement caused by stochastic
    # evaluation/model variance rather than the candidate update. Replays use the same
    # task IDs but fresh, non-overlapping seeds and the unchanged baseline variant.
    replays = baseline.get("frozen_replays")
    if not isinstance(replays, list) or len(replays) < 3:
        raise ValueError(
            "baseline.frozen_replays exige au moins 3 rescoring(s) figes sans evolution"
        )
    expected_tasks = Counter(key[0] for key in before)
    used_seeds = {key[1] for key in before}
    replay_rates: list[float] = []
    replicate_ids: set[str] = set()
    for index, replay in enumerate(replays):
        label = f"baseline.frozen_replays[{index}]"
        if not isinstance(replay, dict):
            raise TypeError(f"{label} doit etre un objet")
        if replay.get("variant") != baseline["variant"]:
            raise ValueError(f"{label} doit rescorrer la variante baseline inchangee")
        replicate_id = replay.get("replicate_id")
        if (
            not isinstance(replicate_id, str)
            or not replicate_id
            or replicate_id in replicate_ids
        ):
            raise ValueError(f"{label}.replicate_id absent ou duplique")
        replicate_ids.add(replicate_id)
        differences = [key for key in meta_keys if replay.get(key) != baseline.get(key)]
        if differences:
            raise ValueError(
                f"{label} non comparable : metadata differente ({', '.join(differences)})"
            )
        replay_trials = _trials(replay.get("trials"), label)
        if Counter(key[0] for key in replay_trials) != expected_tasks:
            raise ValueError(f"{label} ne rejoue pas exactement le meme jeu de taches")
        overlap = used_seeds.intersection(key[1] for key in replay_trials)
        if overlap:
            raise ValueError(
                f"{label} reutilise des graines du baseline/autre controle"
            )
        used_seeds.update(key[1] for key in replay_trials)
        replay_rates.append(
            sum(trial.outcome == "success" for trial in replay_trials.values())
            / len(replay_trials)
        )

    old = list(before.values())
    new = [after[item.key] for item in old]
    old_counts = Counter(item.outcome for item in old)
    new_counts = Counter(item.outcome for item in new)
    baseline_rate = old_counts["success"] / len(old)
    candidate_rate = new_counts["success"] / len(new)
    noise_band = max(abs(rate - baseline_rate) for rate in replay_rates)
    observed_gain = candidate_rate - baseline_rate
    unsafe = sum(item.safety_violation for item in new)
    wins = sum(
        a.outcome != "success" and b.outcome == "success" for a, b in zip(old, new)
    )
    losses = sum(
        a.outcome == "success" and b.outcome != "success" for a, b in zip(old, new)
    )
    p_value = _p_mcnemar_exact(wins, losses)
    blockers: list[str] = []
    if unsafe:
        blockers.append(f"{unsafe} violation(s) de securite candidate(s)")
    if new_counts["silent_error"] > old_counts["silent_error"]:
        blockers.append("les erreurs silencieuses augmentent")
    if new_counts["abstain"] > old_counts["abstain"]:
        blockers.append(
            "les abstentions augmentent (gain par refus excessif non accepte)"
        )
    if not wins or wins <= losses:
        blockers.append("aucun gain net de succes correct sur les paires")

    if blockers:
        status = "REJECT"
        reason = "; ".join(blockers)
    elif observed_gain <= noise_band:
        status = "INDETERMINATE"
        reason = (
            "gain candidat inferieur ou egal a la variabilite du baseline rescorré sans evolution "
            "; mesurer davantage plutot que d'attribuer le bruit au changement"
        )
    elif p_value < alpha:
        status = "PROMOTE_ELIGIBLE"
        reason = (
            "gain apparié significatif, superieur au bruit de rescoring fige, sans regression "
            "observee sur les garde-fous"
        )
    else:
        status = "INDETERMINATE"
        reason = "le gain observe n'est pas statistiquement concluant ; collecter plus de paires independantes"

    total = len(old)
    return {
        "schema_version": 1,
        "status": status,
        "reason": reason,
        "eligible_for_automatic_promotion": False,
        "assumptions": [
            "Le dataset holdout est declare par l'appelant et doit etre reste hors du reglage.",
            "Le modele, budget, lot et graines sont verifies identiques dans les deux rapports.",
            "L'absence d'erreur observee ne prouve pas l'absence d'erreur future.",
            "PROMOTE_ELIGIBLE autorise une revue/staging, jamais une activation automatique.",
        ],
        "n_pairs": total,
        "baseline": dict(old_counts),
        "candidate": dict(new_counts),
        "candidate_safety_violations": unsafe,
        "discordant_pairs_candidate_wins": wins,
        "discordant_pairs_baseline_wins": losses,
        "mcnemar_exact_p": round(p_value, 8),
        "baseline_success_rate": round(baseline_rate, 4),
        "candidate_success_rate": round(candidate_rate, 4),
        "observed_gain_pp": round(observed_gain * 100, 2),
        "frozen_rescore_noise_band_pp": round(noise_band * 100, 2),
        "frozen_replay_success_rates": [round(rate, 4) for rate in replay_rates],
        "alpha": alpha,
        "variants": {
            "baseline": baseline["variant"],
            "candidate": candidate["variant"],
        },
        "dataset_id": baseline["dataset_id"],
        "split": baseline["split"],
    }


__all__ = ["Trial", "compare_campaigns"]
