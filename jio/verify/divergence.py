"""Comparaison differentielle des candidats — l'ambiguite ne doit pas etre silencieuse.

Le trou, mesure
---------------
Quand plusieurs candidats satisfont la specification, le moteur garde celui qui a le
meilleur ratio de preuves — et, a EGALITE, **le dernier arrive** (`_better` accepte tout
candidat dont le ratio est superieur OU egal). Le choix ne depend donc que de l'ordre de
generation : mesure sur un cas reel, avec un candidat juste et un candidat faux tous
deux a 1,0 de preuves (specification limitee au cas nominal), le livrable CHANGE selon
l'ordre dans lequel les modeles ont repondu — et rien ne le signale. Sur les entrees
que la specification ne couvre pas, les deux divergent pourtant visiblement :

    [2, 4]   ->  3.0   vs   3
    [0, 1]   ->  0.5   vs   0

Un systeme qui repond « livre » dans cette situation n'est pas un systeme sur : il a
choisi au hasard et n'a rien dit. Or les candidats sont DEJA la, payes : les comparer
entre eux ne coute **aucun appel de modele**.

Ce que ce module apporte
------------------------
* **detection** : les candidats sont executes sur les memes entrees derivees
  (annotations, exemples `>>>`), et leurs resultats sont compares — valeur rendue ou
  exception levee ;
* **choix informe** : quand plus de deux candidats sont a egalite, un candidat dont
  le comportement est partage par une majorite d'autres est prefere a un candidat
  isole. Un desaccord isole a plus de chances d'etre une erreur qu'un accord ;
* **aveu** : tout desaccord devient un constat nomme, avec l'entree exacte et les
  valeurs obtenues. Jamais un rejet — un desaccord sur un comportement NON SPECIFIE
  est legitime (deux implementations correctes peuvent différer sur `mean([])`), et
  accuser a tort couterait plus cher que le silence qu'on corrige.

Ce que ce module ne peut PAS faire
----------------------------------
Sans annotation ni exemple `>>>`, il n'existe aucun domaine d'entree a explorer : deux
candidats non documentes ne sont pas comparables, et le module le dit au lieu de
laisser croire qu'ils ont ete verifies.
"""

from __future__ import annotations

import ast
import json
from dataclasses import dataclass

from ..core.types import Severity
from .properties import _cases_for

__all__ = ["Divergence", "comparer", "PROBE_BUDGET"]

#: Plafond d'entrees sondees. Une divergence se montre sur UNE entree : au-dela de
#: quelques dizaines, on paie sans rien apprendre de plus.
PROBE_BUDGET = 12

#: Plafond de candidats compares (le cout d'execution croit avec le nombre).
CANDIDAT_BUDGET = 4


@dataclass(frozen=True)
class Divergence:
    """Un desaccord observable entre candidats, sur une entree precise."""

    entree: str
    resultats: tuple[tuple[str, str], ...]      # (etiquette du candidat, resultat)
    majoritaire: str = ""                        # etiquette majoritaire, si elle existe

    def render(self) -> str:
        detail = " | ".join(f"{nom}: {valeur}" for nom, valeur in self.resultats)
        return f"{self.entree} -> {detail}"


