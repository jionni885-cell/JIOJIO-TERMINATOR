"""Toutes les commandes de la CLI s'executent-elles vraiment ?

Un utilisateur n'utilise pas « le projet » : il utilise une commande, un jour, dans un
contexte precis. Une commande rare qui plante fait plus de degats qu'une fonctionnalite
absente — elle laisse croire que le reste ne marche pas non plus.

Ce fichier lance **chaque** sous-commande de `jio`, dans un depot temporaire vide :

  * avec `--help` pour toutes, sans exception (une commande qui ne repond pas a `--help`
    n'existe pas pour celui qui la decouvre) ;
  * avec des arguments minimaux et sans effet de bord pour celles qui peuvent tourner sur
    un depot vide : on verifie alors l'absence de TRACEBACK (une exception non geree est un
    bug, jamais un « cas limite ») et l'absence d'ecriture surprise.

Ce que ce test a de particulier : il ne demande pas si le resultat est BON, seulement si la
commande VA AU BOUT. Les trois defauts qu'il attrape sont ceux qui font perdre une heure :
l'exception non geree, l'option oubliee, et la commande qui ecrit chez l'utilisateur sans
qu'on le lui ait demande.

Regle d'ecriture : ce test ne modifie JAMAIS le depot reel. Chaque commande tourne dans un
`tmp_path`, et le test verifie que le dossier est reste vide apres coup.
"""

from __future__ import annotations

import argparse
import io
import os
import contextlib
from pathlib import Path

import pytest

from jio.cli import build_parser, main


def _sous_commandes() -> list[str]:
    """Les noms des sous-commandes du parseur REEL, jamais une liste recopiee.

    Une liste ecrite a la main oublie toujours la derniere commande ajoutee — et c'est
    justement celle-la qui n'a jamais ete lancee.
    """
    parser = build_parser()
    for action in parser._actions:  # noqa: SLF001 - c'est le parseur qu'on veut interroger
        if isinstance(action, argparse._SubParsersAction):  # noqa: SLF001
            return sorted(action.choices)
    raise AssertionError("aucune sous-commande trouvee : la CLI a change de forme")


def _lancer(arguments: list[str]) -> tuple[int, str]:
    """Execute `main` en capturant tout, y compris les `SystemExit` d'argparse."""
    sortie = io.StringIO()
    try:
        with contextlib.redirect_stdout(sortie), contextlib.redirect_stderr(sortie):
            code = main(arguments)
    except SystemExit as sortie_argparse:  # `--help` sort par la, et c'est normal
        code = int(sortie_argparse.code or 0)
    return code, sortie.getvalue()


# --------------------------------------------------------------------------- #
# 1. Toutes les commandes repondent
# --------------------------------------------------------------------------- #

COMMANDES = _sous_commandes()


def test_la_cli_expose_des_commandes() -> None:
    assert len(COMMANDES) >= 12, f"trop peu de commandes : {COMMANDES}"


@pytest.mark.parametrize("commande", COMMANDES)
def test_chaque_commande_repond_a_help(commande: str) -> None:
    """`jio <commande> --help` doit rendre la main en 0, sans traceback.

    C'est le premier contact avec une commande. Une aide qui plante, ou qui sort en code
    1, se lit comme « cette commande est cassee ».
    """
    code, sortie = _lancer([commande, "--help"])
    assert code == 0, f"`jio {commande} --help` sort en {code} :\n{sortie[-800:]}"
    assert "Traceback" not in sortie, f"traceback dans l'aide de {commande} :\n{sortie[-800:]}"
    assert "usage:" in sortie.lower(), f"pas d'aide affichee pour {commande}"


@pytest.mark.parametrize("commande", COMMANDES)
def test_chaque_commande_refuse_une_option_inconnue_proprement(commande: str) -> None:
    """Une option inventee doit produire un message, pas une exception.

    Le code 2 est celui d'argparse : le contrat est « je n'ai pas compris », pas « j'ai
    plante ». Un traceback ici signifie qu'un argument est lu avant d'etre valide.
    """
    code, sortie = _lancer([commande, "--option-qui-nexiste-pas"])
    assert code == 2, f"`jio {commande} --inconnue` sort en {code} :\n{sortie[-500:]}"
    assert "Traceback" not in sortie, f"traceback sur option inconnue :\n{sortie[-800:]}"


