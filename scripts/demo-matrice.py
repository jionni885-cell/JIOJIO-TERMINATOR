#!/usr/bin/env python3
"""Demonstration reproductible de la matrice mutants x regles.

Ce script ne raconte rien : il MESURE les deux references citees dans le README et
il echoue si la matrice se trompe d'accusation. C'est la version que la preuve
`scripts/evidence.sh` rejoue, et c'est celle qui doit rester vraie.

Reference 1 — `median` avec une specification faible
    Un mutant survit sur la ligne du test de parite. Les deux regles l'ont EXECUTEE
    (elles appellent la fonction) : elles sont donc `aveugle`, pas `hors-portee`, et
    le geste demande est de renforcer le controle — pas d'ajouter une regle.

Reference 2 — `tariff` avec une regle qui n'atteint jamais la seconde branche
    Le mutant de la ligne 4 survit parce qu'AUCUNE regle n'execute cette ligne. La
    matrice doit refuser d'accuser la regle existante et demander une regle de plus :
    c'est la difference entre « controle faible » et « chemin non couvert ».

Usage :  python scripts/demo-matrice.py
Sortie : code 0 si les deux references tiennent, 1 sinon.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from jio.core.types import Rule, RuleKind, Spec
from jio.verify.matrice import (
    AVEUGLE,
    HORS_PORTEE,
    construire,
    formater,
)

MEDIAN = """def median(nums):
    s = sorted(nums)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2
"""

TARIFF = """def tariff(age):
    if age < 18:
        return 0
    return 20
"""


def cas_median() -> bool:
    spec = Spec(
        mission="mediane",
        rules=(
            Rule(id="R-001", statement="mediane d'une liste impaire", kind=RuleKind.PROPERTY),
            Rule(id="R-002", statement="le resultat existe", kind=RuleKind.PROPERTY),
        ),
    )
    checks = {
        "R-001": "assert median([3, 1, 2]) == 2",
        "R-002": "assert median([1, 2, 3, 4]) is not None",
    }
    print("== Reference 1 : une regle de FORME ne peut pas voir un changement de valeur")
    matrice = construire(MEDIAN, spec, checks=checks, budget=4)
    print(formater(matrice))

    etats = {c.etat for index in matrice.survivants for c in matrice.cellules_de(index)}
    if AVEUGLE not in etats:
        print("\nECHEC : un controle qui a execute la ligne mutee doit etre declare AVEUGLE.")
        return False
    if "R-002" not in matrice.regles_aveugles:
        print("\nECHEC : `is not None` est la faiblesse de R-002, la matrice doit la nommer.")
        return False
    if "falsifiable" not in " ".join(matrice.reserves):
        print("\nECHEC : le geste demande (rendre l'assertion falsifiable) doit etre ecrit.")
        return False
    print("\nOK : la faiblesse est nommee, avec le geste qui la corrige.")
    return True


def cas_tariff() -> bool:
    spec = Spec(
        mission="tarif",
        rules=(Rule(id="R-001", statement="avant 18 ans, gratuit", kind=RuleKind.PROPERTY),),
    )
    print("\n== Reference 2 : une ligne qu'AUCUNE regle n'execute n'accuse pas les regles")
    matrice = construire(
        TARIFF, spec, checks={"R-001": "assert tariff(10) == 0"}, budget=5
    )
    print(formater(matrice))

    hors_portee = [
        index
        for index in matrice.survivants
        for cellule in matrice.cellules_de(index)
        if cellule.etat == HORS_PORTEE
    ]
    if not hors_portee:
        print("\nECHEC : le mutant de la ligne 4 n'est atteint par aucune regle ;")
        print("        le declarer autrement qu'`hors-portee` accuserait une regle a tort.")
        return False
    if hors_portee[0] not in matrice.survivants_sans_couverture:
        print("\nECHEC : le trou de specification doit etre compte comme tel.")
        return False
    if "ajouter une regle" not in " ".join(matrice.reserves):
        print("\nECHEC : la reserve doit demander une regle de plus, pas un durcissement.")
        return False
    if not matrice.regles_aveugles:
        print("\nECHEC : le mutant de borne (18 -> 19) est, lui, bien aveugle.")
        return False
    print("\nOK : la matrice distingue « controle faible » de « chemin non couvert ».")
    return True


def main() -> int:
    ok = cas_median()
    ok = cas_tariff() and ok
    if not ok:
        return 1
    print(
        "\nLes deux references tiennent : "
        "un survivant n'est pas un chiffre, c'est un geste a faire."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
