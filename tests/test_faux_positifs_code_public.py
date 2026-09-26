"""Mesure de `jio scan` sur du code public : quatre faux positifs, et un vrai defaut.

Le README annoncait un chiffre manquant : « de nouvelles regles dans `jio scan` sans mesure
sur le corpus de paquets publics — qui est ce qui decide si une regle accuse a tort ». Ce
fichier est cette mesure, transformee en non-regression.

Protocole : quatre bibliotheques publiques installees depuis PyPI (`click` 8.5.0,
`packaging` 26.3, `pyparsing` 3.3.3, `attrs` 26.1.0), passees a `jio scan`. Resultat avant
correction : **trois paquets sur quatre declares fautifs** — 5 problemes pour `packaging`,
5 pour `pyparsing`, 0 pour `click` et `attrs`.

Aucun de ces problemes n'etait un defaut du code. Quatre causes, toutes de la meme famille :
**l'analyseur ne pouvait pas conclure, et il accusalit.**

| Cause reelle | Ce qui etait rapporte |
|---|---|
| une fixture pytest n'est pas appelable directement | 1 probleme `[A-002]` (appel direct de `mesures`) |
| une classe a fabriques refuse la construction | 5 problemes `[C-001..005]` (`VersionRange`) |
| un exemple attend une traceback, dont le nom de module differe | 2 problemes `[A-003]`, `[C-001]` |
| un exemple ecrit dans un flux lie a l'import (`file=sys.stdout`) | 1 probleme `[A-003]` |
| `import *` : l'analyseur ne peut pas suivre les noms | 5 problemes `[ruff:F403]` |
| un nom vient d'un `from .core import *` dans le module voisin | 2 problemes `[IMPORT]` |

Apres correction : `click`, `packaging`, `attrs` et **ce depot** rendent **0 probleme**, et
`pyparsing` en rend **un seul** — un vrai :

    [ruff:F401] `.unicode.UnicodeRangeList` imported but unused

Verifie a la main : `UnicodeRangeList` est un alias de type public de `pyparsing.unicode`,
importe dans `__init__.py`, et absent des 171 noms de `__all__`. Le nom est donc visible
(`pyparsing.UnicodeRangeList`) sans etre reexporte. C'est exactement ce qu'un audit doit
rendre : peu de lignes, toutes vraies.

Ces tests reproduisent les FORMES du code reel, sans dependre des paquets : ils doivent
passer sur une machine sans reseau.
"""

from __future__ import annotations

import ast
from pathlib import Path

from jio.verify.autocheck import _instantiable_without_args, derive, _lie_la_sortie_standard
from jio.verify.imports import check_project
from jio.verify.linters import LIMITES_DE_L_ANALYSE, LintFinding

# --------------------------------------------------------------------------- #
# 1. La classe a fabriques (`packaging.ranges.VersionRange`)
# --------------------------------------------------------------------------- #

#: Forme exacte du code public : `__new__` dont le corps est un `raise` inconditionnel.
CLASSE_A_FABRIQUES = '''
class VersionRange:
    """Un intervalle de versions.

    >>> SpecifierSet(">=1.0").to_range()
    Traceback (most recent call last):
        ...
    TypeError: cannot create 'VersionRange' instances directly
    """

    def __new__(cls, *args, **kwargs):
        raise TypeError(
            "cannot create 'VersionRange' instances directly; use "
            "SpecifierSet.to_range(), VersionRange.full() instead"
        )
'''


def test_une_classe_a_fabriques_n_est_pas_instanciee_de_force() -> None:
    """Le refus est une decision d'architecture, ecrite en clair. Ce n'est pas un defaut."""
    derives = derive(CLASSE_A_FABRIQUES, entrypoint="VersionRange")
    motifs = " ".join(derives.spec.under_specified)
    assert "fabriques" in motifs, motifs
    # Aucune regle C-001 « s'instancie sans argument » : elle serait fausse par construction.
    assert not any("s'instancie" in regle.statement for regle in derives.spec.rules)

    arbre = ast.parse(CLASSE_A_FABRIQUES)
    classe = next(n for n in arbre.body if isinstance(n, ast.ClassDef))
    possible, raison = _instantiable_without_args(classe)
    assert not possible and "fabriques" in raison


