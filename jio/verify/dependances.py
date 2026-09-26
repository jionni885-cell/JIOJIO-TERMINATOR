"""Une suite de tests qui importe un paquet non declare rend la CI rouge sur un clone neuf.

Probleme resolu
---------------
Defaut reel, mesure sur ce depot : la CI installe `pytest` et `ruff`, et son commentaire
affirmait « aucune autre dependance n'est necessaire ». Or `tests/test_hooks.py` importe
`yaml` : sur un clone neuf, `python -m pytest -q` echouait avec `ModuleNotFoundError: No
module named 'yaml'` — deux tests rouges, dans le fichier meme qui verifie les hooks.

Le defaut n'etait pas le `import yaml` : c'etait qu'AUCUN controle ne reliait ce que les
tests utilisent a ce qui est declare. Une dependance manquante ne se voit que sur une
machine ou elle manque — c'est-a-dire jamais sur celle du developpeur, qui l'a installee
un jour pour autre chose et l'a oubliee.

Regle
-----
Tout paquet importe par les tests doit etre :

  * la bibliotheque standard (`sys.stdlib_module_names`) ;
  * le projet lui-meme, ou un module local du depot ;
  * declare dans `pyproject.toml` (dependances ou extras) ;
  * ou installe explicitement par le fichier de CI.

Un import inconnu devient un defaut, avec le fichier qui l'importe : de quoi corriger, ou
de quoi declarer en connaissance de cause. Aucune heuristique : un nom stdlib est verifie
contre la table du langage, pas devine.

Ce que ce module ne fait PAS
----------------------------
Il ne verifie pas les VERSIONS (une borne fausse ne se voit qu'a l'installation) et ne
devine pas le nom de distribution derriere un nom d'import. Quand le nom d'import ne
correspond pas au nom du paquet — `yaml` vient de `PyYAML` — la correspondance doit etre
declaree explicitement dans :data:`CORRESPONDANCES`. Un alias oublie produit un faux
positif, jamais un faux negatif : le controle echoue dans le sens ou l'erreur est visible.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

#: Nom d'import -> nom de distribution, quand les deux different.
#:
#: Volontairement courte : on n'y met que ce qui est rencontre, pas une table exhaustive
#: recopiee d'ailleurs. Un paquet absent de cette table est signale, et c'est juste : le
#: nom d'import ne figure alors nulle part dans les declarations.
CORRESPONDANCES = {
    "yaml": "pyyaml",
    "pytest_cov": "pytest-cov",
    "bs4": "beautifulsoup4",
    "PIL": "pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "z3": "z3-solver",
    "hypothesis": "hypothesis",
}

#: Dossiers fouilles par defaut : ce qui s'execute pendant la CI.
DOSSIERS = ("tests",)


@dataclass(frozen=True)
class Manque:
    """Un paquet importe par les tests, declare nulle part."""

    paquet: str
    distribution: str
    fichiers: tuple[str, ...]

    def __str__(self) -> str:
        return (
            f"{self.paquet} (paquet `{self.distribution}`) importe par "
            + ", ".join(self.fichiers)
        )


def _normaliser(nom: str) -> str:
    """Nom de distribution comparable : minuscules, `_` et `.` ramenes a `-`.

    C'est la normalisation de PEP 503 : `PyYAML`, `pyyaml` et `py_yaml` designent le meme
    paquet. Sans elle, `import yaml` declare en `PyYAML` serait signale a tort.
    """
    return nom.strip().lower().replace("_", "-").replace(".", "-")


def _sans_contrainte(exigence: str) -> str:
    """`pytest>=8.0 ; python_version>'3.10'` -> `pytest`."""
    return _normaliser(exigence.split(";")[0].split("[")[0].split(">=")[0]
                       .split("<")[0].split("=")[0].split("~")[0].split("!")[0]
                       .split(" ")[0].strip())


def _paquet_importe(nom: str) -> str:
    return CORRESPONDANCES.get(nom, _normaliser(nom))


# --------------------------------------------------------------------------- #
# Ce que les tests importent
# --------------------------------------------------------------------------- #


def _modules_locaux(racine: Path) -> set[str]:
    """Noms importables depuis le depot lui-meme : paquets et modules a la racine."""
    locaux = set()
    if not racine.is_dir():
        return locaux
    for enfant in racine.iterdir():
        if enfant.name.startswith("."):
            continue
        if enfant.is_dir() and (enfant / "__init__.py").is_file():
            locaux.add(enfant.name)
        elif enfant.suffix == ".py" and enfant.name != "setup.py":
            locaux.add(enfant.stem)
    return locaux


def imports_externes(
    racine: Path, dossiers: tuple[str, ...] = DOSSIERS
) -> dict[str, tuple[str, ...]]:
    """`{paquet importe: (fichiers, ...)}` pour tout import NON stdlib et NON local.

    Les imports sont cherches partout dans l'arbre syntaxique, pas seulement en tete de
    fichier : un `import yaml` ecrit dans une fonction — c'est exactement le cas rencontre
    ici — doit compter autant qu'un import global.
    """
    locaux = _modules_locaux(racine)
    trouves: dict[str, set[str]] = {}
    for dossier in dossiers:
        base = racine / dossier
        if not base.is_dir():
            continue
        for fichier in sorted(base.rglob("*.py")):
            try:
                arbre = ast.parse(fichier.read_text(encoding="utf-8"), filename=str(fichier))
            except (SyntaxError, UnicodeDecodeError):
                # Un fichier illisible n'est pas un defaut de dependance : c'est un autre
                # controle qui doit le dire. On ne le compte ni en bien ni en mal.
                continue
            for noeud in ast.walk(arbre):
                if isinstance(noeud, ast.Import):
                    racines = [alias.name.split(".")[0] for alias in noeud.names]
                elif isinstance(noeud, ast.ImportFrom):
                    # Un import relatif (`from . import x`) est local par construction.
                    if noeud.level or not noeud.module:
                        continue
                    racines = [noeud.module.split(".")[0]]
                else:
                    continue
                for racine_import in racines:
                    if racine_import in sys.stdlib_module_names or racine_import in locaux:
                        continue
                    relatif = str(fichier.relative_to(racine))
                    trouves.setdefault(racine_import, set()).add(relatif)
    return {paquet: tuple(sorted(fichiers)) for paquet, fichiers in sorted(trouves.items())}


# --------------------------------------------------------------------------- #
# Ce qui est declare
# --------------------------------------------------------------------------- #


def _extras(racine: Path) -> set[str]:
    """Paquets declares dans `pyproject.toml` : dependances et extras."""
    fichier = racine / "pyproject.toml"
    if not fichier.is_file():
        return set()
    import tomllib

    donnees = tomllib.loads(fichier.read_text(encoding="utf-8"))
    projet = donnees.get("project", {})
    noms = {_sans_contrainte(exigence) for exigence in projet.get("dependencies", [])}
    for exigences in projet.get("optional-dependencies", {}).values():
        noms |= {_sans_contrainte(exigence) for exigence in exigences}
    return noms


def _installes_par_la_ci(racine: Path) -> set[str]:
    """Paquets installes par un fichier de CI du depot (`pip install ...`).

    La CI est un deuxieme endroit legitime ou declarer ce dont la suite a besoin : un
    projet qui installe ses outils explicitement dans son workflow n'a pas besoin de les
    mettre dans `pyproject.toml`. En revanche, une dependance declaree NULLE PART est un
    rouge qui attend son heure.
    """
    noms: set[str] = set()
    for motif in (".github/workflows/*.yml", ".github/workflows/*.yaml", ".github/*.yml"):
        for fichier in sorted(racine.glob(motif)):
            texte = fichier.read_text(encoding="utf-8", errors="replace")
            for ligne in texte.splitlines():
                nue = ligne.strip()
                if "pip install" not in nue and "pip3 install" not in nue:
                    continue
                morceaux = nue.split("pip install", 1)[1].split("pip3 install", 1)[-1]
                # On ignore les options (`--upgrade`) et on garde ce qui ressemble a un
                # nom de paquet : un nom, eventuellement une contrainte, eventuellement
                # un extra (`.[dev]`).
                for jeton in morceaux.replace("-e ", " ").split():
                    if jeton.startswith("-"):
                        continue
                    nom = _sans_contrainte(jeton)
                    if nom and nom not in {".", ".."} and not nom.startswith("."):
                        noms.add(nom)
                    # `.[dev]` : l'extra lui-meme est couvert par `_extras`.
    return noms


def declarations(racine: Path) -> set[str]:
    """Tout paquet declare, par `pyproject.toml` ou par la CI."""
    return _extras(racine) | _installes_par_la_ci(racine)


def manquants(racine: Path, dossiers: tuple[str, ...] = DOSSIERS) -> list[Manque]:
    """Les paquets importes par les tests et declares nulle part."""
    declares = declarations(racine)
    resultat = []
    for paquet, fichiers in imports_externes(racine, dossiers).items():
        distribution = _paquet_importe(paquet)
        if distribution in declares:
            continue
        resultat.append(Manque(paquet=paquet, distribution=distribution, fichiers=fichiers))
    return resultat