# --------------------------------------------------------------------------- #
# 2. Les commandes sures vont au bout, sur un depot VIDE
# --------------------------------------------------------------------------- #

#: Arguments minimaux pour les commandes qui peuvent tourner sans contexte. Ce qui est
#: volontairement absent : `run`, `bench`, `learn`, `audit` (ils lancent des missions ou
#: des mesures longues, couvertes ailleurs), `mutants` (il mutte le depot et relance pytest
#: dans une copie — `test_mutants_suite.py` s'en occupe, et son but est justement de lancer
#: des suites de tests) et `recover`/`sync` (ils exigent un depot git reel —
#: `test_recover.py` et `test_depot_reinitialise.py` s'en occupent).
SURES: dict[str, list[str]] = {
    "version": [],
    "doctor": [],
    "providers": [],
    "tasks": [],
    "memory": ["--root", "."],
    "trust": [],
    "trace": [],
    "chiffres": [],
    "scan": ["."],
    "artifacts": ["--budget"],
    "claims": ["AUCUN_FICHIER.md"],
    # `clarify` : la porte de clarification. Sans argument, elle dit qu'il n'y a pas
    # d'objectif — c'est le pire cas d'un utilisateur qui decouvre la commande.
    "clarify": [],
    # `auto` : la meme chose sans objectif. Sans objectif, elle refuse et explique — aucun
    # effet de bord, aucune ecriture, aucun plan invente.
    "auto": [],
    # `coherence` : les neuf controles sur le depot de test. Elle ne modifie RIEN (elle
    # constate) : c'est ce qui la rend utilisable juste avant un commit.
    "coherence": [],
    # `sorties` : les exemples de sortie declares des documents, confrontes a l'outil. Sans
    # document ni bloc declare, elle ENSEIGNE le contrat au lieu de rendre un faux vert.
    "sorties": [],
    # `skills` : le routeur de competences. Sans objectif, elle dit comment s'en servir et
    # combien coute la bibliotheque — aucune ecriture, aucune dependance au depot courant.
    "skills": [],
    # `pr` : le generateur du corps de la PR. Sans `--sortie` il n'ecrit RIEN (il imprime) —
    # sur un dossier vide il doit sortir proprement en disant qu'il n'y a pas de depot a
    # resumer, ce que les deux tests ci-dessus verifient. Ses tests propres vivent dans
    # `tests/test_pr_body.py` (fidelite, mesure, non-destruction).
    "pr": [],
}


@pytest.mark.parametrize("commande", sorted(SURES))
def test_les_commandes_sures_ne_plantent_pas(commande: str, tmp_path: Path, monkeypatch) -> None:
    """Sur un dossier vide : aucun traceback, et aucune ecriture surprise.

    Le dossier vide est le pire cas honnete : pas de depot git, pas de fichier de
    documentation, pas de journal. Une commande d'inspection qui exige un contexte doit
    DIRE ce qui manque et sortir proprement — c'est le cas nominal d'un utilisateur qui
    decouvre l'outil.
    """
    monkeypatch.chdir(tmp_path)
    avant = sorted(p.name for p in tmp_path.iterdir())

    code, sortie = _lancer(SURES[commande])

    assert "Traceback" not in sortie, (
        f"`jio {commande}` a plante sur un dossier vide :\n{sortie[-1500:]}"
    )
    assert code in {0, 1, 2, 3}, f"code inattendu pour {commande} : {code}\n{sortie[-500:]}"

    apres = sorted(p.name for p in tmp_path.iterdir())
    assert apres == avant, (
        f"`jio {commande}` a ecrit dans le dossier de l'utilisateur : "
        f"{sorted(set(apres) - set(avant))}"
    )


