"""Tests de l'integrite d'etat : le depot ne doit jamais reculer en silence.

Incident reel a l'origine de ces tests : entre deux sessions, l'environnement a
restaure `.git` a son etat INITIAL. Le code etait intact sur le disque, mais le depot
ne suivait plus rien — `git status` affichait tout le projet comme « non suivi » et
`git log` revenait au commit initial. Rien ne l'annoncait.

Deux consequences, toutes deux traitees ici :
  * `jio doctor` doit le DIRE (« en retard de N commits », ou « aucun distant
    comparable ») au lieu d'afficher « 0 en retard » quand il ne peut rien comparer ;
  * `scripts/sync.sh` doit reparer SANS POUVOIR perdre de travail : refus si l'arbre
    est modifie, avance rapide seule quand c'est possible, et une etiquette de
    sauvegarde avant tout ecrasement explicite.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[1]
SYNC = REPO / "scripts" / "sync.sh"


def _run(argv, cwd):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60)


def _git(cwd, *argv):
    return _run(["git", *argv], cwd)


def _init_repo(base: pathlib.Path, name: str = "travail") -> pathlib.Path:
    """Depot distant nu + copie de travail, deja synchronises (aucun reseau)."""
    base.mkdir(parents=True, exist_ok=True)
    origin = base / "origin.git"
    _git(base, "init", "-q", "--bare", "-b", "main", str(origin))
    travail = base / name
    _git(base, "clone", "-q", str(origin), str(travail))
    _git(travail, "config", "user.email", "test@exemple.invalid")
    _git(travail, "config", "user.name", "Test")
    (travail / "a.txt").write_text("un\n", encoding="utf-8")
    _git(travail, "add", "-A")
    _git(travail, "commit", "-qm", "initial")
    _git(travail, "push", "-q", "-u", "origin", "main")
    return travail


def _sync(travail: pathlib.Path, *args: str):
    return _run(["sh", str(SYNC), *args], cwd=travail)


# --------------------------------------------------------------------------- #
# scripts/sync.sh
# --------------------------------------------------------------------------- #

def test_sync_refuse_de_toucher_a_un_arbre_modifie(tmp_path):
    """Regle numero un : jamais de destruction de travail non enregistre."""
    travail = _init_repo(tmp_path)
    (travail / "brouillon.txt").write_text("en cours\n", encoding="utf-8")

    res = _sync(travail)

    assert res.returncode == 1, res.stdout + res.stderr
    assert "REFUS" in res.stdout
    assert (travail / "brouillon.txt").exists(), "le fichier non suivi a ete supprime"
    assert "brouillon.txt" in res.stdout, "le refus doit nommer ce qui gene"


def test_sync_avance_rapidement_sans_perdre_aucun_commit(tmp_path):
    """Le seul cas ou l'operation ne peut rien detruire : le local est en retard pur."""
    travail = _init_repo(tmp_path)
    autre = _run(["git", "clone", "-q", str(tmp_path / "origin.git"), str(tmp_path / "autre")],
                 tmp_path).returncode
    assert autre == 0
    autre = tmp_path / "autre"
    _git(autre, "config", "user.email", "t@exemple.invalid")
    _git(autre, "config", "user.name", "T")
    (autre / "a.txt").write_text("un\ndeux\n", encoding="utf-8")
    _git(autre, "commit", "-qam", "distant avance")
    _git(autre, "push", "-q", "origin", "main")

    avant = _git(travail, "rev-parse", "HEAD").stdout.strip()
    res = _sync(travail)

    assert res.returncode == 0, res.stdout + res.stderr
    apres = _git(travail, "rev-parse", "HEAD").stdout.strip()
    assert apres != avant
    assert _git(travail, "merge-base", "--is-ancestor", avant, apres).returncode == 0, (
        "l'ancien etat doit rester un ancetre : rien n'a ete reecrit"
    )
    assert (travail / "a.txt").read_text(encoding="utf-8") == "un\ndeux\n"


def test_sync_refuse_d_ecraser_des_historiques_diverges(tmp_path):
    """Divergence : on montre les deux cotes et on s'arrete, code de retour 1."""
    travail = _init_repo(tmp_path)
    (travail / "local.txt").write_text("moi\n", encoding="utf-8")
    _git(travail, "add", "-A")
    _git(travail, "commit", "-qm", "commit LOCAL")

    autre = tmp_path / "autre"
    _git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(autre))
    _git(autre, "config", "user.email", "t@exemple.invalid")
    _git(autre, "config", "user.name", "T")
    (autre / "a.txt").write_text("un\ndistant\n", encoding="utf-8")
    _git(autre, "commit", "-qam", "distant diverge")
    _git(autre, "push", "-q", "origin", "main")

    avant = _git(travail, "rev-parse", "HEAD").stdout.strip()
    res = _sync(travail)

    assert res.returncode == 1, res.stdout + res.stderr
    assert "DIVERGE" in res.stdout
    assert "commit LOCAL" in res.stdout and "distant diverge" in res.stdout
    assert _git(travail, "rev-parse", "HEAD").stdout.strip() == avant, (
        "un refus ne doit RIEN modifier"
    )


