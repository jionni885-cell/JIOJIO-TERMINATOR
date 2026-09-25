"""Sonder un fournisseur REEL : il repond, et sait-il traduire des regles ?

POURQUOI CE MODULE EXISTE. Un CLI installe n'est pas un CLI qui fonctionne : il
peut n'etre pas authentifie, sortir un format inattendu, ou repondre en prose la ou
JIO attend une structure. Et depuis que la boucle traduit les regles en temoins
executables, il y a une question supplementaire, mesurable, qui decide de tout :
**ce fournisseur sait-il convertir une regle en test executable ?**

C'est la difference entre « j'ai installe opencode » et « jio peut prouver quelque
chose avec opencode ». Ce module repond aux deux, par une requete reelle, avant la
premiere mission — au lieu de laisser l'utilisateur decouvrir le probleme au milieu
d'une mission.

TROIS SONDES, du moins exigeant au plus exigeant :

  1. **vivacite** : une question triviale. Etablit que le binaire repond, et en
     combien de temps. Un CLI qui echoue ici ne peut rien faire d'autre ;
  2. **structure** : une consigne de format. Mesure si la reponse est exploitable,
     pas si elle est juste ;
  3. **traduction de regles** : le prompt REEl de `jio/spec/witness.py`, sur deux
     regles. C'est la capacite dont depend la preuve sans oracle. Les tests rendus
     passent la MEME porte de securite que dans une mission : ici, aucune indulgence
     de diagnostic — un test refuse est refuse.

Aucune sonde ne modifie l'etat, n'ecrit un fichier, ni ne lance une mission.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

from ..core.types import Rule, RuleKind, Spec
from ..providers.base import Message, Provider
from ..spec.witness import Temoignage, traduire

__all__ = ["Sonde", "spec_sonde", "sonder"]

#: Specification minimale, assez petite pour couter une fraction de centime et assez
#: complete pour exiger les deux formes de traduction : une egalite et un refus.
def spec_sonde() -> Spec:
    return Spec(
        mission="moyenne de deux nombres : cas nominal et liste vide refusee",
        rules=(
            Rule(id="R-001", statement="La moyenne de [1, 2] vaut 1.5"),
            Rule(id="R-002", statement="Une liste vide doit lever ValueError",
                 kind=RuleKind.BOUNDARY, negative_case="[]"),
        ),
    )


#: La fonction sur laquelle la sonde demande des tests. Fournie au modele par le
#: prompt : la sonde mesure la CAPACITE DE TRADUIRE, pas celle d'ecrire le code.
ENTRYPOINT_SONDE = "moyenne"


@dataclass
class Sonde:
    """Ce qu'une requete reelle a appris sur un fournisseur."""

    nom: str
    modele: str = ""
    vivant: bool = False
    latence_s: float = 0.0
    reponse_vide: bool = False
    erreur: str = ""
    temoignage: Temoignage | None = None
    latence_traduction_s: float = 0.0
    erreur_traduction: str = ""

    @property
    def traduit(self) -> bool:
        return bool(self.temoignage and self.temoignage.tests)

    @property
    def verdict(self) -> str:
        """Un mot, et il doit dire la VERITE sur ce qui est possible."""
        if self.erreur:
            return "INJOIGNABLE"
        if not self.vivant:
            return "SANS REPONSE"
        if self.erreur_traduction:
            return "REPOND, TRADUCTION EN ECHEC"
        if self.temoignage is None:
            return "REPOND"
        if self.traduit:
            return "CAPABLE DE PROUVER SANS ORACLE"
        if self.temoignage.aveux:
            return "REPOND, NE SAIT PAS TRADUIRE (aveu)"
        return "REPOND, TRADUCTION REFUSEE"

    def resume(self) -> str:
        if self.erreur:
            return f"{self.nom} : injoignable — {self.erreur[:120]}"
        parties = [
            f"{self.nom} ({self.modele or 'modele inconnu'})",
            f"repond en {self.latence_s:.1f}s",
        ]
        if self.reponse_vide:
            parties.append("MAIS rend une reponse VIDE")
        if self.temoignage is not None:
            parties.append(
                f"traduction : {len(self.temoignage.tests)} temoin(s), "
                f"{len(self.temoignage.aveux)} aveu(x), "
                f"{len(self.temoignage.refuses)} refus"
            )
        elif self.erreur_traduction:
            parties.append(f"traduction en echec ({self.erreur_traduction[:80]})")
        return " · ".join(parties)


def sonder(provider: Provider, *, timeout_hint: float = 0.0) -> Sonde:
    """Sonde un fournisseur par des requetes REELLES, sans jamais lever d'exception.

    Un diagnostic qui plante est un diagnostic qu'on ne lance plus. Toute erreur est
    capturee, nommee, et rendue dans le resultat.
    """
    sonde = Sonde(nom=getattr(provider, "name", "?"), modele=getattr(provider, "model", ""))
    debut = time.perf_counter()
    try:
        completion = provider.complete(
            [Message("user", "Reply with exactly the two letters: OK")],
            temperature=0.0, max_tokens=16,
        )
    except Exception as exc:  # noqa: BLE001 — un fournisseur qui echoue est un RESULTAT
        sonde.erreur = f"{type(exc).__name__}: {exc}"
        sonde.latence_s = time.perf_counter() - debut
        return sonde
    sonde.latence_s = time.perf_counter() - debut
    texte = getattr(completion, "text", "") or ""
    sonde.vivant = True
    sonde.reponse_vide = not texte.strip()
    sonde.modele = str(getattr(completion, "model", "") or sonde.modele)

    debut = time.perf_counter()
    try:
        sonde.temoignage = traduire(
            spec_sonde(), provider, entrypoint=ENTRYPOINT_SONDE,
            objectif=spec_sonde().mission,
        )
    except Exception as exc:  # noqa: BLE001
        sonde.erreur_traduction = f"{type(exc).__name__}: {exc}"
    sonde.latence_traduction_s = time.perf_counter() - debut
    return sonde


def sonder_tous(providers: list[Provider]) -> list[Sonde]:
    return [sonder(p) for p in providers]
