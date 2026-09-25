"""Banc d'essai — taches verifiables avec **oracles caches**.

Chaque tache fournit :
  * un objectif en langage naturel,
  * une specification en regles enumerees (une par test),
  * une implementation **correcte**,
  * des **distracteurs** : des implementations fausses mais plausibles, du type
    de bug qu'un vrai modele produit vraiment (off-by-one, cas vide, division
    entiere, erreur silencieuse).

Les tests ne sont **jamais** dans le prompt. Ils vivent de l'autre cote de la
frontiere : c'est ce qui rend le banc honnete, et c'est aussi le principe des
« oracles caches » qui empeche l'agent de tricher.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

from ..core.types import Rule, RuleKind, Spec


@dataclass(frozen=True)
class Task:
    """Une tache du banc."""

    id: str
    objective: str
    entrypoint: str
    correct: str
    distractors: tuple[str, ...]
    checks: Mapping[str, str]      # rule_id -> source de test
    rules: tuple[Rule, ...]
    difficulty: str = "moyen"

    def spec(self) -> Spec:
        return Spec(mission=self.objective, rules=self.rules)

    def bank_entry(self) -> tuple[str, Sequence[str]]:
        return self.correct, self.distractors


def _rule(rid: str, statement: str, kind: RuleKind = RuleKind.PROPERTY) -> Rule:
    return Rule(id=rid, statement=statement, kind=kind)


# --------------------------------------------------------------------------- #
# Tache 1 — somme des pairs
# --------------------------------------------------------------------------- #

T_SUM_EVEN = Task(
    id="sum_even",
    objective=(
        "Ecrire une fonction `sum_even(nums)` qui renvoie la somme des nombres pairs "
        "d'une liste d'entiers. Une liste vide renvoie 0. Les nombres negatifs pairs comptent."
    ),
    entrypoint="sum_even",
    difficulty="facile",
    correct="""def sum_even(nums):
    return sum(n for n in nums if n % 2 == 0)
""",
    distractors=(
        # Bug classique : confusion pair/impair.
        """def sum_even(nums):
    return sum(n for n in nums if n % 2 == 1)
""",
        # Bug classique : oublie le filtre.
        """def sum_even(nums):
    return sum(nums)
""",
        # Bug classique : exclut les negatifs.
        """def sum_even(nums):
    return sum(n for n in nums if n > 0 and n % 2 == 0)
""",
    ),
    rules=(
        _rule("R-001", "Somme des pairs correcte sur le cas nominal"),
        _rule("R-002", "Liste vide renvoie 0", RuleKind.BOUNDARY),
        _rule("R-003", "Les entiers negatifs pairs sont inclus", RuleKind.BOUNDARY),
    ),
    checks={
        "R-001": "assert sum_even([1, 2, 3, 4, 5, 6]) == 12, f'nominal: {sum_even([1,2,3,4,5,6])} != 12'",
        "R-002": "assert sum_even([]) == 0, f'liste vide: {sum_even([])} != 0'",
        "R-003": "assert sum_even([-4, -3, 2]) == -2, f'negatifs pairs: {sum_even([-4,-3,2])} != -2'",
    },
)


# --------------------------------------------------------------------------- #
# Tache 2 — mediane
# --------------------------------------------------------------------------- #

T_MEDIAN = Task(
    id="median",
    objective=(
        "Ecrire `median(nums)` qui renvoie la mediane d'une liste de nombres. "
        "Pour un nombre pair d'elements, renvoyer la moyenne des deux valeurs centrales. "
        "Une liste vide doit lever ValueError."
    ),
    entrypoint="median",
    difficulty="moyen",
    correct="""def median(nums):
    if not nums:
        raise ValueError("median: liste vide")
    s = sorted(nums)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / 2
""",
    distractors=(
        # Bug classique : moyenne des deux centres avec division entiere.
        """def median(nums):
    s = sorted(nums)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) // 2
""",
        # Bug classique : pas de gestion du cas vide.
        """def median(nums):
    s = sorted(nums)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2
""",
        # Bug classique : oublie de trier.
        """def median(nums):
    n = len(nums)
    mid = n // 2
    return nums[mid] if n % 2 else (nums[mid - 1] + nums[mid]) / 2
