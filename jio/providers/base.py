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


#: Plafond de texte accepte d'un modele : 4 millions de caracteres (~1 M jetons). Au-dela,
#: on tronque ET on le dit. Une reponse de modele n'a pas a etre lue sans limite : un modele
#: qui part en boucle, ou un serveur hostile, remplirait sinon la memoire du processus avant
#: qu'on puisse reagir — et `capture_output=True` lit tout avant de rendre la main.
MAX_REPONSE = 4_000_000


def extraire_texte(valeur: object) -> str:
    """Le texte utile d'un champ `content`, quelle que soit sa FORME.

    Les API de modeles renvoient deux formes, et la seconde cassait tout :

      * `"content": "du texte"` — la forme classique ;
      * `"content": [{"type": "text", "text": "du texte"}, ...]` — la forme par BLOCS,
        desormais courante.

    La seconde etait passee telle quelle dans `Completion(text=...)` : `text` devenait une
    LISTE. En aval, le premier `re.search` sur ce texte levait un `AttributeError` — un
    plantage la ou le systeme doit s'abstenir. Le type declare (`str`) n'etait verifie nulle
    part : c'est le genre de contrat non controle qui ne se voit qu'en production.

    Les blocs non-texte (images, appels d'outil) sont ignores : ils ne portent pas de
    reponse a la question posee. Un bloc `content` imbrique est lu aussi, par prudence.
    """
    if isinstance(valeur, str):
        return valeur
    if isinstance(valeur, list):
        morceaux: list[str] = []
        for bloc in valeur:
            if isinstance(bloc, str):
                morceaux.append(bloc)
            elif isinstance(bloc, dict):
                texte = bloc.get("text")
                if isinstance(texte, str):
                    morceaux.append(texte)
                elif isinstance(bloc.get("content"), str):
                    morceaux.append(bloc["content"])
        return "\n".join(morceaux)
    if valeur is None:
        return ""
    if isinstance(valeur, (int, float, bool)):
        return str(valeur)
    return ""


def borner(texte: str) -> tuple[str, bool]:
    """Tronque au plafond. Rend `(texte, tronque)` — jamais une troncature silencieuse."""
    if len(texte) <= MAX_REPONSE:
        return texte, False
    return texte[:MAX_REPONSE], True


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
