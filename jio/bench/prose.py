"""Le banc de PROSE : une mission generaliste mesurable sans cle d'API.

POURQUOI CE MODULE
------------------
Le banc d'essai ne mesurait que du code. Or la demande est generaliste — rapports,
analyses, notes — et c'est exactement la ou un harness n'avait rien a dire : sans
oracle, il n'y avait qu'une abstention honnete. Mesurer la prose demande donc une
banque de DOCUMENTS, pas de programmes.

Le simulateur de `providers/simulated.py` est deja generique : il associe une cle de
tache a ``(reponse_correcte, distracteurs)`` et rend du TEXTE. Une banque de prose ne
demande donc aucun code nouveau cote fournisseur — seulement des documents.

CE QUI REND LA MESURE HONNETE
-----------------------------
* le document CORRECT ne contient que des affirmations vraies, et au moins une
  affirmation verifiable (sinon la regle de couverture le refuse, a raison) ;
* chaque DISTRACTEUR est le MEME document avec des affirmations FAUSSES, de sorte que
  la difference mesuree soit la verification, et rien d'autre ;
* les distracteurs portent les trois formes que la prose produit reellement : un
  calcul faux, un bloc annonce comme Python qui ne compile pas, et un chemin cite qui
  n'existe pas.

Le dernier cas est le plus important, et c'est celui qu'on rate en le traitant comme
les autres : un chemin introuvable est une RESERVE (`advisory`), jamais un rejet. Un
distracteur qui ne contient QUE cela ne doit pas etre presente comme un document
faux — il est signale, et le systeme le dit.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = ["PROSE_BY_ID", "PROSE_TASKS", "ProseTache", "prose_bank"]


@dataclass(frozen=True)
class ProseTache:
    """Une mission de document, avec sa reponse juste et ses distracteurs."""

    id: str
    objective: str
    sujet: str
    correct: str
    distractors: tuple[str, ...]

    def bank(self) -> Mapping[str, tuple[str, Sequence[str]]]:
        """La banque attendue par le simulateur : la CLE est le sujet du document."""
        return {self.sujet: (self.correct, list(self.distractors))}


_RAPPORT_CORRECT = """# Mesure du palier de latence

## Methode

Le protocole compare deux bras a budget egal, sur 400 requetes par bras. La latence
mediane du premier bras est de 12 + 30 = 42 ms ; celle du second est de 100/4 = 25 ms.

## Resultat

Le gain median atteint donc 7 x 6 = 42 ms, soit une reduction de 17 ms.

## Verification

La normalisation des chemins est faite par le module `jio/core/journal.py`, et le
calcul ci-dessus est reproductible :

```python
def gain(a, b):
    return a - b
```

## Limites

Deux bras seulement, et une seule machine : le resultat est un ordre de grandeur, pas
une loi. Aucun chiffre n'est avance pour les cas non mesures.
"""

_RAPPORT_CALCUL_FAUX = _RAPPORT_CORRECT.replace(
    "Le gain median atteint donc 7 x 6 = 42 ms",
    "Le gain median atteint donc 7 x 6 = 43 ms",
)

_RAPPORT_BLOC_CASSE = _RAPPORT_CORRECT.replace(
    """```python
def gain(a, b):
    return a - b
```""",
    """```python
def gain(a, b:
    return a - b
```""",
)

_RAPPORT_CHEMIN_FAUX = _RAPPORT_CORRECT.replace(
    "`jio/core/journal.py`", "`jio/core/journal_inexistant.py`"
)


PROSE_TASKS: tuple[ProseTache, ...] = (
    ProseTache(
        id="rapport_latence",
        sujet="palier de latence",
        objective=(
            "Redige le rapport de mesure du palier de latence : methode, resultat "
            "chiffre, verification et limites. Les chiffres annonces doivent etre "
            "exacts et recalculables."
        ),
        correct=_RAPPORT_CORRECT,
        distractors=(_RAPPORT_CALCUL_FAUX, _RAPPORT_BLOC_CASSE, _RAPPORT_CHEMIN_FAUX),
    ),
)

PROSE_BY_ID: Mapping[str, ProseTache] = {t.id: t for t in PROSE_TASKS}


def prose_bank(tache: ProseTache) -> Mapping[str, tuple[str, Sequence[str]]]:
    """La banque du simulateur pour cette tache."""
    return tache.bank()


# --------------------------------------------------------------------------- #
# Mesure
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class MesureProse:
    """Le resultat d'un bras de mesure, avec ce qui doit rester a zero."""

    essais: int
    aveugle: float          # un tirage, aucune verification
    aveugle_best_of: float  # meilleur d'un lot, choisi PAR L'ORACLE (borne haute)
    jio: float              # moteur complet, AUCUN oracle
    #: Documents FAUX livres SANS aucun signalement (statut DELIVERED). Le seul
    #: chiffre qui doit rester a zero dans tout le projet.
    erreurs_silencieuses: int
    #: Documents non corrects livres SOUS RESERVE : le signalement existe et il est
    #: nomme. Ce n'est pas un silence, c'est une livraison degradee et declaree.
    sous_reserve: int
    abstentions: int
    appels: float

    def resume(self, nom: str) -> str:
        return (
            f"    {nom:<38} {self.jio * 100:5.1f}%   "
            f"(aveugle {self.aveugle * 100:.1f}%, oracle best-of {self.aveugle_best_of * 100:.1f}%)"
            f"   SILENCIEUX : {self.erreurs_silencieuses}   sous reserve : "
            f"{self.sous_reserve}   abstention : {self.abstentions}   "
            f"appels {self.appels:.1f}"
        )