""",
    ),
    rules=(
        _rule("R-001", "Mediane correcte pour un nombre impair d'elements"),
        _rule("R-002", "Mediane correcte pour un nombre pair d'elements", RuleKind.PROPERTY),
        _rule("R-003", "Liste vide leve ValueError", RuleKind.BOUNDARY),
        _rule("R-004", "La liste d'entree n'est pas supposee triee", RuleKind.PROPERTY),
    ),
    checks={
        "R-001": "assert median([3, 1, 2]) == 2, f'impair: {median([3,1,2])} != 2'",
        "R-002": "assert median([1, 2, 3, 4]) == 2.5, f'pair: {median([1,2,3,4])} != 2.5'",
        "R-003": (
            "ok = False\n"
            "try:\n"
            "    median([])\n"
            "except ValueError:\n"
            "    ok = True\n"
            "assert ok, 'liste vide: aucune ValueError levee'"
        ),
        "R-004": "assert median([5, 2, 9, 1, 7]) == 5, f'non trie: {median([5,2,9,1,7])} != 5'",
    },
)


# --------------------------------------------------------------------------- #
# Tache 3 — primalite
# --------------------------------------------------------------------------- #

T_IS_PRIME = Task(
    id="is_prime",
    objective=(
        "Ecrire `is_prime(n)` qui renvoie True si n est premier, False sinon. "
        "0 et 1 ne sont pas premiers. Les nombres negatifs ne sont pas premiers."
    ),
    entrypoint="is_prime",
    difficulty="facile",
    correct="""def is_prime(n):
    if n < 2:
        return False
    if n < 4:
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True
""",
    distractors=(
        # Bug classique : oublie n < 2.
        """def is_prime(n):
    if n < 4:
        return True
    if n % 2 == 0:
        return False
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    return True
""",
        # Bug classique : comparaison stricte i*i < n au lieu de <= n.
        # 4, 9, 25, 49 passent tous au travers — les carres parfaits.
        """def is_prime(n):
    if n < 2:
        return False
    i = 2
    while i * i < n:
        if n % i == 0:
            return False
        i += 1
    return True
""",
        # Bug classique : seuil sqrt.
        """def is_prime(n):
    if n < 2:
        return False
    limit = int(n ** 0.5)
    for i in range(2, limit):
        if n % i == 0:
            return False
    return True
""",
    ),
    rules=(
        _rule("R-001", "2 et 3 sont premiers"),
        _rule("R-002", "0 et 1 ne sont pas premiers", RuleKind.BOUNDARY),
        _rule("R-003", "9 et 4 (carres parfaits) ne sont pas premiers", RuleKind.BOUNDARY),
        _rule("R-004", "97 et 89 sont premiers"),
        _rule("R-005", "Les nombres negatifs ne sont pas premiers", RuleKind.BOUNDARY),
        _rule("R-006", "25 et 49 (carres parfaits de nombres premiers) non plus", RuleKind.BOUNDARY),
    ),
    checks={
        "R-001": "assert is_prime(2) and is_prime(3), 'faux: 2 et 3 sont premiers'",
        "R-002": "assert not is_prime(0) and not is_prime(1), 'faux: 0 et 1 ne sont pas premiers'",
        "R-003": "assert not is_prime(9) and not is_prime(4), 'faux: 9 et 4 ne sont pas premiers'",
        "R-004": "assert is_prime(97) and is_prime(89), 'faux: 97 et 89 sont premiers'",
        "R-005": "assert not is_prime(-7), 'faux: les negatifs ne sont pas premiers'",
        "R-006": "assert not is_prime(25) and not is_prime(49), 'faux: 25 et 49 ne sont pas premiers'",
    },
)


# --------------------------------------------------------------------------- #
# Tache 4 — analyse de duree
# --------------------------------------------------------------------------- #

T_PARSE_DURATION = Task(
    id="parse_duration",
    objective=(
        "Ecrire `parse_duration(text)` qui convertit '1h30m' en 5400 secondes, "
        "'45s' en 45, '2h' en 7200. Unites reconnues : h (heures), m (minutes), s (secondes). "
        "Une entree vide ou invalide leve ValueError."
    ),
    entrypoint="parse_duration",
    difficulty="difficile",
    correct="""import re

def parse_duration(text):
    if not text or not text.strip():
        raise ValueError("parse_duration: entree vide")
    pattern = re.fullmatch(r"\\s*((\\d+)h)?\\s*((\\d+)m)?\\s*((\\d+)s)?\\s*", text)
    if pattern is None or not any(pattern.group(i) for i in (2, 4, 6)):
        raise ValueError(f"parse_duration: format invalide {text!r}")
    hours = int(pattern.group(2) or 0)
    minutes = int(pattern.group(4) or 0)
    seconds = int(pattern.group(6) or 0)
    return hours * 3600 + minutes * 60 + seconds
""",
    distractors=(
        # Bug classique : renvoie 0 au lieu de lever (erreur silencieuse).
        """import re

def parse_duration(text):
    if not text:
        return 0
    pattern = re.fullmatch(r"\\s*((\\d+)h)?\\s*((\\d+)m)?\\s*((\\d+)s)?\\s*", text)
    if pattern is None:
        return 0
    return (int(pattern.group(2) or 0) * 3600
            + int(pattern.group(4) or 0) * 60
            + int(pattern.group(6) or 0))
""",
        # Bug classique : confond m et h.
        """import re

