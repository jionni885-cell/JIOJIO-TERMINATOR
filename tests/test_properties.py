"""Tests de l'axe proprietes (P-001 non-mutation, P-002 idempotence, P-003 aller-retour).

Chaque test correspond a un echec REELLEMENT observe pendant le developpement :

* `double(value: int) -> int` a d'abord ete declare « non idempotent » — faux :
  `double(1) = 2`, `double(2) = 4`. Le TYPE ne prouve rien, seul un nom ou une
  docstring peut promettre une propriete.
* une API « en place » (`sort_in_place(x) -> None`) a d'abord ete accusee de
  muter son argument — c'est sa raison d'etre. Un verificateur qui accuse a tort
  est desactive au bout de deux jours.
* la propriete d'aller-retour etait rattachee a TOUTES les fonctions du module :
  un seul defaut produisait autant de rapports que de fonctions.
* la derivation par annotations ne couvrait qu'UNE fonction dans tout le noyau :
  les exemples `>>>` fournissent le temoin d'entree qui manque.
* une propriete qui echoue a cause d'un `ImportError` du bac a sable n'est PAS une
  violation : elle ne doit jamais devenir un « probleme » du projet.
"""

from __future__ import annotations

import ast
import pathlib
import subprocess
import sys
import tempfile

from jio.verify.autocheck import derive
from jio.verify.executable import ExecutableProver, Sandbox
from jio.verify.properties import derive_properties, generate_inputs

REPO = pathlib.Path(__file__).resolve().parents[1]


def _props(source: str):
    tree = ast.parse(source)
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    out = []
    for name, node in funcs.items():
        out.extend(derive_properties(node, name, module_functions=funcs))
    return out


def _prove(source: str):
    derived = derive(source)
    prover = ExecutableProver(sandbox=Sandbox(timeout=20))
    return prover.prove(
        source, derived.spec,
        hidden_checks={k: v for k, v in derived.checks.items() if k.startswith("P-")},
        entrypoint=derived.entrypoint, preamble=derived.preamble,
    )


# --------------------------------------------------------------------------- #
# Detection : ce que les exemples ne voient pas
# --------------------------------------------------------------------------- #

MUTATION_SANS_ANNOTATION = '''
def normalize(nums, extra=None):
    """Normalise une suite.

    >>> normalize([3, 1, 3])
    [1, 3, 3]
    """
    nums.sort()
    return nums
'''

SAIN_SANS_ANNOTATION = MUTATION_SANS_ANNOTATION.replace("    nums.sort()\n    return nums", "    return sorted(nums)")


def test_mutation_detectee_sans_annotation():
    """Le cas decisif : la docstring est JUSTE, le code est fautif.

    Les regles par exemples passent (la valeur rendue est celle annoncee) ; seule la
    propriete de non-mutation voit que l'argument de l'appelant a ete detruit.
    """
    props = _props(MUTATION_SANS_ANNOTATION)
    assert [p.id for p in props] == ["P-001"]
    res = _prove(MUTATION_SANS_ANNOTATION)
    echecs = [w.rule_id for w in res.witnesses if not w.ok]
    assert echecs == ["P-001:normalize"]


def test_mutation_par_liste_passee_en_argument():
    """Deuxieme argument mute, sans annotation : detecte aussi."""
    source = '''
def process(data, seen):
    """Traite les donnees.

    >>> process([1, 2], [])
    [1, 2]
    """
    seen.append(len(data))
    return list(data)
'''
    res = _prove(source)
    assert [w.rule_id for w in res.witnesses if not w.ok] == ["P-001:process"]


def test_contre_exemple_reduit():
    """Le temoin livre doit etre le PLUS PETIT : un rapport exploitable, pas une liste brute."""
    source = '''
def normalize(nums):
    """Normalise.

    >>> normalize([1, 2, 3, 4, 5, 6])
    [1, 2, 3, 4, 5, 6]
    """
    nums.sort()
    return nums
'''
    res = _prove(source)
    (witness,) = [w for w in res.witnesses if not w.ok]
    assert "contre-exemple est ([" in witness.stderr
    # 6 elements au depart ; le reducteur doit descendre a moins de 5.
    import re

    found = re.search(r"contre-exemple est \((.*?),\)", witness.stderr)
    assert found, witness.stderr
    assert found.group(1).count(",") < 5, f"temoin non reduit : {found.group(1)}"


def test_aller_retour_avec_perte_detecte():
    """`decode(encode(x)) != x` : defaut silencieux, invisible sans propriete."""
    source = '''
def url_encode(value: str) -> bytes:
    return value[:3].encode("utf-8")


def url_decode(data: bytes) -> str:
    return data.decode("utf-8")
'''
    res = _prove(source)
    echecs = [w.rule_id for w in res.witnesses if not w.ok]
    assert echecs == ["P-003:url_encode"], echecs


# --------------------------------------------------------------------------- #
# Non-detection : aucun faux positif tolere
# --------------------------------------------------------------------------- #

