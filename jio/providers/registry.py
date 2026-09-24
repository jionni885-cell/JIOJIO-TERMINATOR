"""Registre de fournisseurs + resolution depuis l'environnement.

Aucun fournisseur n'est obligatoire. Si rien n'est configure, on retombe
sur la simulation deterministe : le systeme reste utilisable et testable.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from .base import Provider
from .cli import CliProvider

# Binaires externes connus, avec leur syntaxe non interactive.
KNOWN_CLIS: dict[str, dict[str, str]] = {
    "opencode": {"argv": "{binary} run {prompt}", "model": "opencode/default"},
    "hermes": {"argv": "{binary} chat -q {prompt}", "model": "hermes/default"},
    "claude": {"argv": "{binary} -p {prompt}", "model": "claude/default"},
    "codex": {"argv": "{binary} exec {prompt}", "model": "codex/default"},
    "gemini": {"argv": "{binary} -p {prompt}", "model": "gemini/default"},
    "aider": {"argv": "{binary} --message {prompt} --yes", "model": "aider/default"},
}


@dataclass
class Registry:
    """Resout les fournisseurs par nom ou par capacite."""

    providers: dict[str, Provider] = field(default_factory=dict)

    def add(self, provider: Provider) -> None:
        self.providers[provider.name] = provider

    def get(self, name: str) -> Provider:
        if name not in self.providers:
            raise KeyError(f"fournisseur inconnu : {name!r} (connus : {sorted(self.providers)})")
        return self.providers[name]

    def names(self) -> list[str]:
        return sorted(self.providers)

    def __iter__(self) -> Iterable[Provider]:
        return iter(self.providers.values())


def detect_clis(candidates: Sequence[str] | None = None) -> list[CliProvider]:
    """Detecte les CLI externes reellement installes sur la machine."""
    found: list[CliProvider] = []
    for name in candidates or list(KNOWN_CLIS):
        spec = KNOWN_CLIS.get(name)
        if spec is None:
            continue
        prov = CliProvider(
            binary=name,
            argv_template=spec["argv"],
            name=f"cli::{name}",
            model=spec["model"],
        )
        if prov.available():
            found.append(prov)
    return found


def from_env() -> Registry:
    """Construit un registre a partir de l'environnement.

    Variables reconnues (toutes optionnelles) :
      * ``JIO_OPENAI_BASE``  + ``JIO_OPENAI_KEY``  + ``JIO_OPENAI_MODEL``
      * ``OPENROUTER_API_KEY`` / ``OPENAI_API_KEY`` / ``ANTHROPIC_API_KEY``
      * ``JIO_OLLAMA``  (ex. ``http://localhost:11434``)
    """
    reg = Registry()
    for prov in detect_clis():
        reg.add(prov)

    base = os.environ.get("JIO_OPENAI_BASE") or os.environ.get("JIO_OLLAMA")
    key = os.environ.get("JIO_OPENAI_KEY") or _first_key()
    if base:
        from .openai_compat import OpenAiCompatProvider

        reg.add(
            OpenAiCompatProvider(
                base_url=base,
                api_key=key or "",
                model=os.environ.get("JIO_OPENAI_MODEL", "gpt-4o-mini"),
                name="api",
            )
        )
    return reg


def _first_key() -> str | None:
    for var in ("OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "DEEPSEEK_API_KEY"):
        val = os.environ.get(var)
        if val:
            return val
    return None


def make_providers(specs: Sequence[str]) -> list[Provider]:
    """Resout une liste de noms de fournisseurs (utile pour les tests et la CLI)."""
    reg = from_env()
    out: list[Provider] = []
    for spec in specs:
        try:
            out.append(reg.get(spec))
        except KeyError as exc:  # pragma: no cover
            raise SystemExit(str(exc)) from exc
    return out


__all__ = ["Registry", "KNOWN_CLIS", "detect_clis", "from_env", "make_providers"]
