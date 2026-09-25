"""Bibliotheque de temoins : une traduction VALIDEE devient une capacite durable.

LE PROBLEME QUE CE MODULE RESOUT, mesure. Traduire les regles d'une mission en
tests executables marche… quand le modele lit bien les regles. Au banc, sans
aucun oracle : fidelite 100 % -> 5/5 livraisons justes ; fidelite 0 % -> 0/5, que
des abstentions. Autrement dit, a chaque nouvelle mission, on repaye le meme pari
sur la meme competence du meme modele, alors que la mission peut etre EXACTEMENT
la meme que la precedente.

CE QU'IL FAIT. Une traduction qui a participe a une livraison PROUVEE est
conservee, indexee par l'objectif et par l'enonce de chaque regle. La prochaine
mission identique ne demande plus rien au modele : elle reprend les temoins deja
valides. Cout de la traduction : UN appel, ramene a ZERO.

CE QUI ENTRE DANS LA BIBLIOTHEQUE, ET CE QUI N'Y ENTRE PAS — c'est tout le sujet.
Une entree n'est acceptee que si :

  * la mission s'est terminee en ``DELIVERED`` (pas sous reserve, pas abstention) :
    l'artefact livre satisfaisait TOUTES les regles, temoins compris ;
  * les temoins venaient bien d'une traduction (jamais d'un oracle fourni : on ne
    recopie pas le banc dans une memoire) ;
  * l'empreinte de l'enonce de la regle accompagne le temoin : si la specification
    change d'un mot, l'entree ne s'applique plus.

Un temoin FAUX ne peut donc pas entrer par la porte d'une abstention ou d'une
reserve. Et s'il entre malgre tout (via une livraison fausse d'un tour precedent),
la reutilisation n'est pas aveugle : chaque entree est REVALIDEE a l'usage. Une
entree qui se met a echouer sur TOUS les candidats est retiree — elle accuse tout
le monde, donc elle ne discrimine personne — et la traduction redevient la source.

Le journal est append-only, comme tout le reste : `retenir` ajoute, `retirer`
ajoute une revocation. Rien n'est reecrit, donc rien ne peut etre reecrit en
silence.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from ..core.journal import Journal

__all__ = ["BibliothequeTemoins", "TemoinValide", "empreinte_objectif", "empreinte_regle"]

_MOT = re.compile(r"[a-z0-9_]{3,}")


def _empreinte(*parties: str) -> str:
    base = "|".join(" ".join(sorted(_MOT.findall(p.lower()))) for p in parties)
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def empreinte_objectif(objectif: str) -> str:
    """Empreinte de l'objectif : deux formulations equivalentes se reconnaissent.

    Volontairement independante de l'ordre des mots et de la ponctuation : une
    mission reformulee doit retrouver ses temoins, sinon la memoire ne servirait
    qu'a la repetition litterale — c'est-a-dire presque jamais.
    """
    return _empreinte(objectif)


def empreinte_regle(rule_id: str, enonce: str) -> str:
    """Empreinte d'une regle : identifiant + enonce. Un mot change, l'entree expire."""
    return _empreinte(rule_id, enonce)


@dataclass(frozen=True)
class TemoinValide:
    """Un temoin executable qui a participe a une livraison prouvee.

    Deux identifiants, et les confondre a ete un vrai bug : `regle` est le NOM de
    la regle (« R-001 »), `empreinte` est l'empreinte de son ENONCE. Le magasin est
    indexe par l'empreinte (une specification qui change d'un mot ne doit pas
    retrouver un temoin valide pour une autre), mais la revocation se demande par
    le NOM — c'est ce qu'un humain, un rapport ou un journal manipulent. La
    premiere version ne stockait que l'empreinte sous le nom `regle`, donc toute
    revocation par identifiant ne trouvait RIEN et echouait en silence.
    """

    objectif: str
    regle: str
    empreinte: str
    assertion: str
    mission_id: str = ""
    seq: int = 0

    def as_dict(self) -> dict[str, object]:
        return {
            "objectif": self.objectif,
            "regle": self.regle,
            "empreinte": self.empreinte,
            "assertion": self.assertion,
            "mission_id": self.mission_id,
            "seq": self.seq,
        }


@dataclass
class BibliothequeTemoins:
    """Mémoire append-only des temoins valides, avec revocation explicite."""

    path: Path | None = None
    journal: Journal | None = None
    _entrees: dict[tuple[str, str], TemoinValide] = field(default_factory=dict)
    #: Nombre de reutilisations servies depuis l'ouverture (mesure, pas estimation).
    servies: int = field(default=0, init=False)
    #: Nombre de revocations (temoins retires parce qu'ils accusaient tout le monde).
    revoquees: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self._entrees = {}
        self.servies = 0
        self.revoquees = 0
        if self.journal is None:
            # VERIFIE, pas seulement lu : une memoire dont le contenu decide des
            # verdicts ne peut pas venir d'un fichier que n'importe qui peut editer.
            self.journal = Journal.load_verified(self.path)
        for evenement in self.journal.events():
            if evenement.kind == "temoin-valide":
                entree = TemoinValide(
                    objectif=str(evenement.payload.get("objectif", "")),
                    regle=str(evenement.payload.get("regle", "")),
                    empreinte=str(evenement.payload.get("empreinte", "")),
                    assertion=str(evenement.payload.get("assertion", "")),
                    mission_id=str(evenement.payload.get("mission_id", "")),
                    seq=int(evenement.payload.get("seq", 0) or 0),
                )
                if entree.objectif and entree.empreinte and entree.assertion:
                    self._entrees[(entree.objectif, entree.empreinte)] = entree
            elif evenement.kind == "temoin-revoque":
                cle = (str(evenement.payload.get("objectif", "")),
                       str(evenement.payload.get("empreinte", "")))
                self._entrees.pop(cle, None)

    # -- ecriture ----------------------------------------------------------- #

    def retenir(
        self,
        *,
        objectif: str,
        empreintes: Mapping[str, str],
        correspondance: Mapping[str, str],
        mission_id: str = "",
    ) -> int:
        """Conserve une traduction validee. Rend le nombre d'entrees retenues.

        `correspondance` associe un nom de regle a son assertion ; `empreintes`
        associe le meme nom a l'empreinte de son ENONCE. L'enonce en clair n'est
        jamais stocke : il change d'une mission a l'autre sans que le sens change.
        """
        empreinte_obj = empreinte_objectif(objectif)
        gardees = 0
        for regle, assertion in correspondance.items():
            empreinte = empreintes.get(regle)
            if not empreinte or not assertion.strip():
                continue
            entree = TemoinValide(
                objectif=empreinte_obj, regle=regle, empreinte=empreinte,
                assertion=assertion, mission_id=mission_id, seq=len(self._entrees),
            )
            self._entrees[(empreinte_obj, empreinte)] = entree
            self.journal.append("temoin-valide", entree.as_dict())
            gardees += 1
        return gardees

    def retirer(self, *, objectif: str, regle: str, raison: str) -> bool:
        """Revoque une entree, designee par son NOM de regle. Rien n'est efface.

        Un temoin qui se met a echouer sur tous les candidats accuse tout le monde :
        il ne discrimine plus rien. On ne peut pas decider qui, de lui ou de tous
        les candidats, se trompe — donc on ne l'utilise plus, et on re-traduit. La
        revocation s'AJOUTE au journal : elle ne reecrit rien.
        """
        empreinte_obj = empreinte_objectif(objectif)
        a_retirer = [cle for cle, entree in self._entrees.items()
                     if cle[0] == empreinte_obj and entree.regle == regle]
        if not a_retirer:
            return False
        for cle in a_retirer:
            self._entrees.pop(cle, None)
            self.revoquees += 1
            self.journal.append(
                "temoin-revoque",
                {"objectif": cle[0], "empreinte": cle[1], "regle": regle,
                 "raison": raison[:300]},
            )
        return True

    # -- lecture ------------------------------------------------------------ #

    def rappeler(self, objectif: str, empreintes: Mapping[str, str]) -> dict[str, str]:
        """Rend les temoins connus pour cette mission et ces regles exactes.

        `empreintes` associe un nom de regle a l'empreinte de son enonce. Une regle
        absente, ou dont l'enonce a change, ne retrouve rien : c'est le but.
        """
        empreinte_obj = empreinte_objectif(objectif)
        out: dict[str, str] = {}
        for regle, empreinte in empreintes.items():
            entree = self._entrees.get((empreinte_obj, empreinte))
            if entree is not None:
                out[regle] = entree.assertion
        if out:
            self.servies += len(out)
        return out

    def connait(self, objectif: str, regle: str) -> bool:
        empreinte_obj = empreinte_objectif(objectif)
        return any(cle[0] == empreinte_obj and entree.regle == regle
                   for cle, entree in self._entrees.items())

    @property
    def size(self) -> int:
        return len(self._entrees)

    @property
    def notices(self) -> list[str]:
        """Ce que le chargement a eu a signaler — notamment une chaine cassee.

        Un fichier de memoire falsifie est mis en quarantaine par le journal
        (renomme, jamais supprime) et une chaine neuve commence. C'est le bon
        comportement fail-closed, mais il ne doit pas etre SILENCIEUX : perdre sa
        memoire sans le savoir est exactement ce que ce projet refuse.
        """
        return list(getattr(self.journal, "notices", []))

    def resume(self) -> str:
        base = (
            f"bibliotheque de temoins : {len(self._entrees)} entree(s) validee(s), "
            f"{self.servies} reutilisation(s), {self.revoquees} revocation(s)"
        )
        if self.notices:
            base += " | " + " ; ".join(self.notices)
        return base