def test_api_en_place_non_accusee():
    """Muter son argument est la RAISON D'ETRE d'une API en place."""
    source = '''
def sort_in_place(nums) -> None:
    nums.sort()


def fill(values, n):
    values.extend(range(n))
'''
    assert _props(source) == []


def test_double_n_est_pas_idempotent_par_nature():
    """Le type `int -> int` ne promet RIEN : `double(1)=2` et `double(2)=4`.

    Accuser cette fonction serait une fausse alerte sur du code correct — l'erreur
    exacte que ce test verrouille.
    """
    source = '''
def double(value: int) -> int:
    return value * 2


def increment(value: int) -> int:
    return value + 1
'''
    ids = [p.id for p in _props(source)]
    assert "P-002" not in ids


def test_idempotence_verifiee_quand_le_nom_la_promet():
    source = '''
def normalize(nums: list[int]) -> list[int]:
    """Normalise une suite."""
    return sorted(set(nums)) + [0]
'''
    ids = [p.id for p in _props(source)]
    assert "P-002" in ids


def test_projet_sain_est_muet():
    res = _prove(SAIN_SANS_ANNOTATION)
    assert not res.failures, [w.rule_id for w in res.failures]


def test_fonction_sans_source_d_entree_ne_produit_rien():
    """Ni annotation ni exemple : aucune propriete inventee."""
    assert _props("def f(a, b):\n    return a + b\n") == []


# --------------------------------------------------------------------------- #
# Determinisme et bornes
# --------------------------------------------------------------------------- #

def test_generation_deterministe_et_bords_presents():
    """Meme graine -> memes entrees ; et les CAS LIMITES sont toujours la.

    Un tirage uniforme rate systematiquement les bords (vide, zero, un element) :
    c'est exactement ce que font les tests par exemples.
    """
    a = generate_inputs("list[int]", 8, 42)
    b = generate_inputs("list[int]", 8, 42)
    assert a == b
    # Bords STRUCTURELS : la liste vide et la liste a un element.
    assert [] in a, "la liste vide doit etre testee"
    assert [1] in a, "la liste a un seul element doit etre testee"
    # Bords de VALEUR : un entier negatif et une grande magnitude.
    assert any(isinstance(x, int) and x < 0 for v in a for x in v), "aucun bord negatif"
    assert any(isinstance(x, int) and abs(x) >= 10**6 for v in a for x in v), "aucune grande valeur"


def test_domaine_inconnu_ne_produit_pas_d_entree():
    """Un type maison n'a pas de domaine devinable : on ne devine pas."""
    assert generate_inputs("MaClasse", 5, 1) is None


def test_budget_de_proprietes_borne():
    """Le nombre de fonctions couvertes est borne : le cout doit rester visible."""
    source = "\n".join(
        f'''
def normalize_{i}(nums: list[int]) -> list[int]:
    """Normalise {i}."""
    return sorted(nums)
'''
        for i in range(12)
    )
    derived = derive(source)
    regles_p = [r.id for r in derived.spec.rules if str(r.id).startswith("P-")]
    assert 0 < len(regles_p) <= 4 * 2, f"budget depasse : {len(regles_p)}"


def test_proprietes_declarees_dans_les_limites_ou_les_notes():
    """Un audit qui n'a rien pu verifier doit le DIRE, jamais le taire."""
    derived = derive("def f(a, b):\n    return a + b\n")
    texte = " ".join(derived.spec.under_specified) + " ".join(derived.notes)
    assert "propriete" in texte


# --------------------------------------------------------------------------- #
# Bout en bout : la commande reelle
# --------------------------------------------------------------------------- #

def _scan(project: pathlib.Path) -> str:
    proc = subprocess.run(
        [sys.executable, "-m", "jio", "scan", str(project), "--exclude-tests", "--no-learn"],
        cwd=REPO, capture_output=True, text=True, timeout=300,
    )
    return proc.stdout + proc.stderr


def test_scan_condamne_le_projet_fautif_et_epargne_le_sain():
    """Le vrai chemin, celui que l'utilisateur lance."""
    with tempfile.TemporaryDirectory() as tmp:
        bugue = pathlib.Path(tmp) / "bugue"
        propre = pathlib.Path(tmp) / "propre"
        for directory, corps in ((bugue, "    nums.sort()\n    return nums"),
                                 (propre, "    return sorted(nums)")):
            directory.mkdir()
            (directory / "normalizer.py").write_text(
                "def normalize(nums, extra=None):\n"
                '    """Normalise.\n\n'
                "    >>> normalize([3, 1, 3])\n"
                "    [1, 3, 3]\n"
                '    """\n'
                f"{corps}\n",
                encoding="utf-8",
            )

        sortie_bugue = _scan(bugue)
        sortie_propre = _scan(propre)

    assert "P-001:normalize" in sortie_bugue, sortie_bugue
    assert "1 PROBLEME(S)" in sortie_bugue, sortie_bugue
    assert "Aucun probleme" in sortie_propre, sortie_propre


# --------------------------------------------------------------------------- #
# P-004 / P-005 : promesses de tri et de dedoublonnage
# --------------------------------------------------------------------------- #

