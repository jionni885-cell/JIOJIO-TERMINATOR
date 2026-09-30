"""Les codes de sortie : un message d'erreur qui sort en 0 est un mensonge a la machine.

LE DEFAUT, mesure sur un projet ETRANGER. `jio run "<objectif>"` sans aucun fournisseur
affichait :

    Aucun fournisseur detecte.
    Installe un CLI (opencode, hermes, claude, codex, gemini) ou definis
    une variable d'environnement d'API (OPENROUTER_API_KEY, OPENAI_API_KEY...).

et sortait en **0**. Ce n'est pas un oubli dans le code : c'est une propriete de Python —
`raise SystemExit("message")` (avec une CHAINE) ecrit le message sur la sortie d'erreur et
termine NORMALEMENT. Le code 0 est ce qu'un agent qui enchaine lit comme « c'est fait, et
prouve » : il n'ira donc jamais chercher la cle manquante, et rien ne le lui aura dit.

La doctrine du depot range ce cas en `INDETERMINE` (2) : « il manque de quoi conclure : un
fournisseur, une preuve, une entree », action associee « fournir ce qui manque, puis relancer ».
`jio/core/codes.py::sortir` est le seul chemin qui ecrit un message ET sort avec un code, et le
code y est un parametre OBLIGATOIRE — un appelant doit decider ce qu'il vient de dire.

Deux verrous, parce qu'un seul ne suffirait pas : un verrou MECANIQUE (aucune forme interdite
dans le paquet, lu par `ast`, donc insensible a la reformulation) et un verrou COMPORTEMENTAL
(la commande reelle, sans fournisseur, rend bien 2).
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


def _fichiers_du_paquet() -> list[Path]:
    paquet = Path(__file__).resolve().parent.parent / "jio"
    return sorted(p for p in paquet.rglob("*.py") if "__pycache__" not in p.parts)


def test_aucun_SystemExit_avec_un_MESSAGE_dans_tout_le_paquet() -> None:
    """La forme qui a produit le defaut est interdite partout, pas seulement la ou on l'a vue.

    On lit l'arbre syntaxique, pas le texte : une reformulation (`raise SystemExit(msg)`,
    `raise SystemExit(f"...")`, une concatenation) ne peut pas passer entre les mailles. Les
    formes CORRECTES sont laissees : `SystemExit(main())` (le code vient de `main`) et
    `SystemExit(2)` (le code est decide).
    """
    coupables: list[str] = []
    for chemin in _fichiers_du_paquet():
        arbre = ast.parse(chemin.read_text(encoding="utf-8"), filename=str(chemin))
        for noeud in ast.walk(arbre):
            if not isinstance(noeud, ast.Raise) or noeud.exc is None:
                continue
            appel = noeud.exc
            if not isinstance(appel, ast.Call) or getattr(appel.func, "id", "") != "SystemExit":
                continue
            if not appel.args:
                continue
            argument = appel.args[0]
            interdite = isinstance(argument, (ast.Constant, ast.JoinedStr, ast.BinOp)) or (
                isinstance(argument, ast.Call) and getattr(argument.func, "id", "") == "str"
            )
            if interdite:
                coupables.append(f"{chemin.name}:{noeud.lineno}")
    assert not coupables, (
        "ces `SystemExit` prennent un MESSAGE et sortent donc en 0 (le code 0 dit « c'est "
        "fait, et prouve ») : " + ", ".join(coupables) + " — utiliser `codes.sortir(message, "
        "code)`, qui rend le code obligatoire."
    )


def test_la_fonction_sortir_rend_le_code_OBLIGATOIRE() -> None:
    """Un appelant doit DECIDER du code : un defaut implicite recreerait le meme silence."""
    import inspect

    from jio.core import codes

    parametres = inspect.signature(codes.sortir).parameters
    assert "code" in parametres
    assert parametres["code"].default is inspect.Parameter.empty, (
        "`sortir` sans code obligatoire laisserait recreer « un message d'erreur qui sort en 0 »"
    )


def test_jio_run_sans_fournisseur_sort_en_INDETERMINE(monkeypatch, capsys) -> None:
    """La commande reelle, sans aucun fournisseur : code 2, et les chemins SANS CLE sont dits.

    Le message ne se contente pas de constater le manque : il nomme les deux chemins qui
    marchent sans aucune cle (`jio bench`, `jio run ... --simulate --task ... --no-oracle`).
    Une erreur qui n'indique pas d'issue oblige l'utilisateur a deviner — et il desinstalle.
    """
    from jio.core.codes import INDETERMINE
    from jio.providers import registry

    monkeypatch.setattr(registry, "from_env", lambda: registry.Registry())
    from jio.cli import main

    code = main(["run", "corrige le total du panier"])
    capture = capsys.readouterr()
    assert code == INDETERMINE, (
        f"un fournisseur manquant n'est pas un succes (code rendu : {code})\n{capture.err}"
    )
    assert "fournisseur" in capture.err.lower()
    assert "--simulate" in capture.err, "le chemin sans cle doit etre indique"
    assert "jio bench" in capture.err


def test_un_nom_de_fournisseur_inconnu_sort_en_INDETERMINE() -> None:
    """Meme famille : un nom inconnu est un usage impossible, pas une reussite."""
    from jio.core.codes import INDETERMINE
    from jio.providers.registry import make_providers

    with pytest.raises(SystemExit) as sortie:
        make_providers(["fournisseur-qui-nexiste-pas"])
    assert sortie.value.code == INDETERMINE


def test_main_TRADUIT_un_SystemExit_en_code_et_jamais_en_zero(monkeypatch, capsys) -> None:
    """Le garde-fou de dernier recours, et la seule traduction qui compte : la chaine n'est
    jamais un succes.

    `main()` est l'entree du programme ET ce que les tests appellent : elle doit rendre un
    nombre. Trois cas, trois reponses — `None` -> 0 (sortie demandee), un entier -> cet entier,
    une CHAINE -> le message est ecrit et le code est **1**, jamais 0. C'est exactement la
    traduction que Python fait a l'envers, et c'est ce qui a produit le defaut mesure.
    """
    from jio import cli

    def leve(valeur: object):
        def commande(_args) -> int:
            raise SystemExit(valeur)

        return commande

    for code_attendu, valeur in ((0, None), (2, 2), (1, "un message nu")):
        monkeypatch.setattr(cli, "cmd_doctor", leve(valeur))
        capture = capsys.readouterr()
        assert cli.main(["doctor"]) == code_attendu, capture.err
    assert "un message nu" in capsys.readouterr().err, "le message doit tout de meme etre ecrit"
