"""Recuperer un depot reinitialise sans perdre un octet — prouve sur une vraie simulation.

L'accident est arrive **trois fois** pendant le developpement de ce projet : `.git` restaure
a son etat initial, le travail intact sur le disque, mais plus rien de suivi. Le script ecrit
pour cela (`scripts/sync.sh`) refuse de travailler des que `git status` n'est pas vide — et
dans cet accident, tout est precisement « non suivi ». **L'outil de secours refusait le
sinistre pour lequel il avait ete ecrit.**

Ces tests construisent l'accident POUR DE VRAI (un depot distant, un clone, puis la
destruction de l'historique local) au lieu de le simuler en memoire. C'est la seule facon de
savoir si la commande repare, et c'est ainsi qu'a ete trouve le defaut de `-uall` : un
`git status` sans cette option regroupe un dossier non suivi en UNE ligne, si bien qu'un
projet de 34 fichiers organises en dossiers n'affichait que 2 entrees et que le detecteur
laissait passer l'accident.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from jio.cli import main
from jio.recover import empreinte_accident, empreinte_arbre, recuperer

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git absent")


def _git(racine: Path, *argv: str, avec_identite: bool = True) -> str:
    commande = ["git"]
    if avec_identite:
        commande += ["-c", "user.email=a@b", "-c", "user.name=test"]
    commande += list(argv)
    proc = subprocess.run(commande, cwd=racine, capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, f"{commande} -> {proc.stderr}"
    return proc.stdout.strip()


def _remplir(racine: Path, combien: int = 25) -> None:
    (racine / "jio").mkdir(exist_ok=True)
    (racine / "docs").mkdir(exist_ok=True)
    for i in range(combien):
        (racine / "jio" / f"module_{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
    for i in range(8):
        (racine / "docs" / f"doc_{i}.md").write_text(f"# doc {i}\n", encoding="utf-8")
    (racine / "jio" / "sante.py").write_text('def sante():\n    return "intact"\n',
                                             encoding="utf-8")


@pytest.fixture()
def incident(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    """Un depot distant sain, un clone, puis l'accident : rend `(travail, distant)`.

    La reproduction est fidele a ce qui s'est passe trois fois : `.git` detruit et
    reinitialise, `origin` re-declare, un commit vide, et tout le travail « non suivi ».
    """
    monkeypatch.chdir(tmp_path)
    distant = tmp_path / "distant.git"
    _git(tmp_path, "init", "-q", "--bare", "--initial-branch=main", str(distant))

    # Le depot de travail est construit sur place puis pousse : cloner le depot nu ne
    # marche pas tant qu'il est vide (« Remote branch main not found »), et un clone
    # n'apporterait rien a la simulation.
    travail = tmp_path / "travail"
    _git(tmp_path, "init", "-q", "-b", "main", str(travail))
    _remplir(travail)
    _git(travail, "add", "-A")
    _git(travail, "commit", "-q", "-m", "travail reel")
    _git(travail, "remote", "add", "origin", str(distant))
    _git(travail, "push", "-q", "-u", "origin", "main")

    # --- l'accident ---
    shutil.rmtree(travail / ".git")
    _git(travail, "init", "-q", "-b", "main")
    _git(travail, "remote", "add", "origin", str(distant))
    # Le refspec d'origine ne recuperait que `main` : c'est ce qui a rendu l'accident
    # invisible (`git push` sans reference de suivi).
    _git(travail, "config", "remote.origin.fetch", "+refs/heads/main:refs/remotes/origin/main")
    _git(travail, "commit", "-q", "--allow-empty", "-m", "Initial commit")

    return travail, distant


# --------------------------------------------------------------------------- #
# 1. L'empreinte de l'accident : deux seuils, et le piege des dossiers
# --------------------------------------------------------------------------- #


def test_l_empreinte_de_l_accident_est_reconnue(incident: tuple[Path, Path]) -> None:
    travail, _ = incident
    signature = empreinte_accident(travail)
    assert signature is not None
    commits, non_suivis = signature
    assert commits == 1
    # 33 fichiers + le dossier : c'est le compte REEL des fichiers, pas celui des dossiers.
    assert non_suivis >= 30, non_suivis


def test_le_detecteur_compte_les_FICHIERS_et_non_les_dossiers(
    incident: tuple[Path, Path],
) -> None:
    """Le piege qui aurait rendu le detecteur aveugle sur un vrai projet.

    `git status --porcelain` regroupe un dossier non suivi en UNE ligne (`?? jio/`). Sans
    `--untracked-files=all`, les 34 fichiers organises en dossiers n'affichaient que 2
    entrees — sous le seuil de 20, donc l'accident passait inapercu. Mesure faite sur la
    simulation : 2 lignes sans l'option, 34 avec.
    """
    travail, _ = incident
    sans = _git(travail, "status", "--porcelain")
    avec = _git(travail, "status", "--porcelain", "--untracked-files=all")
    lignes_sans = sum(1 for l in sans.splitlines() if l.startswith("??"))
    lignes_avec = sum(1 for l in avec.splitlines() if l.startswith("??"))

    assert lignes_sans < 5, "le piege n'existe plus : ce test doit etre revu"
    assert lignes_avec == empreinte_accident(travail)[1]


def test_un_depot_sain_n_est_pas_touche(tmp_path: Path) -> None:
    """Un depot normal ne doit pas etre « recupere » : la commande refuse et n'agit pas."""
    travail = tmp_path / "sain"
    _git(tmp_path, "init", "-q", "-b", "main", str(travail))
    _remplir(travail)
    _git(travail, "add", "-A")
    _git(travail, "commit", "-q", "-m", "vrai historique")

    avant = empreinte_arbre(travail)
    resultat = recuperer(travail, branche="main")

    assert not resultat.fait
    assert "ne porte PAS l'empreinte" in resultat.motif
    assert empreinte_arbre(travail) == avant
    # Et le message dit quoi faire a la place.
    assert "scripts/sync.sh" in resultat.motif