TRI_PERD_DOUBLONS = '''
def sort_values(nums: list[int]) -> list[int]:
    """Trie.

    >>> sort_values([3, 1, 2])
    [1, 2, 3]
    """
    return sorted(set(nums))
'''

TRI_DESC_FAUX = '''
def sort_desc(nums: list[int]) -> list[int]:
    """Trie a l'envers.

    >>> sort_desc([1, 2, 3])
    [3, 2, 1]
    """
    return sorted(nums)
'''

DEDUPE_PERD = '''
def dedupe(items: list[int]) -> list[int]:
    """Retire les doublons.

    >>> dedupe([1, 1, 2])
    [1, 2]
    """
    return [items[0]]
'''


def test_tri_qui_perd_des_elements_detecte():
    """`sorted(set(x))` est trie mais INFIDELE : un tri doit rendre tout ce qu'il recoit.

    Le banc a revele que ce cas echappait a la premiere version : les listes generees
    depuis les annotations n'avaient aucun doublon. Les cas sont donc enrichis par
    deformation structurelle (liste dupliquee, vide, reduite).
    """
    res = _prove(TRI_PERD_DOUBLONS)
    assert [w.rule_id for w in res.witnesses if not w.ok] == ["P-004:sort_values"]


def test_tri_decroissant_qui_rend_croissant_detecte():
    """Le nom promet l'ordre decroissant ; la sortie est croissante."""
    res = _prove(TRI_DESC_FAUX)
    assert [w.rule_id for w in res.witnesses if not w.ok] == ["P-004:sort_desc"]


def test_dedoublonnage_qui_perd_un_element_detecte():
    """Retirer les REPETITIONS est permis ; retirer une valeur unique ne l'est pas."""
    res = _prove(DEDUPE_PERD)
    assert [w.rule_id for w in res.witnesses if not w.ok] == ["P-005:dedupe"]


def test_nom_sans_promesse_n_est_pas_juge():
    """`arrange` ne promet ni tri ni fidelite : aucune regle P-004/P-005 ne l'accuse."""
    source = '''
def arrange(nums: list[int]) -> list[int]:
    """Range les nombres.

    >>> arrange([3, 1, 2])
    [1, 2, 3]
    """
    return sorted(set(nums))
'''
    ids = [p.id for p in _props(source)]
    assert "P-004" not in ids and "P-005" not in ids


def test_dedoublonnage_annonce_par_le_nom_reste_permis():
    """`sorted_unique` annonce la perte : la fidelite n'est PAS exigee."""
    source = '''
def sorted_unique(nums: list[int]) -> list[int]:
    """Trie et dedoublonne.

    >>> sorted_unique([3, 1, 3])
    [1, 3]
    """
    return sorted(set(nums))
'''
    res = _prove(source)
    assert not res.failures, [w.rule_id for w in res.failures]


# --------------------------------------------------------------------------- #
# Garde-fous de l'outillage lui-meme
# --------------------------------------------------------------------------- #

def test_programme_d_audit_est_compilable():
    """Le programme envoye au bac a sable doit COMPILER.

    Fuite reelle : un saut de ligne mal echappe a fait echouer tous les controles en
    `SyntaxError` — que la classification range en « environnement ». L'audit est
    devenu silencieusement aveugle (aucun probleme signale, aucune erreur visible).
    Un `compile()` en test rend cette classe de panne impossible a livrer.
    """
    from jio.verify.executable import _AUDIT_AS_MODULE, _SYNC_MODULE

    programme = (
        _AUDIT_AS_MODULE
        + "def f(value: int) -> int:\n    return value\n"
        + "\n"
        + _SYNC_MODULE
        + "assert callable(f)\n"
    )
    compile(programme, "<audit>", "exec")


def test_l_artefact_est_audite_comme_module_pas_comme_script():
    """Le bloc `if __name__ == "__main__":` ne doit PAS s'executer pendant l'audit.

    Fuite reelle : une bibliotheque dont la demonstration (sous `__main__`) divise
    par zero etait declaree « ne s'execute pas ».
    """
    source = '''
def utile(value: int) -> int:
    """Double.

    >>> utile(2)
    4
    """
    return value * 2


if __name__ == "__main__":
    raise SystemExit(1 / 0)
'''
    res = _prove(source)
    assert not res.failures, [w.rule_id for w in res.failures]


def test_un_echec_est_une_violation_pas_un_plantage_de_l_outillage():
    """Un echec doit etre une VIOLATION, avec son message — jamais une erreur de notre
    propre outillage. Sans cette exigence, « quelque chose a echoue » peut vouloir dire
    « notre programme etait casse », et la mesure ne vaut rien."""
    res = _prove(MUTATION_SANS_ANNOTATION)
    (witness,) = res.failures
    assert "MODIFIE par normalize" in witness.stderr, witness.stderr
    for plantage in ("SyntaxError", "AttributeError", "NameError", "TypeError"):
        assert plantage not in witness.stderr, witness.stderr