def test_un_raise_CONDITIONNEL_ne_suspend_pas_la_regle() -> None:
    """Le doute profite a l'artefact, pas au silence : un `raise` sous condition depend d'un
    argument, donc il ne dit rien de la construction a vide. La classe reste auditee."""
    source = (
        "class Machine:\n"
        "    def __init__(self, mode: str = 'ok'):\n"
        "        if mode == 'ko':\n"
        "            raise ValueError('mode invalide')\n"
        "        self.mode = mode\n"
    )
    derives = derive(source, entrypoint="Machine")
    assert any("s'instancie" in regle.statement for regle in derives.spec.rules), (
        "une classe normale a ete retiree de l'audit par un raise conditionnel"
    )


# --------------------------------------------------------------------------- #
# 2. La sortie standard liee a l'import (`pyparsing.show_best_practices`)
# --------------------------------------------------------------------------- #


def _fonction(source: str) -> ast.FunctionDef:
    arbre = ast.parse(source)
    return next(n for n in arbre.body if isinstance(n, ast.FunctionDef))


def test_une_sortie_liee_a_l_import_est_reconnue() -> None:
    """`def f(file=sys.stdout)` evalue la valeur par defaut a la DEFINITION.

    Doctest remplace `sys.stdout` pendant l'execution : l'exemple ecrit dans l'ancien flux,
    doctest ne voit rien et conclut « Got nothing ». C'est la mesure qui est en cause.
    """
    liee = _fonction("import sys\n\ndef f(file=sys.stdout):\n    print('x', file=file)\n")
    assert _lie_la_sortie_standard(liee)

    sur = _fonction("def g(file=None):\n    print('x', file=file)\n")
    assert not _lie_la_sortie_standard(sur), "un flux passe explicitement est capturable"


def test_le_controle_accepte_une_CLASSE() -> None:
    """Regression attrapee par la mesure : `derive` levait

        'ClassDef' object has no attribute 'args'

    parce que le controle etait appele avec une classe sans accepter ce cas. Un controle qui
    plante sur une moitie de son entree fait echouer l'audit du fichier entier.
    """
    arbre = ast.parse(
        "import sys\n"
        "class Doc:\n"
        "    def __init__(self):\n"
        "        pass\n"
        "    def affiche(self, file=sys.stdout):\n"
        "        print(self, file=file)\n"
    )
    classe = next(n for n in arbre.body if isinstance(n, ast.ClassDef))
    assert _lie_la_sortie_standard(classe) is True

    hors = next(n for n in ast.parse("class Simple:\n    pass\n").body
                if isinstance(n, ast.ClassDef))
    assert _lie_la_sortie_standard(hors) is False


def test_un_exemple_a_traceback_ne_fait_pas_echouer_l_audit() -> None:
    """Le nom qualifie de l'exception depend du nom du module — synthetique ici.

    Doctest sait comparer ce cas (`IGNORE_EXCEPTION_DETAIL`) ; il fallait le lui demander.
    Et il fallait RECONSTRUIRE les objets de test : rejouer le meme `DocTest` levait
    `NameError: name 'Specifier' is not defined`, une raison qui n'avait rien a voir avec ce
    qu'on verifiait.
    """
    source = (
        "class Garde:\n"
        '    """\n'
        "    >>> Garde('nope')\n"
        "    Traceback (most recent call last):\n"
        "        ...\n"
        "    __main__.Mauvais: specifieur invalide\n"
        '    """\n'
        "\n"
        "    def __init__(self, texte: str = 'ok'):\n"
        "        if texte != 'ok':\n"
        "            raise Mauvais('specifieur invalide')\n"
        "        self.texte = texte\n"
        "\n"
        "\n"
        "class Mauvais(ValueError):\n"
        "    pass\n"
    )
    derives = derive(source, entrypoint="Garde")
    assert derives.verifiable
    assert "stdlib" not in " ".join(derives.spec.under_specified)