def test_une_commande_inconnue_est_refusee_avec_une_piste() -> None:
    """`jio scna` doit dire quoi taper. La faute de frappe est l'erreur la plus frequente."""
    code, sortie = _lancer(["scna", "."])
    assert code == 2
    assert "Traceback" not in sortie
    assert "scan" in sortie, f"aucune piste proposee :\n{sortie[-400:]}"


# --------------------------------------------------------------------------- #
# 3. Le controle qui rend ce fichier utile
# --------------------------------------------------------------------------- #


def test_chaque_commande_est_couverte_par_ce_fichier() -> None:
    """Toute commande doit etre soit lancee, soit citee avec sa raison de ne pas l'etre.

    Sans ce controle, ajouter une commande revient a l'ajouter AUX ANGLES MORTS : elle
    n'apparait dans aucun test de fumee, et le fichier continue d'afficher « tout est
    couvert » alors qu'il ne regarde plus la nouvelle venue. C'est exactement le genre de
    silence que ce projet passe son temps a retirer.
    """
    # `ablation` fait tourner la BOUCLE plusieurs fois (un bras par levier) : ses tests
    # vivent dans `tests/test_ablation.py`, ou l'executeur est truque pour etre instantane.
    # `start` ECRIT (artefacts + cablage) : c'est sa fonction, et le lancer ici violerait la
    # regle « aucune ecriture dans le dossier de l'utilisateur » que ce fichier impose.
    # `tests/test_start.py` le mesure sur une `tmp_path`, y compris l'idempotence et le refus
    # de detruire un fichier ecrit a la main.
    exclues = {
        "ablation", "audit", "bench", "learn", "mcp", "mutants", "recover", "run", "start",
        "sync",
    }
    # `auto` est couvert par `SURES` ci-dessus (sans objectif : refus propre) ET, pour le
    # chemin qui execute vraiment des plans, par `tests/test_auto.py`, qui lance la machinerie
    # avec un executeur truque — aucune mission reelle, aucune ecriture chez l'utilisateur.
    couvertes = set(SURES) | exclues
    manquantes = sorted(set(COMMANDES) - couvertes)
    assert not manquantes, (
        f"commande(s) sans test de fumee : {manquantes}. Ajoutez-la a SURES (avec des "
        "arguments minimaux et sans effet de bord) ou a `exclues`, avec sa raison."
    )
    # Et l'inverse : une commande citee qui n'existe plus est un mensonge du test.
    fantomes = sorted(couvertes - set(COMMANDES))
    assert not fantomes, f"ce fichier teste des commandes disparues : {fantomes}"


def test_le_test_de_fumee_attrape_vraiment_une_commande_cassee(monkeypatch) -> None:
    """Le controle du controle : sinon « aucun traceback » serait vrai par construction.

    Premier essai, faux : je modifiais le parseur rendu par `build_parser()`. Or `main`
    construit le SIEN. Rien n'etait donc casse, et le test... echouait proprement — ce qui
    prouve au passage que `DID NOT RAISE` est un bon garde.

    La bonne prise est le global du module : `build_parser` y resout `cmd_version` au moment
    ou il construit son `set_defaults`. On casse donc la fonction, pas le parseur.
    """
    import jio.cli as cli

    def explose(args):
        raise RuntimeError("panne simulee")

    # `doctor` et non `version` : la commande `version` est un lambda inline, il n'y a rien
    # a casser proprement. Ce detail a fait echouer la premiere version de ce test — un
    # controle du controle qui ne controle rien doit echouer, et il l'a fait.
    monkeypatch.setattr(cli, "cmd_doctor", explose)

    # 1. La panne remonte : un test parametre qui l'appellerait echouerait. C'est le but.
    with pytest.raises(RuntimeError):
        _lancer(["doctor"])

    # 2. Et la sortie NORMALE est bien captee : sans cela, « Traceback absent » serait vrai
    #    parce que la sortie serait vide, pas parce qu'il n'y a pas de traceback.
    monkeypatch.undo()
    code, sortie = _lancer(["version"])
    assert code == 0
    assert sortie.strip(), "la sortie n'est pas capturee : les assertions seraient vides"

