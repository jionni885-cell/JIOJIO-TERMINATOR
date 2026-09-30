"""Un fichier qui situe ses donnees par rapport a lui-meme doit rester auditable.

Defaut trouve par l'outil sur CE depot, et c'est ce qui le rend interessant : `jio scan .`
declarait `tests/test_divergence.py` « NON TESTABLE ICI », avec pour toute preuve un
`FileNotFoundError` sous `/tmp`. Le fichier lit son corpus par

    REPO = pathlib.Path(__file__).resolve().parents[1]

Or l'audit executait le fichier dans un dossier temporaire : `__file__` valait
`/tmp/jio-xxxx/main.py`, donc `REPO` valait `/tmp`, donc le corpus etait cherche sous
`/tmp/evidence/...` — il n'y etait pas, evidemment. Le scan presentait cela comme une limite
du PROJET (« l'environnement est incomplet ») alors que c'etait une consequence de NOTRE
facon de mesurer.

Ce que coute ce defaut, en clair : un fichier parfaitement auditable est declare hors de
portee, et l'utilisateur apprend que le scan ne sait pas lire les tests — c'est-a-dire
exactement les fichiers ou se trouve la verite d'un projet.

La correction : le script tourne toujours dans un dossier temporaire (aucune ecriture ne
tombe dans le projet), mais le module audite recoit son VRAI `__file__`, et le dossier qui le
contient est ajoute a `sys.path`. Les donnees se resolvent donc comme sous `pytest`.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from jio.verify.autocheck import derive
from jio.verify.executable import ExecutableProver, Sandbox

PROJET_LISANT_SES_DONNEES = '''\
"""Un fichier de test ordinaire : il lit un corpus voisin."""

import pathlib

RACINE = pathlib.Path(__file__).resolve().parents[1]
CORPUS = RACINE / "evidence" / "valeurs.txt"


def moyenne(valeurs: list[int]) -> float:
    """Moyenne arithmetique.

    >>> moyenne([1, 3])
    2.0
    """
    return sum(valeurs) / len(valeurs)


def charger() -> list[int]:
    """Charge le corpus du projet — c'est CE chemin qui doit resoudre.

    >>> charger()
    [1, 3]
    """
    return [int(x) for x in CORPUS.read_text(encoding="utf-8").split()]
'''

PROJET_ARGUMENT = '''\
"""Second fichier du meme projet : il doit pouvoir importer son voisin."""

import valeurs


def double(valeur: int) -> int:
    """Double.

    >>> double(21)
    42
    """
    return valeur * 2
'''


def _projet(tmp_path: Path) -> Path:
    (tmp_path / "tests").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "evidence" / "valeurs.txt").write_text("1 3\n", encoding="utf-8")
    (tmp_path / "tests" / "valeurs.py").write_text(PROJET_ARGUMENT, encoding="utf-8")
    chemin = tmp_path / "tests" / "test_panier.py"
    chemin.write_text(PROJET_LISANT_SES_DONNEES, encoding="utf-8")
    return chemin


def test_le_fichier_audite_voit_son_vrai_chemin(tmp_path: Path) -> None:
    """Le module audite recoit son chemin REEL : ses donnees voisines existent."""
    chemin = _projet(tmp_path)
    prover = ExecutableProver(sandbox=Sandbox(timeout=30))
    source = chemin.read_text(encoding="utf-8")
    derived = derive(source, path=chemin)
    res = prover.prove(
        source, derived.spec, hidden_checks=derived.checks,
        entrypoint=derived.entrypoint, preamble=derived.preamble, chemin=chemin,
    )
    assert not res.hard_failures, [(w.rule_id, w.stderr) for w in res.hard_failures]


def test_sans_le_chemin_le_defaut_existe_toujours() -> None:
    """Le pendant, et il est essentiel : ce test ECHOUERAIT si le `__file__` reel n'avait
    pas d'effet. Sans lui, on ne saurait pas que la correction corrige quelque chose.

    Meme source, meme prover, mais sans chemin declare : `__file__` pointe dans le dossier
    temporaire, le corpus est cherche sous `/tmp` et l'audit ne peut rien conclure. C'est
    l'ancien comportement, conserve ici comme temoin de la mesure.
    """
    import tempfile

    with tempfile.TemporaryDirectory() as dossier:
        racine = Path(dossier)
        chemin = _projet(racine)
        prover = ExecutableProver(sandbox=Sandbox(timeout=30))
        source = chemin.read_text(encoding="utf-8")
        derived = derive(source, path=chemin)
        res = prover.prove(
            source, derived.spec, hidden_checks=derived.checks,
            entrypoint=derived.entrypoint, preamble=derived.preamble,
        )
    messages = (res.hard_failures[0].stderr if res.hard_failures else "") + (res.reservations or "")
    assert res.hard_failures or "FileNotFoundError" in messages, (
        "sans `__file__` reel, un fichier qui lit ses donnees doit echouer : "
        "sinon ce test ne mesure rien"
    )


def test_le_dossier_de_l_artefact_est_importable(tmp_path: Path) -> None:
    """Un fichier de test importe souvent son voisin (`import valeurs`).

    L'import doit resoudre comme sous `pytest`, c'est-a-dire depuis le dossier du fichier.
    """
    chemin = _projet(tmp_path)
    prover = ExecutableProver(sandbox=Sandbox(timeout=30))
    source = chemin.read_text(encoding="utf-8")
    derived = derive(source, path=chemin)
    res = prover.prove(
        source, derived.spec, hidden_checks=derived.checks,
        entrypoint=derived.entrypoint, preamble=derived.preamble, chemin=chemin,
    )
    assert not res.hard_failures, [(w.rule_id, w.stderr) for w in res.hard_failures]


def test_aucune_ecriture_ne_tombe_dans_le_projet(tmp_path: Path) -> None:
    """La correction ne doit PAS relacher la containment : le projet reste intact.

    C'est le point de doctrine : le bac a sable donne au fichier audite la connaissance de
    son emplacement, jamais le droit d'ecrire chez lui. Un fichier qui ecrit dans son
    dossier courant ecrit dans le dossier temporaire.
    """
    (tmp_path / "tests").mkdir()
    chemin = tmp_path / "tests" / "test_ecrivain.py"
    chemin.write_text(
        '"""Un fichier qui ecrit dans son dossier courant."""\n'
        "import pathlib\n\n\n"
        "def ecrire(valeur: str) -> int:\n"
        '    """Ecrit un temoin.\n\n'
        "    >>> ecrire('x')\n"
        "    1\n"
        '    """\n'
        "    pathlib.Path('temoin.txt').write_text(valeur, encoding='utf-8')\n"
        "    return 1\n",
        encoding="utf-8",
    )
    prover = ExecutableProver(sandbox=Sandbox(timeout=30))
    source = chemin.read_text(encoding="utf-8")
    derived = derive(source, path=chemin)
    prover.prove(
        source, derived.spec, hidden_checks=derived.checks,
        entrypoint=derived.entrypoint, preamble=derived.preamble, chemin=chemin,
    )
    restes = sorted(p.name for p in tmp_path.rglob("*"))
    assert restes == ["test_ecrivain.py", "tests"], (
        f"le projet ne doit pas etre modifie par l'audit : {restes}"
    )


def test_le_scan_reel_ne_declare_plus_le_fichier_non_testable() -> None:
    """Le meme verdict, mesure avec la VRAIE commande, sur un projet temporaire.

    Une propriete unitaire peut passer alors que la ligne de commande, elle, n'a pas ete
    branchee. Ce test lance `python -m jio scan` sur le projet et exige que le fichier ne
    soit pas classe « non testable ».
    """
    import tempfile

    with tempfile.TemporaryDirectory() as dossier:
        racine = Path(dossier)
        _projet(racine)
        proc = subprocess.run(
            [__import__("sys").executable, "-m", "jio", "scan", "tests/test_panier.py"],
            cwd=racine, capture_output=True, text=True, timeout=120,
        )
    sortie = proc.stdout + proc.stderr
    assert "0 non testable" in sortie, f"le fichier a ete classe non testable : {sortie}"
    assert "FileNotFoundError" not in sortie, sortie
