"""Choisir les competences a charger : mesure, pas menu.

Le depot livre une bibliotheque de competences Hermes ; ce paquet repond a la question qui rend
cette bibliotheque utile — « pour CET objectif, lesquelles, et pourquoi ? » — et la mesure sur un
banc annote, temoins compris.
"""

from __future__ import annotations

from .banc import (
    BANC,
    ObjectifAnnote,
    Rapport,
    balayer_seuils,
    comparer,
    meilleur_seuil,
    mesurer,
)
from .router import (
    POIDS_CORPS,
    SEUIL_CONCEPTS,
    Catalogue,
    Choix,
    catalogue_du_depot,
    choisir,
    cout,
    jetons,
    proches,
    stem,
)

__all__ = [
    "BANC",
    "POIDS_CORPS",
    "SEUIL_CONCEPTS",
    "Catalogue",
    "Choix",
    "ObjectifAnnote",
    "Rapport",
    "balayer_seuils",
    "catalogue_du_depot",
    "choisir",
    "comparer",
    "cout",
    "jetons",
    "meilleur_seuil",
    "mesurer",
    "proches",
    "stem",
]
