"""Artefacts natifs : une doctrine, tous les dialectes d'agents."""

from __future__ import annotations

from .definitions import AGENTS, PRINCIPLES, SKILLS, AgentSpec, SkillSpec
from .emit import TARGETS, manifest, write_manifest

__all__ = [
    "AGENTS",
    "SKILLS",
    "PRINCIPLES",
    "AgentSpec",
    "SkillSpec",
    "TARGETS",
    "manifest",
    "write_manifest",
]
