"""Le corps de la PR : un rapport GENERE, donc reconstructible et verifiable.

Ces tests existent a cause d'un incident reel, et ils sont ecrits pour qu'il ne se reproduise
pas. Le corps de la pull request vivait dans un fichier unique hors du depot, ecrit a la main
pendant plusieurs jours. Un evenement exterieur a efface ce fichier ; le tour suivant a pousse
une PR qui ne contenait plus qu'une section, et l'API GitHub ne rend pas l'historique des corps.
**Le seul endroit ou vivait la synthese de 82 commits etait aussi le seul qui n'en gardait
aucune copie.**

La sortie de l'incident n'est pas « faire plus attention » : c'est que la source de verite (les
commits) suffise a reconstruire le document. Trois proprietes sont donc verrouillees ici :

  1. **fidelite** — chaque commit de la branche apparait, dans l'ordre, avec son corps integral ;
  2. **mesure** — les compteurs annonces viennent de la mesure du depot, pas d'une saisie ; et
     quand la mesure est impossible, le rapport le DIT au lieu d'ecrire un zero ;
  3. **non-destruction** — ecrire le corps ne detruit jamais la version precedente.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from jio.pr import GitAbsent, base, commits, construire, ecrire


def _git(racine: Path, *arguments: str) -> None:
    subprocess.run(["git", *arguments], cwd=racine, check=True, capture_output=True, text=True)


def _depot(tmp_path: Path, messages: tuple[str, ...]) -> Path:
    """Un depot git reel avec une branche portant `messages`, dans l'ordre donne."""
    _git(tmp_path, "init", "-q", "-b", "main")
    identite = ("-c", "user.email=tests@jio", "-c", "user.name=Tests")
    (tmp_path / "base.txt").write_text("base\n", encoding="utf-8")
    _git(tmp_path, *identite, "add", "-A")
    _git(tmp_path, *identite, "commit", "-qm", "base: socle")
    _git(tmp_path, "checkout", "-qb", "branche")
    for rang, message in enumerate(messages):
        (tmp_path / f"f{rang}.txt").write_text(f"{rang}\n", encoding="utf-8")
        _git(tmp_path, *identite, "add", "-A")
        _git(tmp_path, *identite, "commit", "-qm", message)
    return tmp_path


def test_le_rapport_contient_CHAQUE_commit_dans_l_ordre(tmp_path: Path) -> None:
    """Fidelite : rien n'est resume, rien n'est choisi, rien n'est reordonne.

    Un filtre editorial ferait de ce rapport une plaidoirie. Ce qui se verifie, c'est que le
    document EST la branche : les sujets dans l'ordre des commits, et les corps integraux.
    """
    depot = _depot(tmp_path, (
        "premier: le defaut trouve\n\nLa mesure qui l'a montre, en clair.",
        "second: le correctif\n\nCe qui le verrouille desormais.",
    ))
    corps = construire(depot)

    assert corps.index("## 1. premier: le defaut trouve") < corps.index(
        "## 2. second: le correctif"
    ), "les sections ne suivent pas l'ordre des commits"
    assert "La mesure qui l'a montre, en clair." in corps
    assert "Ce qui le verrouille desormais." in corps
    # Le numero de section est un compteur : deux sections ne peuvent pas porter le meme.
    for rang in (1, 2):
        assert corps.count(f"## {rang}. ") == 1, f"section {rang} dupliquee ou absente"


def test_le_rapport_declare_SA_base_et_son_nombre_de_commits(tmp_path: Path) -> None:
    """Un rapport qui ne dit pas d'ou il part ne dit rien.

    La base est resolue automatiquement (`main` ici, faute de branche distante) : le lecteur
    doit pouvoir savoir ce qui est resume, et rejouer la meme commande pour obtenir le meme
    document.
    """
    depot = _depot(tmp_path, ("un: chose",))
    corps = construire(depot)

    ref, sha = base(depot)
    assert ref == "main"
    assert f"`{ref}`" in corps and f"`{sha}`" in corps
    assert "**1 commit(s)**" in corps
    # Et l'invariant de reproductibilite : deux generations de suite rendent le meme texte.
    assert construire(depot) == corps


def test_un_message_avec_accents_guillemets_et_retours_est_reproduit_INTEGRALEMENT(
    tmp_path: Path,
) -> None:
    """Le protocole de lecture ne doit pas dependre d'un caractere du message.

    Les messages de ce depot contiennent des accents, des guillemets francais, des tirets longs
    et des tableaux. Un separateur mal choisi les tronquerait en silence — et une troncature
    silencieuse dans un rapport est pire qu'une absence de rapport.
    """
    message = (
        "sujet: « accents », guillemets et tirets — ainsi que : des deux-points\n\n"
        "Un corps avec \"des guillemets droits\", des apostrophes l'air de rien,\n"
        "et un tableau :\n\n"
        "| a | b |\n| 1 | 2 |\n"
    )
    depot = _depot(tmp_path, (message,))
    corps = construire(depot)

    assert "« accents »" in corps
    assert "| a | b |" in corps
    assert "l'air de rien" in corps
    assert "tirets — ainsi" in corps


def test_la_mesure_impossible_est_DITE_et_non_remplacee_par_un_zero(tmp_path: Path) -> None:
    """Un compteur faux est pire qu'un compteur absent — et un zero muet est un chiffre faux.

    Ce depot de test n'a aucun fichier de test : `mesurer` refuse de rendre un nombre. Le
    rapport doit continuer a exister (il vient des commits) et DIRE que les compteurs ne sont
    pas mesures. Ecrire « 0 tests verts » serait un mensonge, et le pire des mensonges : un
    chiffre.
    """
    depot = _depot(tmp_path, ("un: chose",))
    corps = construire(depot)

    assert "Compteurs non mesures" in corps
    assert "0 tests verts" not in corps
    assert "## 1. un: chose" in corps, "les commits restent rapportes malgre la mesure impossible"


def test_ecrire_ne_detruit_JAMAIS_la_version_precedente(tmp_path: Path) -> None:
    """L'incident, transforme en garde-fou.

    Le fichier avait disparu sans copie. Un ecrivain qui ecrase sans sauvegarde transforme une
    erreur de chemin en perte definitive : l'ancienne version part donc dans `.avant-jio`
    AVANT l'ecriture, et rien n'est ecrit quand le contenu est identique (sinon « inchange » et
    « ecrit » seraient indiscernables).
    """
    cible = tmp_path / "corps.md"
    sauvegarde, ecrit = ecrire(cible, "premiere version")
    assert ecrit and sauvegarde is None
    assert cible.read_text(encoding="utf-8") == "premiere version"

    # Contenu identique : aucune ecriture, et l'appelant le SAIT.
    avant = cible.stat().st_mtime_ns
    sauvegarde, ecrit = ecrire(cible, "premiere version")
    assert not ecrit and sauvegarde is None
    assert cible.stat().st_mtime_ns == avant, "un contenu identique a ete reecrit"

    # Contenu different : l'ancien est conserve, puis la nouvelle version ecrite.
    sauvegarde, ecrit = ecrire(cible, "seconde version")
    assert ecrit and sauvegarde is not None
    assert sauvegarde.read_text(encoding="utf-8") == "premiere version"
    assert cible.read_text(encoding="utf-8") == "seconde version"


def test_sans_depot_git_le_module_le_DIT_au_lieu_de_planter(tmp_path: Path) -> None:
    """Un generateur de rapport sur un dossier sans git n'a rien a resumer, et le dit."""
    with pytest.raises(GitAbsent) as exc:
        commits(tmp_path)
    assert "git" in str(exc.value).lower()
