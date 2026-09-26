"""Le depot peut perdre son historique SANS LE DIRE — il doit le dire.

Incident reel, vecu **deux fois** par ce projet : entre deux sessions, l'environnement
d'execution restaure `.git` a son etat initial. Le travail est intact sur le disque, mais
le depot ne suit plus rien : `git log` revient au commit initial, `git status` affiche tout
le code comme « non suivi », et `.git/config` ne connait meme plus notre branche (le
refspec d'origine ne recupere que `main`).

Les avertissements existants de `doctor` parlaient du DISTANT (« en retard », « reference
absente »). Ils supposent qu'on peut comparer — or dans cet accident la reference distante
vient d'etre effacee avec le reste. Il fallait un signal qui ne depende d'aucun reseau :
un depot qui contient beaucoup de fichiers de projet et presque aucun commit est
l'empreinte exacte de cet accident.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from jio.cli import _depot_suspect, main

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git absent")


def _git(*argv: str, cwd: Path) -> None:
    subprocess.run(
        ["git", "-c", "user.email=a@b", "-c", "user.name=test", *argv],
        cwd=cwd, check=True, capture_output=True,
    )


@pytest.fixture()
def depot_reinitialise(tmp_path: Path, monkeypatch) -> Path:
    """Un depot qui a l'empreinte de l'accident : 1 commit, et le travail non suivi."""
    monkeypatch.chdir(tmp_path)
    _git("init", "-q", cwd=tmp_path)
    _git("commit", "-q", "--allow-empty", "-m", "Initial commit", cwd=tmp_path)
    for i in range(25):
        (tmp_path / f"module_{i}.py").write_text("x = 1\n", encoding="utf-8")
    return tmp_path


def test_un_depot_reinitialise_est_detecte(depot_reinitialise: Path) -> None:
    suspect = _depot_suspect()
    assert suspect is not None, "l'accident n'est pas detecte"
    commits, non_suivis = suspect
    assert commits == 1
    assert non_suivis == 25


def test_un_depot_sain_n_est_pas_signale(tmp_path: Path, monkeypatch) -> None:
    """Le controle doit se taire sur un depot normal : un faux positif ici ferait
    ignorer l'avertissement le jour ou il compte."""
    monkeypatch.chdir(tmp_path)
    _git("init", "-q", cwd=tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git("add", "-A", cwd=tmp_path)
    _git("commit", "-q", "-m", "vrai travail", cwd=tmp_path)
    for i in range(25):
        _git("commit", "-q", "--allow-empty", "-m", f"etape {i}", cwd=tmp_path)
    assert _depot_suspect() is None


def test_un_projet_neuf_avec_quelques_fichiers_n_est_pas_signale(
    tmp_path: Path, monkeypatch
) -> None:
    """Un depot tout neuf n'a pas l'empreinte de l'accident : il faut les DEUX signaux.

    Le seuil est volontairement large (20 fichiers non suivis ET <= 3 commits) : rater un
    vrai accident coute l'historique du projet, signaler un depot neuf coute une ligne
    d'avertissement fausse — et un faux positif ici ferait ignorer le vrai.
    """
    monkeypatch.chdir(tmp_path)
    _git("init", "-q", cwd=tmp_path)
    _git("commit", "-q", "--allow-empty", "-m", "Initial commit", cwd=tmp_path)
    for i in range(3):
        (tmp_path / f"note_{i}.md").write_text("brouillon\n", encoding="utf-8")
    assert _depot_suspect() is None


def test_doctor_dit_la_REPARATION_et_pas_seulement_le_probleme(
    depot_reinitialise: Path, capsys
) -> None:
    """Un diagnostic sans commande a lancer laisse l'utilisateur sans prise.

    L'essentiel : la sortie doit nommer `jio recover`, la commande qui restaure
    l'historique distant SANS toucher aux fichiers du disque — et elle doit exister.
    Conseiller une commande inexistante serait pire que ne rien conseiller, donc on
    l'execute ici pour de vrai (en simulation) : le conseil du diagnostic est verifie.
    """
    assert main(["doctor"]) == 0
    sortie = capsys.readouterr().out

    assert "DEPOT SUSPECT" in sortie
    assert "jio recover" in sortie
    assert "jio recover --dry-run" in sortie
    # Et pas de conseil dangereux. Le controle porte sur les LIGNES DE COMMANDE, pas sur
    # le mot : la sortie dit elle-meme « ni --hard, ni checkout, ni clean » pour rassurer,
    # et un test qui interdit la chaine quelque part punirait cette phrase honnete.
    conseils = [
        ligne.strip() for ligne in sortie.splitlines()
        if ligne.strip().startswith(("$ git", "git ", "$ jio", "jio "))
    ]
    dangereux = [c for c in conseils if "--hard" in c or "clean -" in c or "checkout --" in c]
    assert not dangereux, f"conseil destructeur dans le diagnostic : {dangereux}"


def test_sans_distant_le_message_dit_quoi_faire(depot_reinitialise: Path, capsys) -> None:
    """Apres une reinitialisation, `.git/config` est efface AVEC le reste.

    Le message disait « verifiez l'acces au depot distant » — un mauvais conseil quand il
    n'existe aucun distant a joindre : on envoie chercher une panne reseau inexistante.
    Il doit nommer la cause exacte et la commande qui la corrige.
    """
    assert main(["recover", "--dry-run", "--root", str(depot_reinitialise)]) == 1
    sortie = capsys.readouterr().out

    assert "aucun depot distant nomme `origin`" in sortie
    assert "git remote add origin" in sortie
    assert "Verifiez l'acces" not in sortie, "panne reseau inexistante : mauvais conseil"

    # Et la simulation doit vraiment n'avoir rien ecrit.
    assert main(["recover", "--dry-run", "--root", str(depot_reinitialise)]) == 1


def test_doctor_peut_diagnostiquer_un_AUTRE_depot(
    depot_reinitialise: Path, tmp_path_factory, monkeypatch, capsys
) -> None:
    """`--root` : diagnostiquer un depot sans s'y deplacer.

    Toutes les commandes du projet l'acceptent (`recover`, `scan`, `claims`, `sync`...)
    sauf `doctor` — il refusait l'argument et sortait en 2. Consequence concrete : un
    script qui diagnostique puis repare plusieurs depots devait changer de dossier entre
    les deux, ce qui rend la comparaison et l'enchainement fragiles.

    Pire qu'une option absente : une option qui ne fait rien. Le controle porte donc sur
    un depot qui n'est PAS le dossier courant, et sur les deux sens — il accuse celui qui
    est casse, et il se tait sur celui qui ne l'est pas.
    """
    # HORS du depot casse, et pas dedans : un depot cree dans le depot suspect lui ajoute
    # un fichier non suivi et change le compte annonce (26 au lieu de 25). Mesure faite —
    # le diagnostic etait juste, c'est le montage du test qui ne decrivait pas la fixture.
    sain = tmp_path_factory.mktemp("sain")
    _git("init", "-q", cwd=sain)
    (sain / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git("add", "-A", cwd=sain)
    _git("commit", "-q", "-m", "vrai travail", cwd=sain)
    for i in range(25):
        _git("commit", "-q", "--allow-empty", "-m", f"etape {i}", cwd=sain)

    # Le dossier courant reste le depot casse : c'est bien `--root` qui decide.
    assert main(["doctor", "--root", str(sain)]) == 0
    sortie_saine = capsys.readouterr().out
    assert "DEPOT SUSPECT" not in sortie_saine, "faux positif sur un depot sain"

    assert main(["doctor", "--root", str(depot_reinitialise)]) == 0
    sortie = capsys.readouterr().out
    assert "DEPOT SUSPECT" in sortie, "l'accident n'est pas vu quand le depot est vise"
    assert "25 fichier(s) NON SUIVIS" in sortie