# --------------------------------------------------------------------------- #
# 2. La recuperation : l'historique revient, les fichiers NE BOUGENT PAS
# --------------------------------------------------------------------------- #


def test_la_recuperation_restaure_l_historique_sans_toucher_aux_fichiers(
    incident: tuple[Path, Path],
) -> None:
    travail, _ = incident
    avant = empreinte_arbre(travail)
    attendu = _git(travail, "rev-parse", "main@{1}" if False else "HEAD")

    resultat = recuperer(travail, branche="main")

    assert resultat.fait, resultat.motif
    assert resultat.contenu_intact, "un fichier du disque a change"
    assert empreinte_arbre(travail) == avant
    # L'historique est celui du DISTANT, plus le commit initial.
    assert _git(travail, "log", "--oneline") != attendu
    assert _git(travail, "rev-parse", "HEAD") == _git(travail, "rev-parse", "origin/main")
    # Et l'etiquette rend l'ancien etat joignable : rien ne disparait.
    assert resultat.etiquette
    assert _git(travail, "tag", "--list", resultat.etiquette) == resultat.etiquette


def test_le_travail_local_non_pousse_survit_a_la_recuperation(
    incident: tuple[Path, Path],
) -> None:
    """LE cas qui decide si la commande est sure : du travail jamais pousse.

    Un fichier neuf et une modification locale, tous deux inconnus du distant. Apres
    recuperation, ils doivent etre **la**, indexes, et inchanges — sinon la commande
    detruit exactement ce qu'elle est censee sauver.
    """
    travail, _ = incident
    neuf = travail / "travail_local.py"
    neuf.write_text('def local():\n    return "pas encore pousse"\n', encoding="utf-8")
    modifie = travail / "jio" / "sante.py"
    modifie.write_text('def sante():\n    return "MODIFIE LOCALEMENT"\n', encoding="utf-8")
    avant = empreinte_arbre(travail)

    resultat = recuperer(travail, branche="main")

    assert resultat.fait, resultat.motif
    assert resultat.contenu_intact
    assert empreinte_arbre(travail) == avant
    # Le travail local est INDEXE (donc visible et pret a commiter), pas perdu.
    statut = _git(travail, "status", "--short")
    assert "travail_local.py" in statut
    assert "jio/sante.py" in statut
    assert "MODIFIE LOCALEMENT" in modifie.read_text(encoding="utf-8")
    assert resultat.fichiers_modifies >= 2


def test_aucune_commande_destructive_n_est_utilisee(
    incident: tuple[Path, Path],
) -> None:
    """Controle de doctrine, verifie sur les commandes REELLEMENT listees.

    Un `--hard`, un `checkout` ou un `clean` detruirait le travail non suivi — c'est-a-dire
    le seul travail qui existe dans cet accident. Les operations rendues par la
    recuperation sont explicitement inspectees.
    """
    travail, _ = incident
    resultat = recuperer(travail, branche="main")

    operations = " ; ".join(resultat.operations)
    for interdite in ("--hard", "checkout", "clean", "restore", "stash"):
        assert interdite not in operations, operations
    assert "reset --soft" in operations


# --------------------------------------------------------------------------- #
# 3. La simulation, et le refus quand il n'y a rien a faire
# --------------------------------------------------------------------------- #