def _cas_d_entree(source: str, entrypoint: str, budget: int = PROBE_BUDGET):
    """Entrees derivees du candidat : annotations, sinon exemples de l'auteur."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    node = None
    for item in ast.walk(tree):
        if isinstance(item, ast.FunctionDef) and item.name == entrypoint:
            node = item
            break
    if node is None:
        for item in ast.walk(tree):
            if isinstance(item, ast.FunctionDef):
                node = item
                break
    if node is None:
        return []
    positional = list(node.args.posonlyargs) + list(node.args.args)
    if positional and positional[0].arg in {"self", "cls"}:
        return []
    # `_cases_for` gere l'ordre de fiabilite : domaine declare (annotations) puis
    # temoins ecrits par l'auteur (exemples `>>>`), deformes pour couvrir les bords.
    cases, provenance = _cases_for(node, positional, budget, seed=20260101)
    return [(case, provenance) for case in cases[:budget]]


def _sonde(source: str, entrypoint: str, cases: list[tuple[object, ...]]) -> list[str] | None:
    """Execute un candidat sur les entrees et rend une trace canonique par entree.

    La trace est un TEXTE (valeur ou type d'exception). Comparer des textes evite
    toutes les surprises de comparaison d'objets entre deux programmes differents.
    """
    from .executable import Sandbox

    litteraux = ",\n    ".join(
        "(" + ", ".join(repr(v) for v in case) + ",)" for case in cases
    )
    # Sortie en JSON : un separateur maison a d'abord ete utilise, et son echappement
    # s'est perdu en traversant `repr` -> toutes les sondes etaient jetees en silence.
    # Un format standard ne peut pas se corrompre de cette facon.
    # Le marqueur ne commence PAS par `JIO_` : `test_env_wiring` cherche les variables
    # d'environnement dans le source, et un marqueur nomme comme une variable etait
    # signale a juste titre comme un reglage non documente.
    programme = (
        source
        + "\n\n"
        + "import json as _jio_json\n"
        + "_jio_cas = [\n    "
        + litteraux
        + ",\n]\n"
        + "_jio_fn = globals().get(" + repr(entrypoint) + ")\n"
        + "if not callable(_jio_fn):\n"
        + "    raise SystemExit('entree absente')\n"
        + "_jio_sortie = []\n"
        + "for _jio_c in _jio_cas:\n"
        + "    try:\n"
        + "        _jio_sortie.append(repr(_jio_fn(*_jio_c)))\n"
        + "    except Exception as _jio_e:\n"
        + "        _jio_sortie.append('!' + type(_jio_e).__name__)\n"
        + "print('SONDE_DIVERGENCE=' + _jio_json.dumps(_jio_sortie))\n"
    )
    resultat = Sandbox(timeout=20).run_python(programme, tag="divergence")
    if not resultat.ok:
        return None
    for ligne in resultat.stdout.splitlines():
        if ligne.startswith("SONDE_DIVERGENCE="):
            try:
                trace = json.loads(ligne[len("SONDE_DIVERGENCE="):])
            except Exception:
                return None
            return trace if isinstance(trace, list) else None
    return None


def comparer(
    candidats: list[tuple[str, str]],
    entrypoint: str,
    *,
    budget: int = PROBE_BUDGET,
    candidat_budget: int = CANDIDAT_BUDGET,
) -> tuple[tuple[Divergence, ...], str]:
    """Compare les candidats. Rend `(divergences, majoritaire)`.

    `candidats` : liste de `(etiquette, source)`. L'etiquette sert uniquement a
    rendre le constat lisible ; elle n'influence aucune decision.

    `majoritaire` : etiquette du candidat dont le comportement est partage par une
    majorite STRICTE des autres. Vide s'il n'y a pas de majorite claire — auquel cas
    aucun candidat n'est prefere, et le desaccord est simplement avoue.

    Aucune exception ne remonte : ce module OBSERVE, il ne juge pas. Un candidat qui
    ne s'execute pas est simplement absent de la comparaison.
    """
    candidats = [(nom, src) for nom, src in candidats[:candidat_budget] if src.strip()]
    if len(candidats) < 2:
        return (), ""

    premier = candidats[0][1]
    cases_et_provenance = _cas_d_entree(premier, entrypoint, budget)
    if not cases_et_provenance:
        return (), ""
    cases = [case for case, _ in cases_et_provenance]
    if not cases:
        return (), ""

    traces: list[tuple[str, list[str]]] = []
    for nom, source in candidats:
        trace = _sonde(source, entrypoint, cases)
        if trace is not None and len(trace) == len(cases):
            traces.append((nom, trace))
    if len(traces) < 2:
        return (), ""

    divergences: list[Divergence] = []
    for index, case in enumerate(cases):
        valeurs = [(nom, trace[index]) for nom, trace in traces]
        distinctes = {valeur for _, valeur in valeurs}
        if len(distinctes) < 2:
            continue
        # Valeur majoritaire : au moins deux candidats s'accordent.
        compte: dict[str, int] = {}
        for _, valeur in valeurs:
            compte[valeur] = compte.get(valeur, 0) + 1
        meilleure = max(compte.items(), key=lambda item: item[1])
        majoritaire_local = ""
        if meilleure[1] > len(valeurs) / 2 and len(valeurs) >= 3:
            majoritaire_local = next(nom for nom, valeur in valeurs if valeur == meilleure[0])
        divergences.append(
            Divergence(
                entree=repr(case),
                resultats=tuple(valeurs),
                majoritaire=majoritaire_local,
            )
        )

    # Le candidat majoritaire GLOBAL : celui qui est majoritaire sur TOUTES les
    # divergences. Une majorite partielle ne suffit pas a preferer un candidat.
    majoritaire = ""
    if divergences and all(d.majoritaire for d in divergences):
        candidats_majoritaires = {d.majoritaire for d in divergences}
        if len(candidats_majoritaires) == 1:
            majoritaire = candidats_majoritaires.pop()
    return tuple(divergences), majoritaire


def severite(divergences: tuple[Divergence, ...]) -> Severity:
    """Un desaccord n'est jamais bloquant : il est SIGNALE.

    Un desaccord porte souvent sur un comportement non specifie, ou deux
    implementations correctes different legitimement. Le transformer en rejet
    produirait exactement le faux positif que ce projet refuse.
    """
    return Severity.MEDIUM if divergences else Severity.LOW
