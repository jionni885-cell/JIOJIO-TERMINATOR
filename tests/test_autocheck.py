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


def test_bon_artefact_est_conforme_sur_toutes_les_regles():
    """Un artefact sain satisfait TOUTES les regles derivees, quel qu'en soit le nombre.

    Le comptage exact n'est pas le sujet : chaque axe ajoute des regles (ici P-001,
    non-mutation, derivee de la signature et de l'exemple). Ce qui doit tenir est
    qu'aucune regle ne condamne un artefact correct — c'est le point ou un faux
    positif couterait la confiance dans l'outil.
    """
    res = _prove(BON)
    assert res.passed
    assert not res.failures
    assert len(res.witnesses) >= 3
    assert any(w.rule_id.startswith("P-") for w in res.witnesses), (
        "l'axe proprietes doit etre actif sur un artefact annote"
    )


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


# --------------------------------------------------------------------------- #
# Les fixtures pytest ne sont pas des cibles d'audit
# --------------------------------------------------------------------------- #


def test_une_fixture_pytest_est_hors_audit_et_dite_comme_telle() -> None:
    """Une fixture n'est pas appelable directement : ce n'est pas un defaut du fichier.

    Defaut reel, trouve en lancant `jio scan .` sur ce depot apres reconstruction de
    l'environnement : `tests/test_chiffres_documentes.py` rapportait un PROBLEME

        [A-002] https://docs.pytest.org/en/stable/deprecations.html#calling-fixtures-directly

    L'audit avait choisi la fixture `mesures` comme cible (premiere fonction publique du
    fichier), lui avait applique la regle de reproductibilite, et l'appel direct avait leve

        Failed: Fixture "mesures" called directly.

    Un faux positif de cette farine detruit la confiance dans le garde. La fixture sort
    donc de l'audit — et surtout, l'exclusion est DITE : un fichier ou l'on n'a rien
    verifie ne doit pas ressembler a un fichier ou tout va bien.
    """
    source = (
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def mesures():\n"
        "    return {'tests': 1}\n"
        "\n"
        "\n"
        "def utilite() -> int:\n"
        "    return 1\n"
    )
    derived = derive(source)

    assert "mesures" not in derived.functions, "une fixture a ete retenue comme cible"
    assert "utilite" in derived.functions
    assert derived.entrypoint != "mesures", "l'audit vise encore la fixture"
    limites = " ".join(derived.spec.under_specified)
    assert "fixture" in limites and "mesures" in limites, (
        "l'exclusion n'est pas declaree : " + limites
    )


def test_un_fichier_de_fixtures_seulement_le_dit_au_lieu_de_se_taire() -> None:
    """Cas limite : plus rien a auditer, mais une RAISON a donner.

    Le message par defaut (« aucune fonction ni classe publique ») serait faux : le
    fichier declare bien des fonctions, elles ne sont simplement pas auditables ainsi.
    """
    source = (
        "import pytest\n"
        "\n"
        "@pytest.fixture\n"
        "def a():\n"
        "    return 1\n"
        "\n"
        "@pytest.fixture(scope='module')\n"
        "def b():\n"
        "    return 2\n"
    )
    derived = derive(source)

    assert not derived.verifiable
    motif = " ".join(derived.spec.under_specified)
    assert "fixture" in motif
    assert "a" in motif and "b" in motif
    assert "pas un defaut" in motif


def test_une_fonction_decorée_autrement_reste_auditee() -> None:
    """Le filtre ne doit pas devenir un trou : un decorateur ordinaire n'exclut rien.

    Sinon il suffirait d'un `@lru_cache` ou d'un decorateur maison pour sortir de l'audit
    sans que personne ne le voie.
    """
    source = (
        "from functools import lru_cache\n"
        "\n"
        "\n"
        "@lru_cache(maxsize=None)\n"
        "def compte(n: int = 1) -> int:\n"
        "    return n + 1\n"
    )
    derived = derive(source)

    assert "compte" in derived.functions
    assert derived.entrypoint == "compte"
    assert derived.verifiable


# --------------------------------------------------------------------------- #
# La regle A-002 : ce qu'elle compare, et ce qu'elle accuse
# --------------------------------------------------------------------------- #


