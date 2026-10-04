"""Apprentissage : ne jamais repayer deux fois la meme erreur."""

from __future__ import annotations

from .memory import FailureMemory, FailureRecord, fingerprint

__all__ = ["FailureMemory", "FailureRecord", "fingerprint"]