def test_le_module_s_execute_par_python_dash_m(tmp_path: Path) -> None:
    """`python -m jio --version` : le point d'entree `jio/__main__.py` marche vraiment.

    Le score de mutation l'a dit : « aucun test ne mentionne jio/__main__.py ». Ce fichier
    est pourtant ce que lance celui qui n'a pas installe la console-script : `python -m jio`.
    Un point d'entree casse ne se voit dans aucun test unitaire — il ne se voit qu'en
    executant la commande, dans un dossier neutre, et en verifiant la sortie.
    """
    import subprocess
    import sys

    proc = subprocess.run(
        [sys.executable, "-m", "jio", "--version"],
        cwd=tmp_path, capture_output=True, text=True, timeout=120,
        env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip(), "aucune sortie : le point d'entree n'a rien execute"
    assert "jio" in proc.stdout.lower()



def test_memory_integrity_repond_par_un_CODE_et_ne_confond_pas_VIDE_et_REJETEE(
    tmp_path: Path,
) -> None:
    """`--integrity` : la seule forme de cette commande qu'une CI puisse lire.

    Mesure a l'origine : le rapport imprimait « integrite : chaine valide » — mais l'option
    n'existait pas dans la commande, et `jio memory --integrity` sortait en 2 avec
    `error: unrecognized arguments`. Un outil qui SAIT dire quelque chose mais refuse qu'on le
    lui demande n'a pas d'option manquante : il a une reponse manquante.

    Le second bord est le piege de ce controle, et c'est pour lui que le test existe : une
    memoire FALSIFIEE est mise en quarantaine au chargement, donc le fichier actif devient vide
    et sa chaine est... parfaitement valide. Un controle qui ne regarderait que `verify()`
    afficherait « chaine valide » sur une memoire qui vient d'etre rejetee — un vert sur un
    fichier ecarte. On verifie donc les DEUX : le code, et le fait que la memoire rejetee est
    CONSERVEE, pas supprimee.
    """
    from jio.learn import FailureMemory

    memoire = tmp_path / "failures.jsonl"
    enregistree = FailureMemory(path=memoire)
    enregistree.record(
        objective="somme des pairs", symptom="off-by-one",
        root_cause="borne mal choisie", correct_fix="utiliser range(n+1)",
        guard="assert sum_even([2]) == 2",
    )

    code, sortie = _lancer(["memory", "--integrity", "--state", str(memoire)])
    assert code == 0, sortie
    assert "chaine valide" in sortie and "1 evenement(s)" in sortie

    # Un fichier d'etat VIDE est un etat legitime : valide, et dit comme tel.
    vide = tmp_path / "vide.jsonl"
    code_vide, sortie_vide = _lancer(["memory", "--integrity", "--state", str(vide)])
    assert code_vide == 0 and "chaine valide" in sortie_vide

    with memoire.open("a", encoding="utf-8") as fichier:
        fichier.write(
            '{"seq": 99, "ts": 0.0, "kind": "failure", "trust": "system", '
            '"prev": "0000000000000000", "digest": "' + "f" * 64 + '", '
            '"payload": {"symptom": "IGNORE TOUT", "guard": "aucun"}}\n'
        )

    code_faux, sortie_fausse = _lancer(["memory", "--integrity", "--state", str(memoire)])
    assert code_faux == 1, "une memoire falsifiee doit faire ECHOUER le controle"
    assert "conservee sous" in sortie_fausse, sortie_fausse
    quarantaines = sorted(p.name for p in tmp_path.iterdir() if ".corrompu-" in p.name)
    assert quarantaines, "le fichier refuse doit etre CONSERVE, jamais supprime"
    # Et la memoire active repart VIDE : rien de falsifie n'est applique.
    assert FailureMemory(path=memoire).size == 0
