"""Les hooks pre-commit : une promesse ecrite doit avoir une implementation.

`jio-scan-strict` etait annonce comme « echoue aussi si le projet est incoherent a
l'import » — avec **exactement la meme commande** que le hook normal. Un artefact qui ment
sur lui-meme est precisement ce que ce projet traque ailleurs ; l'oublier dans son propre
fichier de hooks serait le pire endroit pour le faire.

Ces tests verifient trois choses : les deux manifestes sont VALIDES au standard de
l'ecosysteme, chaque hook declare a une entree qui existe vraiment, et le mode strict fait
une difference observable.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PRECOMMIT = shutil.which("pre-commit") or str(REPO / ".venv" / "bin" / "pre-commit")


def _lance(*args: str, timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "jio", *args],
        cwd=REPO, capture_output=True, text=True, timeout=timeout, check=False,
    )


# --------------------------------------------------------------------------- #
# 1. Le standard de l'ecosysteme : pre-commit doit accepter les deux fichiers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fichier", [".pre-commit-config.yaml", ".pre-commit-hooks.yaml"])
def test_le_fichier_de_hooks_est_valide(fichier: str) -> None:
    """`pre-commit validate-*` est l'arbitre : c'est lui qui lira ces fichiers.

    Verifier nous-memes notre YAML ne prouverait rien — c'est la meme erreur que de tester
    un parseur contre lui-meme.
    """
    if not Path(PRECOMMIT).exists():
        pytest.skip("pre-commit absent")
    commande = "validate-config" if "config" in fichier else "validate-manifest"
    resultat = subprocess.run(
        [PRECOMMIT, commande, fichier],
        cwd=REPO, capture_output=True, text=True, timeout=120, check=False,
    )
    assert resultat.returncode == 0, resultat.stderr + resultat.stdout


# --------------------------------------------------------------------------- #
# 2. Chaque hook declare une entree qui EXISTE
# --------------------------------------------------------------------------- #


def test_le_hook_strict_utilise_vraiment_le_mode_strict() -> None:
    """Le defaut trouve dans ce depot : deux hooks, une seule commande.

    Le manifeste annoncait un audit « strict » dont l'entree etait identique a celle du
    hook normal. Une promesse sans implementation est un mensonge par omission — et
    l'utilisateur ne le decouvre qu'en croyant sa CI plus severe qu'elle ne l'est.
    """
    import yaml

    manifeste = yaml.safe_load((REPO / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    entrees = {h["id"]: h["entry"] for h in manifeste}

    assert "--strict" in entrees["jio-scan-strict"], (
        "le hook strict doit passer --strict : sinon il est identique au hook normal"
    )
    assert "--strict" not in entrees["jio-scan"], "le hook normal ne doit pas etre strict"
    assert "--hook" in entrees["jio-claims"], (
        "le hook document doit passer --hook : sans cela, « rien a verifier » (code 3) "
        "ferait echouer un commit sans qu'aucune faute n'existe"
    )


def test_les_hooks_declarent_les_bonnes_options_de_fichiers() -> None:
    """`jio-claims` doit recevoir les noms de fichiers ; `jio-scan` non, et c'est voulu."""
    import yaml

    manifeste = yaml.safe_load((REPO / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    par_id = {h["id"]: h for h in manifeste}

    # Un defaut n'existe pas fichier par fichier : un renommage casse le CONSOMMATEUR.
    assert par_id["jio-scan"]["pass_filenames"] is False
    # Le document, si : c'est le fichier lui-meme qui est verifie. `pass_filenames` absent
    # vaut `true` dans le standard pre-commit — c'est ce defaut qui nous sert.
    assert par_id["jio-claims"].get("pass_filenames") is not False
    assert "md" in par_id["jio-claims"]["files"]


# --------------------------------------------------------------------------- #
# 3. Le mode strict change quelque chose d'OBSERVABLE
# --------------------------------------------------------------------------- #


def test_le_mode_strict_echoue_la_ou_le_mode_normal_passe(tmp_path: Path) -> None:
    """Sinon `--strict` serait un drapeau decoratif.

    Le cas : un fichier non testable (analyse impossible). Le mode normal le montre et
    rend 0 — c'est legitime, on ne sait pas encore s'il est fautif. Le mode strict refuse
    de laisser passer un fichier que la porte n'a PAS pu juger.
    """
    projet = tmp_path / "projet"
    projet.mkdir()
    # Le cas mesure sur un vrai projet (`humanize`) : le fichier importe un module GENERE
    # a l'installation, donc absent. Les regles echouent avec ModuleNotFoundError : ce
    # n'est NI un defaut, NI une reserve, c'est « la verification n'a pas pu avoir lieu ».
    # Le mode normal le dit et rend 0 ; le mode strict refuse de laisser passer un fichier
    # que la porte n'a PAS pu juger.
    (projet / "genere.py").write_text(
        '"""Depend d un module genere a l installation."""\n'
        "from ._version import __version__\n"
        "\n"
        "\n"
        "def ver() -> str:\n"
        '    """Return the generated version.\n'
        "\n"
        "    >>> ver()\n"
        "    '1.0'\n"
        '    """\n'
        "    return __version__\n",
        encoding="utf-8",
    )

    normal = _lance("scan", str(projet), "--no-learn", "--no-linters")
    strict = _lance("scan", str(projet), "--no-learn", "--no-linters", "--strict")

    assert normal.returncode == 0, normal.stdout
    assert "NON TESTABLE" in normal.stdout.upper(), normal.stdout
    assert strict.returncode == 1, (
        "le mode strict doit refuser un projet ou la verification n'a pas pu avoir lieu\n"
        + strict.stdout
    )
    assert "MODE STRICT" in strict.stdout


def test_le_mode_strict_ne_bloque_pas_sur_du_code_juge(tmp_path: Path) -> None:
    """Une porte qui refuse tout n'est pas une porte : elle serait desactivee."""
    projet = tmp_path / "projet"
    projet.mkdir()
    (projet / "utils.py").write_text(
        '"""Petite fonction avec exemple verifiable."""\n'
        "\n"
        "\n"
        "def double(x: int) -> int:\n"
        '    """Return x + x.\n'
        "\n"
        "    >>> double(2)\n"
        "    4\n"
        '    """\n'
        "    return x + x\n",
        encoding="utf-8",
    )

    resultat = _lance("scan", str(projet), "--no-learn", "--strict")

    assert resultat.returncode == 0, resultat.stdout
    assert "la porte est franchie" in resultat.stdout


# --------------------------------------------------------------------------- #
# 4. Le contrat avec pre-commit : `entry` doit etre une commande jio VALIDE
# --------------------------------------------------------------------------- #


def test_chaque_entry_du_manifeste_est_une_commande_jio_ACCEPTEE_par_le_parseur() -> None:
    """Le contrat qui manquait : `entry` est une CHAINE, et rien ne la verifiait.

    pre-commit installe l'entree telle quelle. Un `--strict` mal orthographie, une option
    renommee, une sous-commande supprimee : le hook se met a echouer sur TOUS les commits de
    l'utilisateur, avec un message qui parle de jio et non de l'erreur. Le manifeste etait
    teste sur deux fragments (`"--strict" in entree`), ce qui ne dit rien du reste.

    L'oracle est le PARSEUR lui-meme — pas une liste recopiee, qui deriverait.
    """
    import shlex

    import yaml

    from jio.cli import build_parser

    parser = build_parser()
    manifeste = yaml.safe_load((REPO / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    for hook in manifeste:
        morceaux = shlex.split(hook["entry"])
        assert morceaux[0] == "jio", (
            f"{hook['id']} : l'entree doit appeler `jio` (le script installe par le paquet), "
            f"pas `{morceaux[0]}`"
        )
        # pre-commit AJOUTE les noms de fichiers apres l'entree, sauf si le hook declare
        # `pass_filenames: false`. On modelise exactement ce qu'il fera : sans cela, un hook
        # dont le fichier est un argument obligatoire (`jio claims`, qui en exige au moins un)
        # passerait pour casse alors qu'il est correct.
        arguments = morceaux[1:]
        if hook.get("pass_filenames") is not False:
            arguments = [*arguments, "README.md"]
        try:
            parser.parse_args(arguments)
        except SystemExit as exc:  # argparse sort en 2 sur un usage invalide
            raise AssertionError(
                f"{hook['id']} : `{hook['entry']}` est refusee par le parseur de jio "
                f"(code {exc.code}). Verifiez la sous-commande et les options."
            ) from None


def test_le_script_jio_est_declare_dans_le_paquet() -> None:
    """Sans point d'entree `jio`, TOUS ces hooks echouent a l'installation.

    pre-commit, en `language: python`, installe le paquet puis appelle l'entree : si
    `pyproject.toml` ne declare pas le script, l'utilisateur voit « jio: command not found »
    et aucun de ces controles ne tourne — le manifeste entier serait decoratif.
    """
    import tomllib

    projet = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))
    assert projet["project"]["scripts"]["jio"] == "jio.cli:main"


def test_les_hooks_ne_sont_pas_declares_en_LANGUAGE_system() -> None:
    """`language: system` supposerait jio deja installe : l'utilisateur croirait avoir une
    porte alors qu'il aurait une erreur d'installation a chaque commit."""
    import yaml

    manifeste = yaml.safe_load((REPO / ".pre-commit-hooks.yaml").read_text(encoding="utf-8"))
    for hook in manifeste:
        assert hook.get("language") == "python", hook["id"]