def test_un_message_qui_PORTE_un_volatil_n_est_pas_une_non_reproductibilite() -> None:
    """Un message qui porte une adresse memoire bat, et la fonction est reproductible.

    Mesure a l'origine : `tests/test_coherence.py::test_le_depot_est_coherent` a ete declare
    « non reproductible » par `jio scan` — parce que son message d'echec contient le rapport de la
    porte, qui ANNONCE SA DUREE (« 9 controle(s) en 0.1s »). Deux appels identiques, deux durees,
    deux messages. La fonction, elle, ne variait pas d'un iota.

    Une fausse accusation coute plus qu'un silence : elle apprend a ignorer A-002, et A-002 est la
    seule regle qui attrape les compteurs globaux — la classe de bug la plus courante d'un agent
    qui garde un etat entre deux appels.

    Ce test-ci utilise une ADRESSE MEMOIRE plutot qu'une duree : elle varie a chaque appel de
    facon certaine, donc le test PROUVE qu'il exerce la normalisation au lieu de l'esperer. Le
    premier bloc verifie justement que les messages bruts, eux, different — sans cette
    verification, un test vert ne dirait rien.
    """
    source = '''
_vivants = []


def trace() -> str:
    # L'objet est GARDE EN VIE : CPython reutilise l'adresse d'un objet libere, donc sans cette
    # liste les cinq messages seraient identiques et le test serait vert sans rien prouver. Le
    # premier essai de ce test a echoue exactement la : une seule adresse pour cinq appels.
    marqueur = object()
    _vivants.append(marqueur)
    assert False, f"etat inattendu : {marqueur!r}"
'''
    namespace: dict = {}
    exec(source, namespace)                                        # noqa: S102 — le candidat

    def message_brut() -> str:
        try:
            return namespace["trace"]()
        except AssertionError as exc:
            return str(exc)

    assert len({message_brut() for _ in range(5)}) > 1, (
        "les messages doivent varier, sinon ce test ne prouve rien"
    )

    res = _prove(source)
    assert res.passed, res.hard_failures
    # Et la tolerance est DITE, dans le temoin lui-meme : une normalisation silencieuse serait
    # indiscernable d'une regle qu'on a desactivee.
    assert any("[JIO-NOTE]" in w.stdout for w in res.witnesses), [
        (w.rule_id, w.stdout) for w in res.witnesses
    ]


def test_un_compteur_global_reste_ACCUSE_malgre_la_normalisation() -> None:
    """Le remede ne doit pas devenir une complaisance : le vrai non-determinisme reste attrape.

    La normalisation ne retire que des DUREES et des ADRESSES : un compteur change le message
    autrement (« 1 », « 2 », « 3 »), et deux appels qui rendent des valeurs differentes le disent
    par la valeur, pas par le texte.
    """
    source = '''
_counter = {"n": 0}


def next_id() -> int:
    _counter["n"] += 1
    return _counter["n"]
'''
    res = _prove(source)
    assert not res.passed
    assert res.hard_failures[0].rule_id == "A-002"


def test_la_comparaison_normalise_les_volatils_et_RIEN_d_autre() -> None:
    """La liste des fragments retires est courte, declaree, et se voit dans le code.

    Ce test fixe les deux bords : ce qui doit etre retire l'est, et ce qui ne doit pas l'etre ne
    l'est pas. Sans le second bord, « normaliser » finirait par vouloir dire « ignorer ».
    """
    from jio.verify.autocheck import _SAME_HELPERS

    espace: dict = {}
    exec(_SAME_HELPERS, espace)          # noqa: S102 — c'est le code du temoin lui-meme
    same, stable = espace["_jio_same"], espace["_jio_stable"]

    def erreur(message: str):
        return ("erreur", "AssertionError", message)

    # Une duree et une adresse differentes : memes comportements, donc identiques.
    assert same(erreur("x en 0.1s"), erreur("x en 0.2s"))
    assert same(erreur("adresse 0x7f9c1a2b3c4d"), erreur("adresse 0x7f9c1a2b3c4e"))
    assert "<volatil>" in stable("x en 0.1s")
    assert "<volatil>" in stable("duree 12345 ns")
    # Meme message : identiques, evidemment.
    assert same(erreur("x en 0.1s"), erreur("x en 0.1s"))
    # Tout le reste se compare comme avant : un contenu different est une divergence.
    assert not same(erreur("valeur 1"), erreur("valeur 2"))
    assert not same(erreur("x en 0.1s"), erreur("x en 0.1s mais autre chose"))
    assert not same(erreur("meme texte"), ("valeur", "meme texte"))
    assert not same(erreur("meme texte"), ("erreur", "TypeError", "meme texte"))
