"""Tests des analyseurs standards branches sur `jio scan`.

Deux exigences opposees, et c'est tout l'enjeu de ce module :

1. **ne pas reinventer** ce que des outils eprouves font mieux (ruff, flake8,
   pyflakes) ;
2. **ne jamais faire croire** qu'un projet a ete verifie quand aucun outil n'a
   tourne. L'absence d'analyseur n'est pas un echec : c'est une information, et
   elle doit etre dite avec la commande exacte a lancer.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from jio.verify.linters import (
    BUG_RULES,
    LintFinding,
    MAX_FINDINGS,
    _parse_concise,
    _parse_ruff_json,
    analyse,
    plain_french,
)

def _ruff_present() -> bool:
    if shutil.which("ruff") is not None:
        return True
    try:  # pragma: no cover - depend de l'environnement
        import importlib.util

        return importlib.util.find_spec("ruff") is not None
    except Exception:  # pragma: no cover
        return False


RUFF_AVAILABLE = _ruff_present()


def test_aucun_analyseur_installe_le_dit_et_naccuse_personne(tmp_path: Path) -> None:
    """Sans outil disponible, on rend une note actionnable — et zero accusation."""
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    report = analyse([tmp_path / "a.py"], root=tmp_path, prefer="outil-inexistant")

    assert report.findings == []
    assert report.tool == ""
    assert "pip install ruff" in report.note


def test_desactivation_explicite_est_respectee(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")

    report = analyse([tmp_path / "a.py"], root=tmp_path, prefer="off")

    assert report.findings == []
    assert "desactives" in report.note


def test_aucun_fichier_ne_produit_aucun_constat() -> None:
    report = analyse([])

    assert report.findings == []
    assert report.tool == ""


def test_le_jeu_de_regles_ne_contient_aucune_regle_de_style() -> None:
    """JIO n'est pas un formateur : une regle de style dans ce jeu serait un bug.

    Un projet qui passe ses tests ne doit pas etre declare fautif parce qu'il
    n'aime pas l'ordre des imports. C'est ainsi qu'un outil perd sa credibilite.
    """
    codes = set(BUG_RULES.split(","))

    assert codes == {"E9", "F63", "F7", "F811", "F82"}
    for style_rule in ("E501", "I001", "D", "ANN", "N", "UP", "C901", "PLR"):
        assert not any(code.startswith(style_rule) for code in codes)


def test_lecture_du_format_condense() -> None:
    """Format `chemin:ligne:colonne: CODE message` (flake8, pyflakes)."""
    text = (
        "a.py:3:1: F821 undefined name 'x'\n"
        "a.py:9:5: E999 SyntaxError: unexpected EOF\n"
        "b.py:1:1: something went wrong\n"          # pyflakes sans code de regle
        "ligne illisible\n"
    )

    findings = _parse_concise(text, "flake8")

    assert [f.rule for f in findings] == [
        "flake8:F821",
        "flake8:E999",
        "flake8:pyflakes",
    ]
    assert findings[0].line == 3
    assert "undefined name" in findings[0].message


def test_lecture_du_format_json_de_ruff() -> None:
    payload = """[
      {"filename": "a.py", "location": {"row": 5}, "code": "F821",
       "message": "Undefined name `y`"},
      {"bidon": true}
    ]"""

    findings = _parse_ruff_json(payload)

    assert len(findings) == 1
    assert findings[0].rule == "ruff:F821"
    assert findings[0].line == 5
    assert findings[0].path == Path("a.py")


def test_json_illisible_ne_casse_pas_lanalyse() -> None:
    assert _parse_ruff_json("ceci n'est pas du json") == []
    assert _parse_ruff_json("") == []


def test_les_constats_sont_expliques_en_francais() -> None:
    """L'interface est en francais, sans jamais perdre le message d'origine."""
    finding = LintFinding(Path("a.py"), 1, "ruff:F821", "Undefined name `x`")

    label = finding.label

    assert "nom non defini" in label
    assert "Undefined name" in label, "la preuve d'origine doit rester visible"


def test_un_code_inconnu_reste_affiche_brut() -> None:
    assert plain_french("XYZ999") == ""
    assert LintFinding(Path("a.py"), 1, "ruff:XYZ999", "bizarre").label == "bizarre"


def test_le_plafond_evite_de_noyer_le_rapport(tmp_path: Path) -> None:
    """Un fichier peut produire des centaines de constats : le rapport doit rester lisible."""
    source = "\n".join(f"valeur_{i} = inconnu_{i}" for i in range(MAX_FINDINGS + 20))
    path = tmp_path / "beaucoup.py"
    path.write_text(source, encoding="utf-8")

    report = analyse([path], root=tmp_path, prefer="ruff")

    if report.tool == "":
        pytest.skip("aucun analyseur installe dans cet environnement")
    assert len(report.findings) <= MAX_FINDINGS
    assert report.truncated >= 1


@pytest.mark.skipif(not RUFF_AVAILABLE, reason="ruff non installe")
def test_ruff_trouve_un_nom_non_defini(tmp_path: Path) -> None:
    path = tmp_path / "buggy.py"
    path.write_text("def f(v):\n    return v + inconnue\n", encoding="utf-8")

    report = analyse([path], root=tmp_path, prefer="ruff")

    assert report.tool == "ruff"
    assert any("F821" in f.rule for f in report.findings)


@pytest.mark.skipif(not RUFF_AVAILABLE, reason="ruff non installe")
def test_ruff_trouve_une_redefinition_de_fonction(tmp_path: Path) -> None:
    """F811 est la trace exacte d'un renommage incomplet — la classe recherchee."""
    path = tmp_path / "renomme.py"
    path.write_text(
        "def marche(a):\n    return a\n\n\ndef marche(a):\n    return a * 2\n",
        encoding="utf-8",
    )

    report = analyse([path], root=tmp_path, prefer="ruff")

    assert any("F811" in f.rule for f in report.findings)


@pytest.mark.skipif(not RUFF_AVAILABLE, reason="ruff non installe")
def test_du_code_propre_ne_produit_aucun_constat(tmp_path: Path) -> None:
    """Le controle qui compte : pas de faux positif sur du code sain."""
    path = tmp_path / "propre.py"
    path.write_text(
        '"""Propre."""\n\n\ndef double(valeur: int) -> int:\n    return valeur * 2\n',
        encoding="utf-8",
    )

    report = analyse([path], root=tmp_path, prefer="ruff")

    assert report.findings == []
