"""Interface des fournisseurs de modeles.

Le systeme ne connait qu'un contrat : `complete(messages) -> Completion`.
Tout le reste (API, CLI externe, simulation) est un adaptateur remplacable.

Point cle : un fournisseur ne voit **jamais** de donnees marquees SYSTEM
mélangees avec du contenu EXTERNAL. La separation est structurelle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Protocol, Sequence, runtime_checkable

from ..core.types import TrustLevel


@dataclass(frozen=True)
class Message:
    """Un message adresse a un modele, avec son niveau de confiance."""

    role: str                       # system | user | assistant
    content: str
    trust: TrustLevel = TrustLevel.USER

    def __post_init__(self) -> None:
        if self.role not in {"system", "user", "assistant"}:
            raise ValueError(f"role invalide: {self.role!r}")


@dataclass(frozen=True)
class Completion:
    """Reponse d'un modele."""

    text: str
    model: str = "unknown"
    provider: str = "unknown"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    stop_reason: str = "stop"
    metadata: Mapping[str, object] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class ProviderError(RuntimeError):
    """Echec d'appel au modele."""


@runtime_checkable
class Provider(Protocol):
    """Contrat minimal d'un fournisseur."""

    name: str
    model: str

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        seed: int | None = None,
    ) -> Completion:  # pragma: no cover - protocole
        ...


def render(messages: Sequence[Message]) -> str:
    """Rend une conversation en texte unique (utile pour les CLI externes)."""
    return "\n\n".join(f"<{m.role}>\n{m.content}\n</{m.role}>" for m in messages)


__all__ = ["Message", "Completion", "Provider", "ProviderError", "render"]