# --------------------------------------------------------------------------- #
# 3. `import *` : une limite de l'analyseur, pas une faute du code
# --------------------------------------------------------------------------- #


def test_import_etoile_est_une_limite_et_non_une_accusation() -> None:
    """Mesure : `pyparsing` etait declare fautif cinq fois, uniquement sur `F403`.

    Le message de l'outil le dit lui-meme : « unable to detect undefined names ». Accuser un
    projet parce que l'ANALYSEUR n'a pas su suivre les noms est un faux positif.
    """
    etoile = LintFinding(path=Path("x.py"), line=1, rule="ruff:F403",
                         message="`from .core import *` used")
    assert etoile.limite_de_l_analyse, "F403 doit declarer une limite"
    assert "limite de l'outil" in etoile.limite_de_l_analyse

    indefini = LintFinding(path=Path("x.py"), line=2, rule="ruff:F405",
                           message="`nom` may be undefined")
    assert indefini.limite_de_l_analyse, "F405 doit declarer une limite"

    # Un vrai bug garde son statut : le filtre ne doit pas devenir un trou.
    vrai = LintFinding(path=Path("x.py"), line=3, rule="ruff:F821",
                       message="undefined name `truc`")
    assert not vrai.limite_de_l_analyse, "F821 est une preuve de defaut, pas une limite"
    assert not LintFinding(path=Path("x.py"), line=4, rule="ruff:F401",
                           message="import inutilise").limite_de_l_analyse


def test_le_jeu_de_limites_reste_etroit() -> None:
    """Un jeu de limites qui s'elargit transforme l'audit en decor."""
    assert set(LIMITES_DE_L_ANALYSE) == {"F403", "F405"}, sorted(LIMITES_DE_L_ANALYSE)


# --------------------------------------------------------------------------- #
# 4. Un nom qui vient d'un `from X import *` n'est pas un nom absent
# --------------------------------------------------------------------------- #


def _projet(tmp_path, fichiers: dict[str, str]):
    for nom, contenu in fichiers.items():
        chemin = tmp_path / nom
        chemin.parent.mkdir(parents=True, exist_ok=True)
        chemin.write_text(contenu, encoding="utf-8")
    return sorted(tmp_path.rglob("*.py")), tmp_path


def test_un_nom_venu_d_une_etoile_n_est_pas_absent(tmp_path) -> None:
    """Mesure sur `pyparsing` : `common.py` fait `from .helpers import DelimitedList`, et
    `helpers.py` fait `from .core import *`. Le nom existe a l'execution, reste invisible a
    l'analyse : le verificateur accusait deux fois une bibliotheque correcte."""
    fichiers, racine = _projet(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/core.py": "class DelimitedList:\n    pass\n",
        "pkg/helpers.py": "from .core import *\n",
        "pkg/common.py": "from .helpers import DelimitedList\n\nx = DelimitedList\n",
    })
    assert check_project(fichiers, racine) == []


def test_le_meme_nom_absent_sans_etoile_reste_accuse(tmp_path) -> None:
    """Contre-epreuve : sans `import *`, l'absence est une vraie rupture."""
    fichiers, racine = _projet(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/core.py": "class Autre:\n    pass\n",
        "pkg/helpers.py": "from .core import Autre\n",
        "pkg/common.py": "from .helpers import DelimitedList\n\nx = DelimitedList\n",
    })
    trouves = check_project(fichiers, racine)
    assert len(trouves) == 1
    assert "DelimitedList" in trouves[0].message


def test_l_etoile_est_vue_meme_dans_un_try(tmp_path) -> None:
    """Un `from x import *` ecrit sous `try:` fournit tout autant de noms."""
    fichiers, racine = _projet(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/core.py": "class Chose:\n    pass\n",
        "pkg/helpers.py": "try:\n    from .core import *\nexcept Exception:\n    pass\n",
        "pkg/common.py": "from .helpers import Chose\n\nx = Chose\n",
    })
    assert check_project(fichiers, racine) == []
