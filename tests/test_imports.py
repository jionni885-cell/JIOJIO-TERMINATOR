"""Tests de la coherence des imports internes.

Cette verifcation attrape la classe d'erreur la plus banale et la plus coûteuse :
un symbole renomme cote fournisseur, oublie cote appelant. Le fichier modifie
reste valide ; c'est le consommateur qui casse a l'execution.

Ce que ces tests protegent en priorite, c'est la PRUDENCE : aucun test ici
n'exige une accusation. Ils exigent qu'on se taise quand on ne peut pas trancher.
"""

from __future__ import annotations

from pathlib import Path

from jio.verify.imports import analyse, check_project


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _check(root: Path) -> list[str]:
    paths = sorted(root.rglob("*.py"))
    return [f"{p.path.name}:{p.message}" for p in check_project(paths, root)]


def test_renommage_dune_fonction_publique_est_detecte(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from pkg.filesize import naturalsize\n")
    _write(tmp_path, "pkg/filesize.py", "def _naturalsize(value):\n    return value\n")

    messages = _check(tmp_path)

    assert len(messages) == 1
    assert "naturalsize" in messages[0]
    assert "filesize.py" in messages[0]


def test_un_projet_coherent_ne_produit_rien(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "from pkg.a import helper\n")
    _write(tmp_path, "pkg/a.py", "def helper():\n    return 1\n")

    assert _check(tmp_path) == []


def test_import_externe_est_ignore(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/a.py", "import os\nimport json\nfrom collections import OrderedDict\n")

    assert _check(tmp_path) == []


def test_resolution_ambiague_est_ignoree(tmp_path: Path) -> None:
    """Deux modules partagent le meme suffixe : on ne peut pas trancher, donc on se tait.

    Accuser le mauvais fichier est pire que de ne rien dire : l'utilisateur perd
    sa confiance dans l'outil au premier faux positif.
    """
    _write(tmp_path, "a/utils.py", "def helper():\n    return 1\n")
    _write(tmp_path, "b/utils.py", "def autre():\n    return 1\n")
    _write(tmp_path, "a/consumer.py", "from utils import helper\n")

    assert _check(tmp_path) == []


def test_import_en_etoile_est_ignore(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/a.py", "def helper():\n    return 1\n")
    _write(tmp_path, "pkg/b.py", "from pkg.a import *\n")

    assert _check(tmp_path) == []


def test_module_incompilable_n_est_pas_accuse_de_renommage(tmp_path: Path) -> None:
    """Un fichier qui ne compile pas n'a pas d'exports lisibles : le scan s'en charge ailleurs."""
    _write(tmp_path, "pkg/a.py", "def helper(:\n    pass\n")
    _write(tmp_path, "pkg/b.py", "from pkg.a import helper\n")

    assert _check(tmp_path) == []


def test_import_relatif_est_resolu(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "def helper():\n    return 1\n")
    _write(tmp_path, "pkg/b.py", "from .a import helper\n")

    assert _check(tmp_path) == []


def test_symbole_absent_dun_module_relatif_est_detecte(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "def autre():\n    return 1\n")
    _write(tmp_path, "pkg/b.py", "from .a import helper\n")

    messages = _check(tmp_path)

    assert len(messages) == 1
    assert "helper" in messages[0]


def test_acces_par_attribut_est_verifie(tmp_path: Path) -> None:
    """`import pkg.a` puis `pkg.a.helper()` doit etre vu comme un import de `helper`."""
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/a.py", "def autre():\n    return 1\n")
    _write(tmp_path, "pkg/b.py", "from pkg import a\n\n\ndef use():\n    return a.helper()\n")

    messages = _check(tmp_path)

    assert messages, "un appel a un attribut inexistant doit etre vu"
    assert "helper" in messages[0]


def test_le_nom_est_trouve_quelle_que_soit_la_racine_du_scan(tmp_path: Path) -> None:
    """Scanner le depot ou le dossier du paquet doit donner le MEME verdict.

    Constate sur un vrai projet : le meme renommage etait detecte depuis la racine,
    et invisible depuis le dossier du paquet. Un audit ne doit pas dependre de
    l'endroit d'ou on le regarde.
    """
    _write(tmp_path, "src/humanize/__init__.py", "from humanize.filesize import naturalsize\n")
    _write(tmp_path, "src/humanize/filesize.py", "def _naturalsize(value):\n    return value\n")

    from_root = _check(tmp_path)
    from_package = _check(tmp_path / "src" / "humanize")

    assert from_root != [], "detecte depuis la racine"
    assert from_package != [], "doit aussi etre detecte depuis le dossier du paquet"


def test_analyse_rapporte_ce_que_le_fichier_declare(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "pkg/m.py",
        "import os as _os\nfrom collections import deque\n\n\nclass A:\n    pass\n\n\ndef f():\n    pass\n",
    )

    info = analyse(path, tmp_path)

    assert info.parses
    assert {"A", "f", "deque", "_os", "os"} <= info.defines or {"A", "f"} <= info.defines
    assert info.dotted == "pkg.m"
    assert info.package == "pkg"


def test_aucun_fichier_ne_produit_aucun_probleme() -> None:
    assert check_project([], Path(".")) == []
