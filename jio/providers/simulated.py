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

_WARNING_MARKER = "PAST FAILURES ON SIMILAR TASKS"
_FEEDBACK_MARKER = "PREVIOUS ATTEMPT FAILED"


def _has_structured_feedback(prompt: str) -> bool:
    """Le prompt contient-il un retour d'echec structure (et non une plainte) ?

    On exige la marque ET la presence d'un identifiant de regle : « ca a rate »
    n'informe personne, « la regle R-003 attend 9 » informe.
    """
    at = prompt.find(_FEEDBACK_MARKER)
    if at < 0:
        return False
    block = prompt[at:]
    return "R-0" in block or "rule" in block.lower() or "regle" in block.lower()


def _warns_about(prompt: str, task_key: str) -> bool:
    """Le souvenir rappele concerne-t-il CETTE tache precisement ?

    Deux exigences, et la seconde est celle qui compte :

      1. un bloc de memoire est present dans le prompt ;
      2. il nomme la tache courante DANS LE BLOC LUI-MEME.

    La premiere version cherchait le mot-cle n'importe ou dans le prompt. Or
    l'objectif contient toujours le nom de la tache : la condition etait donc
    toujours vraie, et l'avertissement se declenchait meme quand le souvenir
    parlait d'une autre tache. Le « gain » mesure aurait alors ete du bruit
    presente comme un resultat — exactement ce que ce projet doit refuser.
    """
    marker_at = prompt.find(_WARNING_MARKER)
    if marker_at < 0 or not task_key:
        return False
    return task_key.lower() in prompt[marker_at:].lower()


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
    #: Gain RELATIF de competence lorsque le prompt contient l'avertissement
    #: precis issu de la memoire des echecs. MODELISE et declare (voir plus bas),
    #: mesurable isolement par `jio learn`.
    warning_gain: float = 0.15
    #: Gain RELATIF lorsqu'un RETOUR D'ECHEC structure est present. Modelise le
    #: levier le mieux documente du harness (+5 a +10 points sur des modeles dont
    #: la competence de base est d'environ 50-60 %, soit ~10-20 % relatifs).
    feedback_gain: float = 0.15

    def _amplify(self, effective: float, gain: float) -> float:
        """Applique un gain RELATIF, jamais un bonus additif.

        C'est l'invariant central du projet, et il doit etre encode dans le
        simulateur lui-meme : **un harness ne cree pas de connaissance, il
        amplifie celle qui existe**.

        La version additive etait fausse : elle faisait reussir un modele de
        competence 0.0 des qu'on lui donnait un retour d'erreur — c'est-a-dire un
        harness capable d'inventer du savoir absent. Un test verrouillait cet
        invariant et l'a detecte immediatement. Ici, competence 0.0 reste 0.0 :
        aucun avertissement ne peut sauver un modele qui ne sait pas.
        """
        if effective <= 0.0:
            return 0.0
        return min(1.0, effective * (1.0 + gain))

    # -- resolution de la tache -------------------------------------------- #

    def _key(self, text: str) -> str | None:
        """Trouve la tache visee par le prompt (la plus longue cle presente)."""
        matches = [k for k in self.bank if k and k in text]
        if not matches:
            return None
        return max(matches, key=len)

    def _seed(self, task_key: str, attempt_hint: str) -> int:
        """Graine de la DISPOSITION pour cette tentative.

        Volontairement PAS calculee sur le prompt entier. La version precedente
        hachait tout le texte du prompt : la consequence etait invisible mais
        devastatrice — ajouter un bloc de memoire, ou un retour d'echec, rebattait
        entierement le tirage. Tout effet au niveau du prompt devenait alors
        inattribuable, et un « gain » mesure n'etait qu'une loterie.

        Mesure du probleme, au banc a trois bras : un temoin SANS aucun effet
        (memoire presente, effet desactive) a produit +50 points d'ecart face au
        bras froid — alors que rien n'agissait. C'est le bruit a l'etat pur.

        Ce qu'un modele fait reellement : il a une disposition stable pour cette
        tache a cette tentative, et un prompt plus long ne le fait pas redevenir
        un autre modele. Les effets du prompt sont donc desormais DECLARES
        (retour d'echec, avertissement memoire) et donc mesurables separement.
        """
        blob = canonical([self.persona.name, self.persona.bias, task_key, attempt_hint])
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
        rng = random.Random(self._seed(key, hint))

        # Le biais diminue la competence effective — c'est ainsi qu'on modelise
        # les erreurs CORRELEES entre agents partageant le meme modele.
        effective = min(1.0, max(0.0, self.persona.skill - self.persona.bias))
        # La temperature aide un peu a sortir d'un mauvais pas (exploration).
        effective = min(1.0, effective + 0.05 * self.persona.temperature)

        # --- effet d'un AVERTISSEMENT issu de la memoire des echecs --------- #
        # C'est un MODELE explicite, pas une observation : un modele reel
        # n'apprend pas davantage parce qu'un fichier JSON a change. On modelise
        # ici le seul mecanisme revendique par la litterature (retour d'echec
        # structure : +5 a +10 points ; AHE : +7,3 points) : quand le contexte
        # contient l'echec precis deja rencontre, la competence effective monte.
        #
        # L'effet s'applique AVANT le tirage et modifie la probabilite elle-meme :
        # le gain mesure par `jio learn` n'est donc pas un artefact de graine,
        # contrairement a une simple reecriture du prompt.
        warned = _warns_about(prompt, key)
        if warned:
            effective = self._amplify(effective, self.warning_gain)

        # --- effet d'un RETOUR D'ECHEC structure --------------------------- #
        # Le levier le mieux documente du harness (+5 a +10 points). Comme le
        # precedent : un modele reel n'apprend pas d'un texte par magie, mais la
        # litterature mesure cet effet — on le MODELISE et on le declare, au lieu
        # de laisser le hasard produire une apparence de progres.
        informed = _has_structured_feedback(prompt)
        if informed:
            effective = self._amplify(effective, self.feedback_gain)

        if rng.random() < effective:
            text = correct
            meta = {"simulated": True, "sim_correct": True}
        else:
            text = distractors[rng.randrange(len(distractors))] if distractors else correct
            meta = {"simulated": True, "sim_correct": False}

        meta["effective_skill"] = round(effective, 4)
        meta["warned"] = warned
        meta["informed"] = informed
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