def test_sync_force_rend_l_ancien_etat_recuperable(tmp_path):
    """`--force` a le droit d'aligner, pas de faire disparaitre : etiquette d'abord."""
    travail = _init_repo(tmp_path)
    (travail / "local.txt").write_text("moi\n", encoding="utf-8")
    _git(travail, "add", "-A")
    _git(travail, "commit", "-qm", "commit LOCAL")
    perdu = _git(travail, "rev-parse", "HEAD").stdout.strip()

    autre = tmp_path / "autre"
    _git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(autre))
    _git(autre, "config", "user.email", "t@exemple.invalid")
    _git(autre, "config", "user.name", "T")
    (autre / "a.txt").write_text("un\ndistant\n", encoding="utf-8")
    _git(autre, "commit", "-qam", "distant diverge")
    _git(autre, "push", "-q", "origin", "main")

    res = _sync(travail, "--force")

    assert res.returncode == 0, res.stdout + res.stderr
    assert _git(travail, "rev-parse", "HEAD").stdout.strip() != perdu
    # Le commit ecrase doit rester joignable : c'est tout l'interet de l'etiquette.
    assert _git(travail, "cat-file", "-e", perdu).returncode == 0
    tags = _git(travail, "tag", "--list", "sauvegarde-avant-sync-*").stdout.split()
    assert tags, "aucune etiquette de sauvegarde posee"
    assert _git(travail, "merge-base", "--is-ancestor", perdu, tags[0]).returncode == 0


def test_sync_est_idempotent(tmp_path):
    """Deux executions d'affilee : la seconde ne fait rien et le dit."""
    travail = _init_repo(tmp_path)
    assert _sync(travail).returncode == 0
    seconde = _sync(travail)
    assert seconde.returncode == 0
    assert "deja a jour" in seconde.stdout.lower()


# --------------------------------------------------------------------------- #
# jio doctor : dire ce qu'on ne peut pas savoir
# --------------------------------------------------------------------------- #

def test_doctor_detecte_le_retard_sur_le_distant(tmp_path):
    """Un depot en retard doit etre SIGNALE, avec la commande de reparation."""
    travail = _init_repo(tmp_path)
    autre = tmp_path / "autre"
    _git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(autre))
    _git(autre, "config", "user.email", "t@exemple.invalid")
    _git(autre, "config", "user.name", "T")
    (autre / "a.txt").write_text("un\ndeux\n", encoding="utf-8")
    _git(autre, "commit", "-qam", "distant avance")
    _git(autre, "push", "-q", "origin", "main")
    _git(travail, "fetch", "-q", "origin", "main:refs/remotes/origin/main")

    # On interroge la fonction elle-meme (elle lit le depot courant).
    import os

    ancien = os.getcwd()
    os.chdir(travail)
    try:
        from jio.cli import _git_state

        etat = _git_state()
    finally:
        os.chdir(ancien)

    assert etat is not None
    branche, avance, recul, distant, distant_existe = etat
    assert distant is True and distant_existe is True
    assert recul == 1 and avance == 0, etat


def test_doctor_avoue_quand_il_ne_peut_pas_comparer(tmp_path):
    """Sans distant comparable, « 0 en retard » serait un mensonge par omission.

    C'est exactement le silence qui a laisse passer le retour en arriere du depot :
    tout paraissait normal.
    """
    travail = tmp_path / "isole"
    travail.mkdir()
    _git(travail, "init", "-q", "-b", "main")
    _git(travail, "config", "user.email", "t@exemple.invalid")
    _git(travail, "config", "user.name", "T")
    (travail / "x.txt").write_text("x\n", encoding="utf-8")
    _git(travail, "add", "-A")
    _git(travail, "commit", "-qm", "seul")

    import os

    ancien = os.getcwd()
    os.chdir(travail)
    try:
        from jio.cli import _git_state

        etat = _git_state()
    finally:
        os.chdir(ancien)

    assert etat is not None
    assert etat[3] is False, "l'absence de distant comparable doit etre avouee"
    assert etat[4] is False, "et l'absence de distant CONFIGURE doit etre distinguee"


def test_doctor_n_ecrit_jamais_dans_le_depot():
    """Un diagnostic qui agit est un diagnostic qu'on n'ose plus lancer."""
    avant = _git(REPO, "status", "--porcelain").stdout
    res = _run([sys.executable, "-m", "jio", "doctor"], cwd=REPO)
    assert res.returncode == 0
    assert "Etat du depot" in res.stdout
    apres = _git(REPO, "status", "--porcelain").stdout
    assert avant == apres, "`doctor` a modifie le depot"


def test_un_distant_configure_sans_reference_comparable_est_distingue(tmp_path):
    """Deux situations differentes, et le diagnostic doit le dire.

    Constate en usage reel : un depot avec `origin` configure mais sans reference
    locale de la branche affichait « aucun depot `origin` : impossible de dire si ce
    travail est sauvegarde ailleurs ». C'etait faux : le distant etait la. La seule
    chose qui manquait etait un `git fetch` — et l'utilisateur, lui, etait envoye
    verifier `git remote -v`.

    Un diagnostic qui se trompe sur la CAUSE est pire qu'un diagnostic muet : il
    envoie reparer ce qui n'est pas casse.
    """
    import os

    travail = tmp_path / "avec-distant"
    travail.mkdir()
    _git(travail, "init", "-q", "-b", "main")
    _git(travail, "config", "user.email", "t@exemple.invalid")
    _git(travail, "config", "user.name", "T")
    (travail / "x.txt").write_text("x\n", encoding="utf-8")
    _git(travail, "add", "-A")
    _git(travail, "commit", "-qm", "seul")
    # Un distant CONFIGURE, mais aucune reference locale recuperee : c'est l'etat
    # exact dans lequel on ne peut pas comparer.
    _git(travail, "remote", "add", "origin", "https://exemple.invalid/x.git")

    ancien = os.getcwd()
    os.chdir(travail)
    try:
        from jio.cli import _git_state

        etat = _git_state()
    finally:
        os.chdir(ancien)

    assert etat is not None
    branche, avance, recul, distant, distant_existe = etat
    assert distant is False, "sans reference locale, impossible de comparer"
    assert distant_existe is True, "mais le distant existe : le diagnostic doit le dire"
    assert branche == "main"
