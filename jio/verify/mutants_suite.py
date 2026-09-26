"""Score de mutation de NOTRE PROPRE suite de tests — l'auto-mesure qui manquait.

Le probleme
-----------
La porte de mutation (`jio.verify.mutation`) verifie qu'une *specification* sait
distinguer un artefact correct d'un artefact faux. Elle ne dit rien de la suite de
tests du depot : elle-meme pourrait etre une decoration. Or tout ce depot affirme des
choses (« aucune erreur ne passe silencieusement », « un faux positif est un bug de
l'audit ») et ces affirmations sont tenues par des tests. Un test qui ne peut pas
echouer ne tient rien.

La reponse
----------
On mutte le code du depot — comparaisons, bornes, constantes booleennes, retours
anticipes — dans une COPIE de travail, puis on relance les tests qui visent le fichier
mute. Un mutant SURVIT si la suite passe encore : le depot n'a alors aucune preuve de
la ligne mutee. Le score est la proportion de mutants tues, et chaque survivant est
liste avec son emplacement et l'etiquette de la mutation.

Ce qui est mesure, c'est le depot lui-meme : le terrain de preuve, c'est lui.

Honte du choix des tests
------------------------
Faire tourner la suite entiere (plusieurs minutes) pour chaque mutant est hors budget.
On selectionne donc les fichiers de test qui MENTIONNENT le module vise (import ou nom
du fichier) : une heuristique, DECLAREE, et un survivant peut venir de la selection
plutot que du code. Le rapport le dit, et l'echappatoire est symetrique : `--tout`
fait tourner la suite complete, au prix du temps.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from .mutation import mutate

__all__ = ["MutantDeLaSuite", "RapportSuite", "mesurer"]

#: Dossiers jamais copies dans la copie de travail : ils ne servent a rien a pytest et ils
#: pesent l'essentiel du poids (l'environnement virtuel et l'historique git).
_IGNORES = shutil.ignore_patterns(
    ".venv", ".git", ".jio", "__pycache__", ".pytest_cache", "*.pyc", "evidence"
)


#: Familles de mutation, lues sur l'etiquette produite par `mutate`. La distinction sert a
#: lire le score sans se raconter d'histoires : un mutant de CONSTANTE (un plafond, un
#: budget) survit souvent sans consequence observable — il dit « cette borne n'est pas
#: testee », pas « cette ligne n'est pas prouvee ». Un mutant de COMPARAISON ou de BOOLEEN
#: dit beaucoup plus : la logique elle-meme n'est pas tenue.
_FAMILLES = (
    ("booleen", "booleen"),
    ("comparaison", "comparaison"),
    ("operateur", "comparaison"),
    ("return", "retour"),
    ("constante", "constante"),
    ("borne", "constante"),
)


def famille(label: str) -> str:
    """Famille d'un mutant, d'apres son etiquette (voir `_FAMILLES`)."""
    minuscule = label.lower()
    for motif, nom in _FAMILLES:
        if minuscule.startswith(motif) or motif in minuscule:
            return nom
    return "autre"


@dataclass
class MutantDeLaSuite:
    fichier: Path
    label: str
    tue: bool
    preuve: str = ""

    @property
    def famille(self) -> str:
        return famille(self.label)


@dataclass
class RapportSuite:
    mutants: list[MutantDeLaSuite] = field(default_factory=list)
    note: str = ""
    tests_lances: int = 0
    duree_s: float = 0.0

    @property
    def tues(self) -> int:
        return sum(1 for m in self.mutants if m.tue)

    @property
    def survivants(self) -> list[MutantDeLaSuite]:
        return [m for m in self.mutants if not m.tue]

    @property
    def score(self) -> float:
        """Part des mutants tues. Un rapport vide vaut 0 : rien n'a ete prouve."""
        if not self.mutants:
            return 0.0
        return self.tues / len(self.mutants)


def _tests_pour(racine: Path, fichier: Path, plafond: int) -> list[str]:
    """Fichiers de test qui mentionnent le module vise (heuristique DECLAREE).

    On ne cherche pas une couverture exacte : on cherche a lancer les tests qui ont une
    chance de toucher ce fichier. Le nom du module et son chemin relatif sont les deux
    formes qu'on trouve dans un depot reel (`from jio.verify import linters`,
    `jio/verify/linters.py`).
    """
    module = fichier.relative_to(racine).with_suffix("")
    motif = str(module).replace("/", ".")
    court = fichier.stem
    # Un fichier de test qui IMPORTE le module directement a plus de chances de le toucher
    # qu'un fichier qui cite son nom en passant. L'ordre alphabetique ignorait cette
    # difference, et un mutant survivait pour cette seule raison : mesure faite, un test
    # couvrant `ImportProblem` n'etait pas selectionne parce que trois autres noms de
    # fichiers passaient avant lui. On CLASSE par pertinence, puis par nom.
    candidats: list[tuple[int, str]] = []
    for test in sorted((racine / "tests").rglob("test_*.py")):
        texte = test.read_text(encoding="utf-8", errors="replace")
        points = 0
        if motif in texte:
            points += 3
        if f"{court}.py" in texte:
            points += 1
        if f" {court} " in texte:
            points += 1
        if points:
            candidats.append((-points, str(test)))
    candidats.sort()
    return [nom for _, nom in candidats[:plafond]]