def mesurer_prose(
    *,
    skill: float,
    runs: int,
    tache_ids: Sequence[str] | None = None,
    max_rounds: int = 3,
    racine: Path | None = None,
) -> MesureProse:
    """Mesure le harness sur des DOCUMENTS : aveugle contre verifie.

    Trois precautions, sans lesquelles le chiffre ne vaut rien :

    1. la graine de la mission entre dans celle de chaque generation (`EngineConfig.seed`).
       Sans cela, tous les essais rejouaient le MEME tirage : verifie, et corrige ;
    2. le bras « aveugle » a le MEME budget d'appels, et il est aide par l'oracle cache.
       C'est donc une borne HAUTE du tirage seul — l'avantage donne au modele brut ;
    3. on compte separement les documents FAUX presentes comme prouves (`faux_livres`,
       qui doit valoir zero), les livraisons sous reserve nommee, et les abstentions.
    """
    from ..cli import _simulated_engine
    from ..core.types import Mission, MissionStatus
    from ..loop.engine import WorkItem
    from ..providers.base import Message
    from ..verify.prose_prover import spec_prose

    ids = list(tache_ids) if tache_ids else [t.id for t in PROSE_TASKS]
    justes = aveugle = best_of = silencieux = sous_reserve = abstentions = 0
    essais = appels = 0

    for tache in (PROSE_BY_ID[i] for i in ids):
        banque = prose_bank(tache)
        for seed in range(runs):
            essais += 1
            moteur = _simulated_engine(
                None, skill=skill, panel_size=5, seed=seed, max_rounds=max_rounds,
                famille="prose", banque=banque, racine=racine or Path.cwd(),
            )
            rapport = moteur.run(
                Mission(objective=tache.objective, id=f"{tache.id}-{seed}",
                        max_rounds=max_rounds),
                WorkItem(objective=tache.objective, spec=spec_prose(tache.objective)),
            )
            appels += int(rapport.usage.get("calls", 0))
            livre = (rapport.subject or "").strip()

            # Le bras aveugle a le MEME budget d'appels que le moteur : autant de
            # tirages, et il gagne si l'un d'eux tombe juste — aide par l'oracle
            # cache, qui n'existe pas dans une mission reelle. C'est donc une borne
            # HAUTE du modele brut, et c'est voulu : l'avantage va au concurrent.
            n_appels = max(1, int(rapport.usage.get("calls", 0) or 1))
            lot = [
                moteur.generators[i % len(moteur.generators)].complete(
                    [Message("user", tache.objective)], seed=1000 * seed + i,
                ).text.strip()
                for i in range(n_appels)
            ]
            aveugle += 1 if lot[0] == tache.correct.strip() else 0
            best_of += 1 if any(x == tache.correct.strip() for x in lot) else 0
            livre_juste = livre == tache.correct.strip()
            if livre_juste:
                justes += 1
            # STATUT, et pas seulement contenu : c'est la definition du banc de code,
            # et elle est plus severe. « Livre » veut dire livre SANS RIEN DIRE.
            # Un document non correct livre `DELIVERED_WITH_RESERVATION` n'est pas un
            # silence : le signalement existe et il est nomme.
            if rapport.status is MissionStatus.DELIVERED:
                if not livre_juste:
                    silencieux += 1
            elif rapport.status is MissionStatus.DELIVERED_WITH_RESERVATION:
                if not livre_juste:
                    sous_reserve += 1
            elif rapport.status in (MissionStatus.ABSTAINED, MissionStatus.FAILED):
                abstentions += 1

    return MesureProse(
        essais=essais,
        aveugle=aveugle / max(1, essais),
        aveugle_best_of=best_of / max(1, essais),
        jio=justes / max(1, essais),
        erreurs_silencieuses=silencieux,
        sous_reserve=sous_reserve,
        abstentions=abstentions,
        appels=appels / max(1, essais),
    )
