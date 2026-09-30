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
import re
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ..core.types import canonical
from .base import Completion, Message

_WARNING_MARKER = "PAST FAILURES ON SIMILAR TASKS"
_FEEDBACK_MARKER = "PREVIOUS ATTEMPT FAILED"

#: Les blocs que JIO INJECTE dans le prompt (memoire, retour d'echec). Ils sont ajoutes
#: APRES la demande, et `_demande` s'arrete au premier d'entre eux.
_MARQUEURS_INJECTES = (_WARNING_MARKER, _FEEDBACK_MARKER)

#: Un identifiant technique : nom entre accents graves (`sum_even(nums)`) ou jeton
#: snake_case. C'est le token le plus DISCRIMINANT d'une demande — l'equivalent d'un IDF
#: eleve dans BM25 — donc celui sur lequel on decide si un souvenir concerne la tache.
_IDENT = re.compile(r"`([^`]+)`|\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b", re.IGNORECASE)
_MOT = re.compile(r"[a-zA-ZÀ-ÿ]{5,}")


def _demande(prompt: str) -> str:
    """La partie du prompt qui EST la demande, avant tout bloc injecte.

    Sans cette restriction, un souvenir rappele peut RE-DESIGNER la tache : `_key` cherche
    la plus longue cle du banc presente dans le texte, et le bloc de memoire contient
    l'objectif d'une autre tache. Mesure du risque : la banque indexe chaque tache par son
    objectif ENTIER (161 caracteres pour `sum_even`) ; un souvenir portant un objectif plus
    long que celui de la tache courante ferait repondre le modele a la mauvaise question.
    """
    fin = len(prompt)
    for marque in _MARQUEURS_INJECTES:
        at = prompt.find(marque)
        if at >= 0:
            fin = min(fin, at)
    return prompt[:fin]


def _identifiants(texte: str) -> set[str]:
    """Noms techniques cites : `sum_even(nums)` -> {sum_even, nums} ; snake_case aussi."""
    trouves: set[str] = set()
    for entre_graves, snake in _IDENT.findall(texte):
        morceau = entre_graves or snake
        if entre_graves:
            # `sum_even(nums)` : on garde le nom ET ses arguments — les deux sont cites.
            trouves.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", morceau))
        else:
            trouves.add(morceau)
    return {t.lower() for t in trouves if len(t) > 2}


def _mots(texte: str) -> set[str]:
    """Mots de prose assez longs pour porter du sens (repli sans identifiant technique)."""
    return {m.lower() for m in _MOT.findall(texte)}


def _recouvrement(bloc: str, cle: str) -> float:
    """Part des identifiants de la cle presents dans le bloc (1.0 si la cle n'en a aucun)."""
    ids_cle = _identifiants(cle)
    if not ids_cle:
        return 1.0
    return len(ids_cle & _identifiants(bloc)) / len(ids_cle)


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
      2. il parle de CETTE tache — mesure sur les IDENTIFIANTS techniques.

    La premiere version cherchait le mot-cle n'importe ou dans le prompt. Or l'objectif
    contient toujours le nom de la tache : la condition etait donc toujours vraie, et
    l'avertissement se declenchait meme quand le souvenir parlait d'une autre tache.

    La deuxieme version exigeait que la cle de tache soit une SOUS-CHAINE du bloc. Elle
    etait fausse pour une raison invisible : la banque indexe chaque tache par son objectif
    ENTIER (jusqu'a 161 caracteres) alors que le bloc de memoire borne ce qu'il cite. La
    condition ne pouvait donc etre satisfaite que par accident — mesure : 0 avertissement
    accorde sur 48 appels, avec le bloc PRESENT dans 31 d'entre eux.

    Comparer les identifiants est robuste a cette troncature, et c'est aussi le bon critere
    sur le fond : un nom technique (`sum_even`) distingue les taches, la prose ne les
    distingue pas. Quand la demande n'a aucun identifiant (une tache de prose), on retombe
    sur un recouvrement de mots STRICT, pour ne pas armer sur deux mots generiques.
    """
    marker_at = prompt.find(_WARNING_MARKER)
    if marker_at < 0 or not task_key:
        return False
    bloc = prompt[marker_at:]
    ids = _identifiants(task_key)
    if ids:
        return bool(ids & _identifiants(bloc))
    mots = _mots(task_key)
    communs = mots & _mots(bloc)
    return len(communs) >= max(3, len(mots) // 2)


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
    #: Nombre d'appels ou l'avertissement de memoire a REELLEMENT ete accorde. Sans ce
    #: compteur, un ecart nul est ambigu : « le levier ne sert a rien » et « le levier n'a
    #: jamais ete arme » se lisent pareil. Le premier condamne un mecanisme, le second dit
    #: qu'on ne l'a pas encore essaye.
    warned_calls: int = 0
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
        # La tache est identifiee sur la DEMANDE seule : un bloc de memoire injecte ne doit
        # jamais pouvoir re-designera la question a laquelle le modele repond (voir _demande).
        key = self._key(_demande(prompt))

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
            self.warned_calls += 1
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
