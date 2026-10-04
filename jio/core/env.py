"""Lecture des reglages par variables d'environnement — un seul endroit.

Pourquoi ce module existe
-------------------------
Audit mesure du projet : sur les **17 variables documentees dans `.env.example`,
11 n'etaient lues NULLE PART**. La documentation promettait des reglages qui
n'existaient pas. C'est pire qu'une absence de documentation : l'utilisateur croit
regler le systeme et ne regle rien.

Deux reponses possibles : cabler, ou supprimer. On cable ce qui a deja un
parametre reel derriere (couteau zero machinerie), on supprime le reste, et un
test verifie que la documentation et le code ne peuvent plus diverger.

Regle : une valeur absente ou illisible retombe sur la valeur par defaut du
programme. Un environnement casse ne doit pas empecher l'execution.
"""

from __future__ import annotations

import os

__all__ = ["bool_env", "float_env", "int_env", "str_env"]


def str_env(name: str, default: str = "") -> str:
    value = os.environ.get(name, "").strip()
    return value or default


def int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def bool_env(name: str, default: bool) -> bool:
    """Vrai pour `1`, `true`, `yes`, `on` — faux pour `0`, `false`, `no`, `off`."""
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default
