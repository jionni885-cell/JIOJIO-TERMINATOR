"""Un test qui importe un paquet non declare est un rouge qui attend son heure.

Defaut reel, trouve en reconstruisant l'environnement de ce depot apres un incident : la CI
installait `pytest` et `ruff`, et son commentaire affirmait « aucune autre dependance n'est
necessaire ». Or `tests/test_hooks.py` importe `yaml`.

Mesure, sur un venv neuf et `python -m pip install pytest ruff` :

    E   ModuleNotFoundError: No module named 'yaml'
    FAILED tests/test_hooks.py::test_le_hook_strict_utilise_vraiment_le_mode_strict
    FAILED tests/test_hooks.py::test_les_hooks_declarent_les_bonnes_options_de_fichiers

Le defaut n'etait pas l'import : c'etait qu'AUCUN controle ne reliait ce que les tests
utilisent a ce qui est declare. Une dependance manquante ne se voit que sur une machine ou
elle manque — jamais sur celle du developpeur, qui l'a installee un jour pour autre chose.
"""

from __future__ import annotations

from pathlib import Path

from jio.cli import main
from jio.verify.dependances import (
    CORRESPONDANCES,
    declarations,
    imports_externes,
    manquants,
)

PROJET = Path(__file__).resolve().parent.parent