def parse_duration(text):
    if not text:
        raise ValueError("vide")
    m = re.fullmatch(r"((\\d+)h)?((\\d+)m)?((\\d+)s)?", text)
    if not m:
        raise ValueError("invalide")
    return (int(m.group(2) or 0) * 60
            + int(m.group(4) or 0) * 60
            + int(m.group(6) or 0))
""",
        # Bug classique : oublie les minutes seules.
        """import re

def parse_duration(text):
    if not text:
        raise ValueError("vide")
    total = 0
    for value, unit in re.findall(r"(\\d+)([hms])", text):
        if unit == "h":
            total += int(value) * 3600
        elif unit == "s":
            total += int(value)
    if total == 0:
        raise ValueError("invalide")
    return total
""",
    ),
    rules=(
        _rule("R-001", "'1h30m' vaut 5400 secondes"),
        _rule("R-002", "'45s' vaut 45 secondes", RuleKind.BOUNDARY),
        _rule("R-003", "'2h' vaut 7200 secondes"),
        _rule("R-004", "Une entree vide leve ValueError", RuleKind.BOUNDARY),
        _rule("R-005", "Une entree invalide leve ValueError", RuleKind.BOUNDARY),
    ),
    checks={
        "R-001": "assert parse_duration('1h30m') == 5400, f'1h30m -> {parse_duration(\"1h30m\")}'",
        "R-002": "assert parse_duration('45s') == 45, f'45s -> {parse_duration(\"45s\")}'",
        "R-003": "assert parse_duration('2h') == 7200, f'2h -> {parse_duration(\"2h\")}'",
        "R-004": (
            "ok = False\n"
            "try:\n"
            "    parse_duration('')\n"
            "except ValueError:\n"
            "    ok = True\n"
            "assert ok, 'entree vide: aucune ValueError levee (erreur silencieuse)'"
        ),
        "R-005": (
            "ok = False\n"
            "try:\n"
            "    parse_duration('abc')\n"
            "except ValueError:\n"
            "    ok = True\n"
            "assert ok, 'entree invalide: aucune ValueError levee'"
        ),
    },
)


# --------------------------------------------------------------------------- #
# Tache 5 — division sure
# --------------------------------------------------------------------------- #

T_SAFE_DIVIDE = Task(
    id="safe_divide",
    objective=(
        "Ecrire `safe_divide(a, b)` qui renvoie a / b. La division par zero doit "
        "lever ValueError. Le resultat est un flottant."
    ),
    entrypoint="safe_divide",
    difficulty="facile",
    correct="""def safe_divide(a, b):
    if b == 0:
        raise ValueError("safe_divide: division par zero")
    return a / b
""",
    distractors=(
        # Bug classique et GRAVE : erreur silencieuse.
        """def safe_divide(a, b):
    if b == 0:
        return 0
    return a / b
""",
        # Bug classique : division entiere.
        """def safe_divide(a, b):
    if b == 0:
        raise ValueError("division par zero")
    return a // b
""",
        # Bug classique : ZeroDivisionError non convertie.
        """def safe_divide(a, b):
    return a / b
""",
    ),
    rules=(
        _rule("R-001", "6 / 3 vaut 2.0"),
        _rule("R-002", "Le resultat est un flottant", RuleKind.CONTRACT),
        _rule("R-003", "La division par zero leve ValueError", RuleKind.BOUNDARY),
        _rule("R-004", "Les valeurs negatives sont gerees correctement", RuleKind.BOUNDARY),
    ),
    checks={
        "R-001": "assert safe_divide(6, 3) == 2.0, f'6/3 -> {safe_divide(6,3)}'",
        "R-002": "assert isinstance(safe_divide(1, 2), float), 'le resultat doit etre un float'",
        "R-003": (
            "ok = False\n"
            "try:\n"
            "    safe_divide(1, 0)\n"
            "except ValueError:\n"
            "    ok = True\n"
            "assert ok, 'division par zero: aucune ValueError (erreur silencieuse)'"
        ),
        "R-004": "assert safe_divide(-9, 3) == -3.0, f'-9/3 -> {safe_divide(-9,3)}'",
    },
)


TASKS: tuple[Task, ...] = (
    T_SUM_EVEN,
    T_IS_PRIME,
    T_SAFE_DIVIDE,
    T_MEDIAN,
    T_PARSE_DURATION,
)

TASKS_BY_ID: Mapping[str, Task] = {t.id: t for t in TASKS}


def build_bank(tasks: Sequence[Task] | None = None) -> dict[str, tuple[str, Sequence[str]]]:
    """Construit le banc `cle_de_tache -> (correct, distracteurs)` pour la simulation."""
    out: dict[str, tuple[str, Sequence[str]]] = {}
    for t in tasks or TASKS:
        out[t.objective] = t.bank_entry()
        out[t.id] = t.bank_entry()
    return out


__all__ = ["Task", "TASKS", "TASKS_BY_ID", "build_bank"]