def test_la_simulation_ne_modifie_rien(incident: tuple[Path, Path]) -> None:
    travail, _ = incident
    avant = empreinte_arbre(travail)
    revision_avant = _git(travail, "rev-parse", "HEAD")

    resultat = recuperer(travail, branche="main", dry_run=True)

    assert not resultat.fait
    assert "simulation" in resultat.motif
    assert empreinte_arbre(travail) == avant
    assert _git(travail, "rev-parse", "HEAD") == revision_avant
    assert any("simulation" in operation for operation in resultat.operations)


def test_la_commande_rend_0_si_elle_a_repare_et_1_sinon(
    incident: tuple[Path, Path], capsys
) -> None:
    """Un appelant doit pouvoir distinguer « repare » de « rien fait, a examiner »."""
    travail, _ = incident
    assert main(["recover", "--root", str(travail)]) == 0
    sortie = capsys.readouterr().out
    assert "INTACT" in sortie
    assert "reset --soft" in sortie

    # Deuxieme passage : l'empreinte a disparu, la commande refuse et le DIT.
    assert main(["recover", "--root", str(travail)]) == 1
    assert "ne porte PAS l'empreinte" in capsys.readouterr().out


def test_la_simulation_est_une_inspection_REUSSIE(
    incident: tuple[Path, Path], capsys
) -> None:
    """`--dry-run` rend 0 : un script ne doit pas confondre « voici le plan » avec un echec.

    Sinon `jio recover --dry-run` se comporte comme une panne dans toute chaine d'outils —
    et la simulation, qui est justement le mode sur, devient inutilisable.
    """
    travail, _ = incident
    assert main(["recover", "--dry-run", "--root", str(travail)]) == 0
    sortie = capsys.readouterr().out
    assert "simulation : l'historique serait restaure" in sortie
    assert "simulation" in sortie

    # Une simulation qui NE PEUT PAS etablir de plan, elle, echoue bien.
    assert main(["recover", "--dry-run", "--root", str(travail), "--branch", "fantome"]) == 1


def test_une_branche_inconnue_donne_les_noms_disponibles(
    incident: tuple[Path, Path], capsys
) -> None:
    """Apres un incident, le nom de la branche est parfois la seule chose qu'on ignore.

    Refuser en disant « aucune reference distante » laisse l'utilisateur deviner. Lister ce
    que le distant publie vraiment transforme le refus en instruction.
    """
    travail, _ = incident
    resultat = recuperer(travail, branche="fantome")
    assert not resultat.fait
    assert "aucune reference distante pour `fantome`" in resultat.motif
    assert "Branches presentes sur le distant" in resultat.motif
    assert "main" in resultat.motif


def test_les_preuves_d_un_autre_monde_sont_signalees(incident: tuple[Path, Path]) -> None:
    """Restaurer l'historique ne restaure pas les preuves : il faut le dire.

    Un journal enchaine prouve qu'il n'a pas ete altere ; il ne prouve pas que le monde n'a
    pas change. Ici, deux evenements sont ecrits, puis le travail continue (le monde
    change), puis l'accident arrive : les preuves portent desormais sur un etat qui n'existe
    plus. La recuperation doit l'annoncer, sans effacer ni invalider quoi que ce soit.

    Mesure honnete faite en ecrivant ce test : quand le monde n'a PAS change (cas normal de
    `jio recover`, qui ne touche aucun fichier), le compte est zero et rien n'est affiche.
    Un avertissement qui se declenche toujours ne dit plus rien.
    """
    from jio.core.journal import Journal

    travail, _ = incident
    journal = Journal(path=travail / ".jio" / "journal.jsonl", racine=travail)
    journal.append("mission", {"id": "avant"})
    journal.append("verdict", {"ok": True})

    # Le monde change apres les preuves.
    (travail / "src").mkdir(exist_ok=True)
    (travail / "src" / "neuf.py").write_text("y = 1\n", encoding="utf-8")

    resultat = recuperer(travail, branche="main")

    assert resultat.fait, resultat.motif
    assert resultat.preuves_total == 2
    assert resultat.preuves_perimees == 2, (
        "les preuves portant sur l'etat precedent n'ont pas ete signalees"
    )


def test_une_recuperation_qui_ne_change_rien_aux_fichiers_ne_perime_rien(
    incident: tuple[Path, Path],
) -> None:
    """Le cas nominal : `recover` ne touche pas aux fichiers, donc les preuves restent valides.

    C'est ce que l'empreinte avant/apres etablit. Signaler une peremption ici serait un faux
    positif — et un faux positif sur un avertissement de surete est pire qu'une absence.
    """
    from jio.core.journal import Journal

    travail, _ = incident
    journal = Journal(path=travail / ".jio" / "journal.jsonl", racine=travail)
    journal.append("mission", {"id": "avant"})

    resultat = recuperer(travail, branche="main")

    assert resultat.fait, resultat.motif
    assert resultat.preuves_total == 1
    assert resultat.preuves_perimees == 0
