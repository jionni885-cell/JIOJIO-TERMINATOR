"""Tests de l'audit generique : derivation de regles a partir de l'artefact.

Ces tests verrouillent la lecon la plus couteuse du projet : tout faux positif
(accuser un artefact sain, ou lui pardonner un defaut) detruit la confiance dans
le garde. Chaque test correspond donc a un faux positif ou faux negatif
reellement observe pendant le developpement.
"""

from __future__ import annotations

from pathlib import Path

from jio.core.types import Rule, RuleKind, Spec
from jio.verify.autocheck import derive, package_preamble, syntax_error
from jio.verify.executable import ExecutableProver, ProverResult, Sandbox

# --------------------------------------------------------------------------- #
# Artefacts de test
# --------------------------------------------------------------------------- #

BON = '''
def sum_even(nums: list[int]) -> int:
    """Somme des nombres pairs.

    >>> sum_even([1, 2, 3, 4])
    6
    """
    return sum(n for n in nums if n % 2 == 0)
'''

DOCSTRING_MENTEUSE = '''
def sum_even(nums: list[int]) -> int:
    """Somme des pairs.

    >>> sum_even([1, 2, 3, 4])
    99
    """
    return sum(n for n in nums if n % 2 == 0)
'''

ALEATOIRE = '''
import random

def pick(n: int) -> int:
    return random.randint(0, n)
'''

HORLOGE = '''
import time

def now() -> float:
    return time.time()
'''

SANS_ANNOTATION = '''
def total(numbers):
    return sum(numbers)
'''

SANS_PARAMETRE = '''
def forty_two() -> int:
    return 42
'''


def _prove(source: str, entrypoint: str = "", path: Path | None = None) -> ProverResult:
    derived = derive(source, entrypoint=entrypoint, path=path)
    prover = ExecutableProver(sandbox=Sandbox(timeout=20))
    return prover.prove(
        source,
        derived.spec,
        hidden_checks=derived.checks,
        entrypoint=derived.entrypoint,
        preamble=derived.preamble,
    )


# --------------------------------------------------------------------------- #
# Detection de syntaxe
# --------------------------------------------------------------------------- #


def test_syntax_error_reported():
    assert syntax_error("def f(:\n") != ""
    assert syntax_error(BON) == ""


# --------------------------------------------------------------------------- #
# Mode fonction
# --------------------------------------------------------------------------- #


def test_bon_artefact_est_conforme_sur_trois_regles():
    res = _prove(BON)
    assert len(res.witnesses) == 3
    assert res.passed


def test_docstring_menteuse_est_detectee():
    """Le seul temoin opposable a un artefact sans spec externe : ses propres exemples."""
    res = _prove(DOCSTRING_MENTEUSE)
    assert not res.passed
    assert res.hard_failures[0].rule_id == "A-003"


def test_aleatoire_ne_produit_pas_de_faux_negatif():
    """Faux negatif historique : sondes [0, 1] et un seul appel laissaient passer random."""
    derived = derive(ALEATOIRE)
    assert "A-002" not in derived.checks  # pas de regle : non-deterministe par conception
    assert any("non-determinisme" in u for u in derived.spec.under_specified)


def test_horloge_est_declaree_non_verifiable_et_non_accusee():
    """`now()` n'est pas un defaut : c'est une dependance a l'environnement."""
    derived = derive(HORLOGE)
    assert "A-002" not in derived.checks
    assert any("horloge" in u for u in derived.spec.under_specified)
    assert _prove(HORLOGE).passed  # seule la regle « appelable » reste, et elle tient


def test_aucune_sonde_inventee_quand_les_parametres_ne_sont_pas_derivables():
    derived = derive(SANS_ANNOTATION)
    assert "A-002" not in derived.checks
    assert any("sans annotation" in u for u in derived.spec.under_specified)


def test_fonction_sans_parametre_est_sondee():
    """Regression : `product(*[[]])` est vide -> la sonde n'etait jamais executee."""
    derived = derive(SANS_PARAMETRE)
    assert "A-002" in derived.checks
    assert _prove(SANS_PARAMETRE).passed