def mesurer(
    racine: Path,
    *,
    fichiers: Sequence[Path] | None = None,
    budget_par_fichier: int = 2,
    plafond_tests: int = 6,
    timeout: int = 300,
    tous_les_tests: bool = False,
    python: str = "",
) -> RapportSuite:
    """Mutte le depot dans une copie de travail et mesure ce que la suite attrape.

    Rien n'est ecrit dans le depot : la copie vit dans un dossier temporaire, et la
    mutation est appliquee fichier par fichier, puis effacee.
    """
    import time

    debut = time.monotonic()
    python = python or sys.executable
    if fichiers is None:
        fichiers = sorted((racine / "jio").rglob("*.py"))
    # Un fichier sans mutation POSSIBLE (`__init__.py` vide, tableau de constantes) ne
    # prouve rien : il est ecarte, et l'ecart est ECRIT. Un seuil de taille cache (`> 200
    # octets`) avait d'abord ete pose ici — c'est exactement le genre d'exclusion muette que
    # ce depot s'interdit, et elle se voyait : le test de ce module ne mesurait plus rien.
    utiles: list[tuple[Path, list]] = []
    sans_mutation: list[str] = []
    for fichier in fichiers:
        if not fichier.is_file():
            continue
        mutants = mutate(fichier.read_text(encoding="utf-8"), budget=budget_par_fichier)
        if mutants:
            utiles.append((fichier, mutants))
        else:
            sans_mutation.append(str(fichier.relative_to(racine)))

    rapport = RapportSuite()
    if sans_mutation:
        rapport.note = (
            f"{len(sans_mutation)} fichier(s) sans mutation possible "
            f"({', '.join(sorted(sans_mutation)[:4])}"
            + (" ..." if len(sans_mutation) > 4 else "")
            + ") : rien n'y peut changer le comportement. Ce n'est pas une mesure manquante."
        )
    if not utiles:
        rapport.note = "aucun fichier mutable dans la selection : rien n'a ete mesure"
        return rapport

    travail = Path(tempfile.mkdtemp(prefix="jio-mutants-"))
    copie = travail / racine.name
    try:
        shutil.copytree(racine, copie, ignore=_IGNORES, symlinks=False)
        for fichier, mutants in utiles:
            original = fichier.read_text(encoding="utf-8")
            relatif = fichier.relative_to(racine)
            cible = copie / relatif
            tests = (
                ["tests"]
                if tous_les_tests
                else _tests_pour(copie, cible, plafond_tests)
            )
            if not tests:
                rapport.note = (
                    (rapport.note + " " if rapport.note else "")
                    + f"aucun test ne mentionne {relatif} : le mutant est compte "
                    "SURVIVANT (rien ne peut le tuer). Ajouter un test, ou dire pourquoi "
                    "il n'y en a pas."
                )
            for mutant in mutants:
                cible.write_text(mutant.source, encoding="utf-8")
                commande = [python, "-m", "pytest", "-q", "-x", "--no-header", *tests]
                try:
                    resultat = subprocess.run(
                        commande, cwd=copie, capture_output=True, text=True, timeout=timeout
                    )
                    sortie = (resultat.stdout or "") + (resultat.stderr or "")
                    tue = resultat.returncode != 0
                except subprocess.TimeoutExpired:
                    # Un mutant qui ne termine pas a fait BOUCLER la suite : c'est un
                    # kill, pas un survivant — mais il faut le dire, parce qu'un test qui
                    # part en boucle coute le temps de tout le monde.
                    sortie, tue = f"delai depasse ({timeout} s) : la suite a boucle", True
                if tue:
                    preuve = next(
                        (l.strip() for l in reversed(sortie.splitlines()) if l.strip()), ""
                    )[:160]
                else:
                    preuve = "la suite passe AVEC le mutant : aucune preuve de cette ligne"
                rapport.mutants.append(
                    MutantDeLaSuite(relatif, mutant.label, tue, preuve)
                )
                rapport.tests_lances += 1
            cible.write_text(original, encoding="utf-8")
    finally:
        shutil.rmtree(travail, ignore_errors=True)
    rapport.duree_s = time.monotonic() - debut
    return rapport


def formater(rapport: RapportSuite) -> str:
    """Rapport lisible : le score, les survivants, et ce qu'il faut en faire."""
    lignes = [
        f"  SCORE DE MUTATION DE LA SUITE  ·  {rapport.tues}/{len(rapport.mutants)} "
        f"mutants tues  ({rapport.score:.0%})  ·  {rapport.duree_s:.0f} s",
        "    Lecture : un mutant SURVIVANT est une ligne du depot qu'aucun test ne protege.",
        "    Ce n'est pas une accusation contre le code : c'est une preuve manquante.",
    ]
    if rapport.note:
        lignes.append(f"    note : {rapport.note}")
    for mutant in rapport.survivants[:12]:
        lignes.append(f"    SURVIVANT  {mutant.fichier}  [{mutant.label}]")
    if len(rapport.survivants) > 12:
        lignes.append(f"    ... et {len(rapport.survivants) - 12} autre(s)")
    if not rapport.survivants:
        lignes.append("    aucun survivant : chaque mutation mesuree a ete attrapee.")
    # Le detail par famille : c'est la lecture honnete d'un score global. Un score bas
    # fait de constantes de plafond n'a pas la meme significance qu'un score bas fait de
    # comparaisons et de booleens.
    if rapport.mutants:
        par_famille: dict[str, list[int]] = {}
        for mutant in rapport.mutants:
            tue, total = par_famille.get(mutant.famille, [0, 0])
            par_famille[mutant.famille] = [tue + (1 if mutant.tue else 0), total + 1]
        detail = " · ".join(
            f"{nom} {tues}/{total}"
            for nom, (tues, total) in sorted(par_famille.items())
        )
        lignes.append(f"    par famille : {detail}")
    return "\n".join(lignes)
