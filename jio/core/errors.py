"""Exceptions JIO."""

from __future__ import annotations


class JioError(Exception):
    """Base de toutes les erreurs JIO."""


class FailClosed(JioError):
    """Le systeme refuse de poursuivre faute de preuve suffisante.

    C'est un comportement VOULU, pas un bug : mieux vaut une abstention
    explicite qu'une livraison douteuse.
    """


class BudgetExhausted(JioError):
    """Budget d'iteration, de tokens ou de temps epuise."""


class OscillationDetected(JioError):
    """La boucle alterne entre deux etats sans progresser.

    La litterature (arXiv 2606.27409) montre qu'une correction trop forte
    ou trop retardee destabilise la boucle par un mode oscillatoire.
    On escalade au lieu de boucler indefiniment.
    """


class IntegrityViolation(JioError):
    """Un exploit a ete detecte dans le journal. Arret immediat."""


class ProviderError(JioError):
    """Echec d'un fournisseur de modele."""


class QuorumNotReached(JioError):
    """Aucun consensus atteint. On escalade, on ne moyenne JAMAIS."""