def test_reproductibilite_detecte_un_compteur_global():
    source = '''
_counter = {"n": 0}

def next_id() -> int:
    _counter["n"] += 1
    return _counter["n"]
'''
    res = _prove(source)
    assert not res.passed
    assert res.hard_failures[0].rule_id == "A-002"


# --------------------------------------------------------------------------- #
# Mode classe
# --------------------------------------------------------------------------- #


def test_dataclass_a_champs_obligatoires_n_est_pas_accusee():
    """Piege paye : une dataclass n'a pas d'`__init__` dans son AST."""
    source = '''
from dataclasses import dataclass

@dataclass
class Point:
    x: int
    y: int
'''
    derived = derive(source)
    assert "C-001" not in derived.checks
    assert any("instanciable a vide" in u for u in derived.spec.under_specified)
    assert any("x, y" in u for u in derived.spec.under_specified)  # les champs sont nommes


def test_protocol_n_est_pas_accuse():
    source = '''
from typing import Protocol

class Critic(Protocol):
    def review(self, text: str) -> bool:
        ...
'''
    derived = derive(source)
    assert "C-001" not in derived.checks
    assert any("par conception" in u for u in derived.spec.under_specified)


def test_classe_sans_argument_est_auditee():
    source = '''
class Counter:
    def __init__(self) -> None:
        self.n = 0

    def step(self, k: int = 1) -> int:
        return k + 1
'''
    derived = derive(source)
    assert "C-001" in derived.checks
    assert _prove(source).passed


# --------------------------------------------------------------------------- #
# PREAMBULE : imports relatifs, `from __future__`
# --------------------------------------------------------------------------- #


def test_preamble_resout_les_imports_relatifs(tmp_path: Path):
    pkg = tmp_path / "pkg"
    (pkg / "sub").mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "sub" / "__init__.py").write_text("")
    mod = pkg / "sub" / "mod.py"
    mod.write_text(
        "from __future__ import annotations\n"
        "from .. import core\n"
        "def add(a: int, b: int) -> int:\n"
        "    return a + b\n"
    )
    (pkg / "core.py").write_text("VALUE = 1\n")

    preamble = package_preamble(mod)
    assert "__package__" in preamble
    derived = derive(mod.read_text(), path=mod)
    prover = ExecutableProver(sandbox=Sandbox(timeout=20))
    res = prover.prove(
        mod.read_text(),
        derived.spec,
        hidden_checks=derived.checks,
        entrypoint=derived.entrypoint,
        preamble=derived.preamble,
    )
    # Faux positif historique : ImportError sur l'import relatif, puis SyntaxError
    # parce que `from __future__` n'etait plus la premiere instruction.
    assert res.passed, [w.stderr for w in res.hard_failures]


def test_pas_de_preamble_hors_paquet():
    assert package_preamble(Path("/tmp/isolated.py")) == ""


# --------------------------------------------------------------------------- #
# RESERVE vs REJET : distinguer le soupcon de la preuve
# --------------------------------------------------------------------------- #


def _spec_avec_regle_advisory() -> tuple[Spec, dict[str, str]]:
    spec = Spec(
        mission="test",
        rules=(
            Rule(id="X-001", statement="regle dure", kind=RuleKind.TEST),
            Rule(id="X-900", statement="suspicion", kind=RuleKind.ADVISORY),
        ),
    )
    checks = {
        "X-001": "assert True",
        "X-900": 'assert False, "divergence environnementale"',
    }
    return spec, checks


def test_echec_advisory_produit_une_reserve_pas_un_rejet():
    spec, checks = _spec_avec_regle_advisory()
    res = ExecutableProver(sandbox=Sandbox(timeout=20)).prove(
        "VALUE = 1\n", spec, hidden_checks=checks
    )
    assert res.passed, "une suspicion ne doit jamais condamner un artefact"
    assert len(res.reservations) == 1
    assert not res.hard_failures
    assert res.ratio == 1.0


def test_echec_dur_condamne_toujours():
    spec = Spec(
        mission="test",
        rules=(Rule(id="X-001", statement="regle dure", kind=RuleKind.TEST),),
    )
    res = ExecutableProver(sandbox=Sandbox(timeout=20)).prove(
        "VALUE = 1\n", spec, hidden_checks={"X-001": 'assert False, "vrai defaut"'}
    )
    assert not res.passed
    assert len(res.hard_failures) == 1
