"""Fournisseur simule deterministe.

Objectif : **pouvoir tester et mesurer tout le systeme sans aucune cle API.**

Ce n'est pas un faux fournisseur qui repond n'importe quoi. Il modelise un
modele reel par un **niveau de competence** `skill` : a chaque tirage il produit
la bonne reponse avec probabilite `skill`, sinon une reponse fausse *plausible*.

Le tirage est deterministe : `seed = hash(prompt + tentative + agent)`.
Deux executions identiques donnent exactement le meme resultat — condition
necessaire pour rejouer les journaux et detecter les exploits.

Consequence importante : la **verification**, elle, est totalement reelle.
Le code produit est vraiment execute contre de vrais tests caches.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..core.types import canonical
from .base import Completion, Message


@dataclass
class Persona:
    """Un modele simule : nom, competence, biais."""

    name: str
    skill: float = 0.35
    temperature: float = 0.0
    bias: float = 0.0  # decalage systematique (erreurs correlees entre agents "identiques")


@dataclass
class SimulatedProvider:
    """Provider deterministe pilote par un banc de taches.

    `bank` associe une cle de tache a ``(reponse_correcte, distracteurs)``.
    """

    name: str = "simulated"
    model: str = "sim-1"
    persona: Persona = field(default_factory=Persona)
    bank: Mapping[str, tuple[str, Sequence[str]]] = field(default_factory=dict)
    calls: int = 0

    # -- resolution de la tache -------------------------------------------- #

    def _key(self, text: str) -> str | None:
        """Trouve la tache visee par le prompt (la plus longue cle presente)."""
        matches = [k for k in self.bank if k and k in text]
        if not matches:
            return None
        return max(matches, key=len)

    def _seed(self, text: str, attempt_hint: str) -> int:
        blob = canonical([self.persona.name, self.persona.bias, text, attempt_hint])
        return int(hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:16], 16)

    # -- contrat ------------------------------------------------------------ #

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        seed: int | None = None,
    ) -> Completion:
        self.calls += 1
        prompt = "\n".join(m.content for m in messages)
        key = self._key(prompt)

        if key is None:
            return Completion(
                text="",
                model=self.model,
                provider=self.name,
                stop_reason="no_task",
                metadata={"simulated": True, "no_task": True},
            )

        correct, distractors = self.bank[key]
        hint = str(seed) if seed is not None else prompt[-256:]
        rng = random.Random(self._seed(prompt, hint))

        # Le biais diminue la competence effective — c'est ainsi qu'on modelise
        # les erreurs CORRELEES entre agents partageant le meme modele.
        effective = min(1.0, max(0.0, self.persona.skill - self.persona.bias))
        # La temperature aide un peu a sortir d'un mauvais pas (exploration).
        effective = min(1.0, effective + 0.05 * self.persona.temperature)

        if rng.random() < effective:
            text = correct
            meta = {"simulated": True, "sim_correct": True}
        else:
            text = distractors[rng.randrange(len(distractors))] if distractors else correct
            meta = {"simulated": True, "sim_correct": False}

        meta["effective_skill"] = round(effective, 4)
        return Completion(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            metadata=meta,
        )


def make_panel(
    names: Sequence[str],
    skill: float,
    bank: Mapping[str, tuple[str, Sequence[str]]],
    *,
    correlated: bool = False,
) -> list[SimulatedProvider]:
    """Construit un panel d'agents simules.

    Si `correlated=True`, tous partagent le meme biais : c'est le cas
    « meme modele partout » qui produit des erreurs correlees — et que le
    systeme doit REFUSER comme preuve de consensus.
    """
    providers: list[SimulatedProvider] = []
    for i, n in enumerate(names):
        bias = 0.15 if correlated else 0.0
        providers.append(
            SimulatedProvider(
                name=f"sim::{n}",
                model="sim-1",
                persona=Persona(name=n, skill=skill, bias=bias),
                bank=bank,
            )
        )
    return providers


__all__ = ["Persona", "SimulatedProvider", "make_panel"]
