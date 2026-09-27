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


#: Mutants declarees EQUIVALENTS : (chemin relatif, etiquette) -> la raison, en clair.
#:
#: Certains mutants ne changent RIEN au comportement : le code retire est repris juste
#: apres par un autre chemin (un `except`, une valeur par defaut, une branche qui rend la
#: meme chose). Ces mutants ne peuvent pas etre tues — aucun test ne peut distinguer deux
#: programmes identiques — et ecrire un test pour les « tuer » serait du theatre : il
#: n'echouerait jamais sur autre chose que la mutation elle-meme.
#:
#: La reponse de ce depot n'est ni de les cacher, ni d'inventer un test : c'est de les
#: DECLARER, avec la raison, et de le dire dans le rapport. Une declaration dont le mutant
#: a disparu (ou dont l'etiquette a change) devient un FANTOME, et un test la refuse : une
#: raison ecrite pour un mutant qui n'existe plus est une raison qui ment.
EQUIVALENTS: dict[tuple[str, str], str] = {
    ("jio/artifacts/write_guard.py", "bloc conditionnel vide"): (
        "le `return {}` retire (registre absent) est rattrape par le `except OSError` qui "
        "suit : verifie sur cinq cas (absent, valide, corrompu, sans cle, mauvais type), "
        "le comportement rendu est identique dans les cinq."
    ),
}


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
    #: Raison ECRITE quand le mutant est declare equivalent (voir `EQUIVALENTS`).
    equivalent: str = ""
    #: Vrai quand le survivant a ete rejoue sur la suite ENTIERE et qu'il est mort la : le
    #: score brut le comptait comme survivant, mais la selection de tests avait simplement
    #: manque le fichier qui le tuait. Un survivant APPARENT n'est pas un manque de test.
    tue_par_suite_complete: bool = False

    @property
    def famille(self) -> str:
        return famille(self.label)

    @property
    def survivant_reel(self) -> bool:
        """Un survivant qui n'est PAS declare equivalent : c'est lui qui demande un test."""
        return not self.tue and not self.equivalent

    @property
    def survivant_confirme(self) -> bool:
        """Un survivant qui survit MEME a la suite entiere : la preuve manque vraiment."""
        return self.survivant_reel and not self.tue_par_suite_complete

    @property
    def survivant_apparent(self) -> bool:
        """Un survivant tue par la suite entiere : il vient de la SELECTION, pas du code."""
        return self.survivant_reel and self.tue_par_suite_complete


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
        """Survivants NON declares equivalents : chacun demande un test, ou une raison."""
        return [m for m in self.mutants if m.survivant_reel]

    @property
    def equivalents(self) -> list[MutantDeLaSuite]:
        """Survivants declares equivalents AVEC leur raison : ils ne comptent pas au score."""
        return [m for m in self.mutants if m.equivalent]

    @property
    def apparents(self) -> list[MutantDeLaSuite]:
        """Survivants tues par la suite COMPLETE : la selection avait manque le fichier."""
        return [m for m in self.mutants if m.survivant_apparent]

    @property
    def confirmes(self) -> list[MutantDeLaSuite]:
        """Survivants qui survivent a tout : chacun demande un test, ou une raison ecrite."""
        return [m for m in self.mutants if m.survivant_confirme]

    @property
    def score_verifie(self) -> float:
        """Le score APRES verification de la selection : les survivants apparents comptent tues.

        Les deux scores ne disent pas la meme chose, et c'est pour cela qu'ils sont separes :
        `score` mesure la suite TELLE QU'ELLE EST LANCEE par l'outil, `score_verifie` mesure ce
        que la suite sait faire quand on lui donne tous ses fichiers. Le second est toujours
        superieur ou egal au premier, et l'ecart EST l'erreur de la selection.
        """
        if not self.mutants:
            return 0.0
        tues = sum(1 for m in self.mutants if m.tue or m.survivant_apparent)
        return tues / len(self.mutants)

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
                # Le survivant est rejoue sur la suite ENTIERE, et seulement lui. Deux natures de
                # survivant se ressemblaient dans le rapport :
                #   * APPARENT  : la selection ne lancait pas le fichier qui le tuait ;
                #   * CONFIRME  : aucun test du depot ne distingue cette ligne.
                # Le premier dit « mon heuristique a un trou » (et c'est un fait sur l'OUTIL),
                # le second dit « cette ligne n'est pas prouvee » (et c'est un fait sur le CODE).
                # Les confondre donnait un score qui melangeait les deux — donc un chiffre qu'on
                # ne peut pas corriger. Le cout est nul en pratique : on ne rejoue QUE les
                # survivants, qui sont l'exception.
                tue_par_suite = False
                if not tue and not tous_les_tests:
                    try:
                        complet = subprocess.run(
                            [python, "-m", "pytest", "-q", "-x", "--no-header", "tests"],
                            cwd=copie, capture_output=True, text=True, timeout=timeout,
                        )
                        tue_par_suite = complet.returncode != 0
                    except subprocess.TimeoutExpired:
                        tue_par_suite = True
                    rapport.tests_lances += 1
                rapport.mutants.append(
                    MutantDeLaSuite(
                        relatif,
                        mutant.label,
                        tue,
                        preuve,
                        equivalent="" if tue else EQUIVALENTS.get(
                            (str(relatif), mutant.label), ""
                        ),
                        tue_par_suite_complete=tue_par_suite,
                    )
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

    # Les deux natures de survivant, separees. Un score qui les melange ne se corrige pas :
    # on ne sait pas s'il faut ecrire un test (code) ou elargir la selection (outil).
    if rapport.apparents:
        lignes.append(
            f"    {len(rapport.apparents)} survivant(s) APPARENT(S) : tues par la suite COMPLETE, "
            "la selection de tests avait manque le fichier. Fait sur l'OUTIL, pas sur le code :"
        )
        for mutant in rapport.apparents:
            lignes.append(f"      apparent   {mutant.fichier}  [{mutant.label}]")
        lignes.append(
            f"    -> score apres verification de la selection : "
            f"{rapport.tues + len(rapport.apparents)}/{len(rapport.mutants)} "
            f"({rapport.score_verifie:.0%}). L'ecart avec {rapport.score:.0%} EST l'erreur de "
            "l'heuristique."
        )
    for mutant in rapport.confirmes:
        lignes.append(f"    SURVIVANT  {mutant.fichier}  [{mutant.label}]")
    if not rapport.survivants:
        lignes.append("    aucun survivant : chaque mutation mesuree a ete attrapee.")
    for mutant in rapport.equivalents:
        # Une equivalence DECLAREE n'est pas un oubli : elle porte sa raison, ici, dans le
        # rapport — pas dans la tete de quelqu'un.
        lignes.append(
            f"    EQUIVALENT DECLARE  {mutant.fichier}  [{mutant.label}]"
        )
        lignes.append(f"      raison : {mutant.equivalent}")
    # Le detail par famille : c'est la lecture honnete d'un score global. Un score bas
    # fait de constantes de plafond n'a pas la meme significance qu'un score bas fait de
    # comparaisons et de booleens.
    if rapport.mutants:
        # Compte APRES verification de la selection : c'est la lecture qui n'entre pas en
        # contradiction avec le score corrige juste au-dessus. Un detail par famille calcule
        # sur le score brut afficherait « constante 0/1 » sous une ligne annoncant 100 %.
        par_famille: dict[str, list[int]] = {}
        for mutant in rapport.mutants:
            tue, total = par_famille.get(mutant.famille, [0, 0])
            mort = mutant.tue or mutant.survivant_apparent
            par_famille[mutant.famille] = [tue + (1 if mort else 0), total + 1]
        detail = " · ".join(
            f"{nom} {tues}/{total}"
            for nom, (tues, total) in sorted(par_famille.items())
        )
        lignes.append(f"    par famille : {detail}")
    return "\n".join(lignes)
