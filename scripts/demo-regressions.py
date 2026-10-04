#!/usr/bin/env python3
"""Demonstration reproductible du jeu de regression : un defaut reel qui revient se VOIT.

Trois etats sont mesures sur le corpus VERSIONNE (`evidence/regressions/`), et le script
echoue si l'un des trois ne se produit pas :

  1. version courante      -> les cas tiennent, taux de silence 0 % ;
  2. redaction neutralisee -> les cas de SECURITE se taisent (FUITE) et le rapport BLOQUE
                              la livraison : c'est le critere qui decide de ce module ;
  3. preuve muette         -> le cas de TEMOIN se tait aussi, mais il ne bloque pas : un
                              silence de temoin est un defaut, pas une fuite.

Le point 2 est la raison d'etre du corpus : sans lui, une fuite refermee a la version N
pourrait revenir a la version N+1 sans qu'aucun controle ne bronche.

Usage :  python scripts/demo-regressions.py
Sortie : code 0 si les trois etats sont observes, 1 sinon.
"""

from __future__ import annotations

import sys
from pathlib import Path

RACINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RACINE))

from jio.core.types import Witness
from jio.eval import regressions as R
from jio.verify.executable import ProverResult

JEU = RACINE / "evidence" / "regressions"


class _ProuveurMuet:
    """Un prouveur qui ne detecte plus rien : la panne la plus dangereuse du harness."""

    def prove(self, source, spec, **kwargs):
        return ProverResult(
            witnesses=tuple(
                Witness(rule_id=r.id, command="muet", exit_code=0, ok=True) for r in spec.rules
            )
        )


def main() -> int:
    if not JEU.is_dir():
        print(f"ECHEC : aucun corpus versionne dans {JEU}")
        return 1
    corpus = R.charger(JEU)
    print(f"== Corpus : {len(corpus)} cas gele(s) depuis de vraies traces")
    for cas in corpus:
        marque = "BLOQUANT" if cas.bloquant else "temoin  "
        print(f"   [{marque}] {cas.id}  {cas.provenance}")

    print("\n== 1. Version courante : les cas doivent TENIR")
    courant = R.evaluer(corpus)
    print(R.formater(courant))
    if courant.silencieux or courant.bloque:
        print("\nECHEC : le corpus ne tient pas sur la version courante.")
        return 1

    print("\n== 2. Redaction neutralisee : les cas de securite doivent BLOQUER")
    original = R.redact_data
    R.redact_data = lambda valeur, **_kw: valeur
    try:
        fuite = R.evaluer(corpus)
    finally:
        R.redact_data = original
    print(R.formater(fuite))
    if not fuite.bloque:
        print("\nECHEC : aucune regression de securite detectee — le corpus ne garde rien.")
        return 1
    if not fuite.silencieux or fuite.taux_de_silence <= 0:
        print("\nECHEC : le taux de silence n'a pas bouge.")
        return 1
    print(f"\n   -> {len(fuite.bloquants)} cas BLOQUANT(S), taux de silence "
          f"{fuite.taux_de_silence:.0%} : la livraison serait refusee.")

    print("\n== 3. Prouveur muet : le cas de temoin doit se taire, sans bloquer")
    muet = R.evaluer(corpus, prover=_ProuveurMuet())
    print(R.formater(muet))
    temoins_silencieux = [r for r in muet.silencieux if not r.bloquant]
    if not temoins_silencieux:
        print("\nECHEC : le silence du temoin n'a pas ete vu.")
        return 1
    print(
        f"\n   -> {len(temoins_silencieux)} silence(s) de temoin vu(s) : un defaut qui se "
        "declare, distinct d'une fuite qui bloque."
    )

    print(
        "\nLes trois etats sont observes : un echec reel enregistre ne peut plus "
        "revenir en silence."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