def _projet(tmp_path: Path, contenu: str, pyproject: str = "") -> Path:
    (tmp_path / "tests").mkdir(parents=True, exist_ok=True)
    (tmp_path / "tests" / "test_x.py").write_text(contenu, encoding="utf-8")
    if pyproject:
        (tmp_path / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    return tmp_path


PYPROJECT_SANS_DEPENDANCE = """[project]
name = "x"
version = "0"
dependencies = []
"""


# --------------------------------------------------------------------------- #
# 1. Le controle mord
# --------------------------------------------------------------------------- #


def test_un_paquet_non_declare_est_signale(tmp_path: Path) -> None:
    racine = _projet(tmp_path, "import paquet_fantome_xyz\n", PYPROJECT_SANS_DEPENDANCE)
    trouves = manquants(racine)
    assert [m.paquet for m in trouves] == ["paquet_fantome_xyz"]
    assert trouves[0].fichiers == ("tests/test_x.py",)
    assert "tests/test_x.py" in str(trouves[0])


def test_un_import_DANS_une_fonction_compte_autant(tmp_path: Path) -> None:
    """Le cas exact rencontre : `import yaml` etait ecrit dans le corps d'un test.

    Un controle qui ne lit que les en-tetes de fichier aurait laisse passer precisement
    le defaut pour lequel il existe.
    """
    racine = _projet(
        tmp_path,
        "def test_a():\n    import paquet_fantome_xyz\n    assert True\n",
        PYPROJECT_SANS_DEPENDANCE,
    )
    assert [m.paquet for m in manquants(racine)] == ["paquet_fantome_xyz"]


def test_le_nom_de_distribution_est_resolu(tmp_path: Path) -> None:
    """`import yaml` vient du paquet `PyYAML` : accuser `yaml` quand `PyYAML` est declare
    serait un faux positif, et un controle qui crie a tort se fait desactiver."""
    assert CORRESPONDANCES["yaml"] == "pyyaml"
    racine = _projet(
        tmp_path,
        "import yaml\n",
        '[project]\nname = "x"\nversion = "0"\ndependencies = ["PyYAML>=6.0"]\n',
    )
    assert manquants(racine) == [], "une declaration en PyYAML doit couvrir `import yaml`"


def test_une_declaration_dans_un_EXTRA_suffit(tmp_path: Path) -> None:
    racine = _projet(
        tmp_path,
        "import yaml\n",
        '[project]\nname = "x"\nversion = "0"\ndependencies = []\n'
        '[project.optional-dependencies]\ndev = ["pyyaml>=6.0"]\n',
    )
    assert manquants(racine) == []


def test_une_installation_par_la_CI_suffit(tmp_path: Path) -> None:
    """Deuxieme endroit legitime : un projet peut installer ses outils dans son workflow."""
    racine = _projet(tmp_path, "import yaml\n", PYPROJECT_SANS_DEPENDANCE)
    (tmp_path / ".github").mkdir()
    (tmp_path / ".github" / "ci.yml").write_text(
        "steps:\n  - run: |\n      python -m pip install pytest pyyaml\n", encoding="utf-8"
    )
    assert manquants(racine) == []
    assert "pyyaml" in declarations(racine)


# --------------------------------------------------------------------------- #
# 2. Pas de faux positifs : ce qui n'est PAS une dependance externe
# --------------------------------------------------------------------------- #


def test_la_bibliotheque_standard_n_est_pas_une_dependance(tmp_path: Path) -> None:
    racine = _projet(
        tmp_path,
        "import ast\nimport json\nfrom pathlib import Path\nfrom collections import Counter\n",
        PYPROJECT_SANS_DEPENDANCE,
    )
    assert imports_externes(racine) == {}
    assert manquants(racine) == []


def test_un_module_local_n_est_pas_une_dependance(tmp_path: Path) -> None:
    """`import jio` dans les tests de ce depot n'est pas une dependance : c'est le projet."""
    racine = _projet(tmp_path, "import paquet_maison\n", PYPROJECT_SANS_DEPENDANCE)
    (tmp_path / "paquet_maison").mkdir()
    (tmp_path / "paquet_maison" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "module_maison.py").write_text("x = 1\n", encoding="utf-8")
    assert manquants(racine) == []


def test_un_import_relatif_est_local(tmp_path: Path) -> None:
    racine = _projet(tmp_path, "from . import aide\nfrom .aide import truc\n", "")
    assert manquants(racine) == []


def test_un_fichier_illisible_ne_fait_pas_echouer_le_controle(tmp_path: Path) -> None:
    """Un fichier qui ne compile pas est le probleme d'un AUTRE controle.

    Ici, il doit etre ignore sans bruit : un controle de dependances qui plante sur du code
    casse deviendrait un controle qu'on n'ose plus lancer.
    """
    racine = _projet(tmp_path, "import paquet_fantome_xyz\n", PYPROJECT_SANS_DEPENDANCE)
    (tmp_path / "tests" / "test_casse.py").write_text("def (:\n", encoding="utf-8")
    assert [m.paquet for m in manquants(racine)] == ["paquet_fantome_xyz"]


def test_un_dossier_de_tests_absent_n_est_pas_un_defaut(tmp_path: Path) -> None:
    assert manquants(tmp_path) == []


# --------------------------------------------------------------------------- #
# 3. Le projet lui-meme
# --------------------------------------------------------------------------- #


def test_les_dependances_des_tests_du_projet_sont_declarees() -> None:
    """Le controle le plus important : c'est CE depot qui doit etre installable tel quel."""
    trouves = manquants(PROJET)
    assert not trouves, "dependance non declaree :\n  " + "\n  ".join(str(m) for m in trouves)


def test_le_controle_voit_bien_les_imports_reels_du_projet() -> None:
    """« Aucun manquant » ne doit pas pouvoir signifier « rien de lu ».

    Sinon le controle deviendrait vert le jour ou il cesserait de lire les fichiers, sans
    que rien ne le signale. On verifie donc les deux cotes : ce qui est vu, et ce qui est
    declare.
    """
    vus = imports_externes(PROJET)
    assert "pytest" in vus, f"pytest devrait etre vu dans les tests : {sorted(vus)}"
    assert "yaml" in vus, (
        "`yaml` est importe par tests/test_hooks.py : s'il disparait de la liste, c'est le "
        f"controle qui est aveugle, pas la dependance qui est inutile ({sorted(vus)})"
    )
    declares = declarations(PROJET)
    assert {"pytest", "pyyaml"} <= declares


def test_la_CI_installe_l_extra_et_non_une_liste_recopiee() -> None:
    """Une liste recopiee a la main diverge — c'est exactement ce qui s'est produit.

    L'exemple de CI affirmait « aucune autre dependance n'est necessaire » alors que les
    tests importent `yaml`. Installer `-e '.[dev]'` fait de `pyproject.toml` la source
    unique.
    """
    ci = (PROJET / ".github" / "ci.yml.example").read_text(encoding="utf-8")
    assert "pip install -e '.[dev]'" in ci, "la CI doit installer l'extra declare"
    assert "Aucune autre dependance n'est necessaire" not in ci, (
        "l'affirmation fausse est encore dans la CI"
    )


def test_la_commande_signale_les_dependances_non_declarees(
    tmp_path: Path, capsys, monkeypatch
) -> None:
    """Le controle est branche sur `jio scan`, et il fait echouer le scan.

    L'import du module de controle se fait DANS `cmd_scan` : un test qui patche le module
    importe ne suffit donc pas. On patche la fonction resolue par le module lui-meme, ce
    qui couvre les deux chemins.
    """
    import jio.verify.dependances as module

    racine = _projet(tmp_path, "import paquet_fantome_xyz\n", PYPROJECT_SANS_DEPENDANCE)
    monkeypatch.setattr(
        module, "manquants",
        lambda *a, **k: [module.Manque("paquet_fantome_xyz", "paquet-fantome-xyz",
                                       ("tests/test_x.py",))],
    )
    assert main(["scan", str(racine), "--no-learn"]) == 1
    sortie = capsys.readouterr().out
    assert "DEPENDANCE(S) DES TESTS NON DECLAREE(S)" in sortie
    assert "paquet_fantome_xyz" in sortie
