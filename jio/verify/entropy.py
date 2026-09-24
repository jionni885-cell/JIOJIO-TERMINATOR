"""Entropie semantique — mesurer l'incertitude sans verite terrain.

Principe (Farquhar, Kossen, Kuhn, Gal) : on echantillonne K reponses, on les
**regroupe par sens** (et non par forme de surface), puis on calcule l'entropie
de Shannon sur les clusters.

    * Faible entropie  -> le modele a une representation stable -> confiance.
    * Forte entropie   -> le modele improvise -> **confabulation probable**.

AUC mesuree : 0.80-0.85 en grey-box, contre 0.78-0.82 pour SelfCheckGPT,
et 0.88 pour la version adaptative + conformite (ACSE).

Ici, le clustering est lexical (Jaccard + entailment approximatif) : aucune
dependance, fonctionne en black-box pur. Si un modele NLI est disponible,
il remplace `_same_meaning` sans toucher au reste.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

from .metamorphic import jaccard


@dataclass(frozen=True)
class EntropyResult:
    """Resultat d'une mesure d'entropie semantique."""

    entropy: float            # entropie de Shannon normalisee sur [0, 1]
    clusters: int
    samples: int
    dominant_share: float     # part du cluster majoritaire
    risk: str                 # faible | moyen | eleve

    @property
    def confident(self) -> bool:
        return self.risk == "faible"


def semantic_entropy(
    answers: Sequence[str],
    *,
    threshold: float = 0.6,
) -> EntropyResult:
    """Calcule l'entropie semantique d'un ensemble de reponses."""
    cleaned = [a.strip() for a in answers if a and a.strip()]
    if not cleaned:
        return EntropyResult(entropy=1.0, clusters=0, samples=0,
                             dominant_share=0.0, risk="eleve")

    # Clustering agglomeratif glouton par equivalence de sens.
    clusters: list[list[str]] = []
    for ans in cleaned:
        for cluster in clusters:
            if _same_meaning(ans, cluster[0], threshold):
                cluster.append(ans)
                break
        else:
            clusters.append([ans])

    total = len(cleaned)
    probs = [len(c) / total for c in clusters]
    raw = -sum(p * math.log(p + 1e-12) for p in probs)
    normalised = raw / math.log(total) if total > 1 else 0.0
    dominant = max(probs)

    if normalised < 0.35:
        risk = "faible"
    elif normalised < 0.75:
        risk = "moyen"
    else:
        risk = "eleve"

    return EntropyResult(
        entropy=round(normalised, 4),
        clusters=len(clusters),
        samples=total,
        dominant_share=round(dominant, 4),
        risk=risk,
    )


def _same_meaning(a: str, b: str, threshold: float) -> bool:
    """Equivalence de sens approximative (entailment bidirectionnel lexical)."""
    return jaccard(a, b) >= threshold or _numeric_equal(a, b)


def _numeric_equal(a: str, b: str) -> bool:
    """Deux affirmations numeriquement identiques sont le meme sens."""
    import re

    na = re.findall(r"-?\d+(?:[.,]\d+)?", a.replace(",", "."))
    nb = re.findall(r"-?\d+(?:[.,]\d+)?", b.replace(",", "."))
    if not na or not nb:
        return False
    return sorted(float(x) for x in na) == sorted(float(y) for y in nb) and jaccard(a, b) > 0.25


def sample_and_measure(
    prompt: str,
    answer_fn: Callable[[str], str],
    k: int = 5,
) -> EntropyResult:
    """Echantillonne K fois puis mesure. Utilitaire direct."""
    answers: list[str] = []
    for i in range(max(1, k)):
        try:
            answers.append(answer_fn(prompt if i == 0 else f"{prompt}\n[variante {i + 1}]"))
        except Exception:  # noqa: BLE001
            continue
    return semantic_entropy(answers)


__all__ = ["EntropyResult", "semantic_entropy", "sample_and_measure"]
