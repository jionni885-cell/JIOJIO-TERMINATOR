"""`jio scan` doit etre lisible : deux mesures, deux corrections.

Ce fichier verrouille les deux defauts trouves en pointant `jio scan .` sur ce depot,
parce qu'ils sont de la meme famille — un balayage inutilisable :

  1. **il traversait l'environnement virtuel.** 1363 fichiers Python au lieu de 105,
     736 « problemes » sur du code tiers, 285 secondes au lieu de 14. Une liste de
     defauts qu'on ne peut pas lire est ignoree EN ENTIER, y compris ses vrais
     defauts : un faux positif n'est pas un desagrement, c'est la perte de l'outil ;
  2. **il accusait ses propres fixtures.** Les corpus de preuve
     (`evidence/**/fautifs/`, `evidence/claims/rapport_fautif.md`) sont faux A DESSEIN,
     et etaient signales comme 16 defauts du projet.

Ce qui est ignore est TOUJOURS dit, et un fichier du corpus se declare lui-meme.
Une exclusion silencieuse serait le silence que tout le projet refuse.
"""

from __future__ import annotations

import pathlib

from jio.cli import DOSSIERS_IGNORES, MARQUEUR_CORPUS, _corpus_volontaire, _est_ignore

REPO = pathlib.Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# 1. Dossiers ignores
# --------------------------------------------------------------------------- #


def test_les_dossiers_vendorises_sont_ignores() -> None:
    for dossier in (".venv", "venv", "node_modules", "__pycache__", ".git",
                    "site-packages", "build", "dist", ".nox", ".tox"):
        assert dossier in DOSSIERS_IGNORES, dossier


def test_un_dossier_ignore_est_reconnu_sous_la_racine(tmp_path: pathlib.Path) -> None:
    racine = tmp_path
    cible = racine / ".venv" / "lib" / "paquet" / "module.py"
    assert _est_ignore(cible, racine)

    normal = racine / "jio" / "cli.py"
    assert not _est_ignore(normal, racine)


def test_le_nom_du_dossier_racine_ne_compte_pas(tmp_path: pathlib.Path) -> None:
    """On peut auditer un paquet INSTALLE en le nommant : la comparaison est SOUS la racine.

    `jio scan /tmp/x/site-packages` doit balayer ce dossier, pas le considerer comme
    ignore : c'est ce que fait l'etape tierce de `scripts/evidence.sh`, et la refuser
    rendrait cette preuve impossible.
    """
    racine = tmp_path / "site-packages"
    racine.mkdir()
    cible = racine / "paquet" / "module.py"
    assert not _est_ignore(cible, racine)


def test_un_chemin_hors_racine_nest_jamais_ignore(tmp_path: pathlib.Path) -> None:
    assert not _est_ignore(pathlib.Path("/autre/endroit/x.py"), tmp_path)


# --------------------------------------------------------------------------- #
# 2. Corpus de fautes volontaires
# --------------------------------------------------------------------------- #


def test_un_fichier_se_declare_corpus_fautif() -> None:
    assert _corpus_volontaire(f"# {MARQUEUR_CORPUS} : faux a dessein\nx = 1\n")
    assert _corpus_volontaire(f"<!-- {MARQUEUR_CORPUS} -->\n# Titre\n")


def test_une_mention_tardive_ne_suffit_pas() -> None:
    """Le marqueur doit etre en TETE : sinon un fichier le citerait par accident.

    Les premiers fichiers de ce depot qui parlent du marqueur sont ce test et le
    module qui l'implemente — un fichier ne doit pas devenir « fautif a dessein »
    parce qu'il en discute a la ligne 40.
    """
    texte = "\n".join(["x = 1"] * 10 + [f"# {MARQUEUR_CORPUS}"])
    assert not _corpus_volontaire(texte)


def test_le_corpus_du_depot_est_declare() -> None:
    """Les fixtures fautives de ce depot doivent TOUTES se declarer.

    Une seule qui l'oublie suffit a rendre `jio scan .` bruyant — et c'est mesure :
    c'est exactement ce qui se passait avant.
    """
    fautifs = sorted(REPO.glob("evidence/**/fautifs/*.py"))
    # `evidence/selfspec/` MELANGE les regimes : 4 artefacts fautifs (les KO mesures
    # par `scripts/evidence.sh`), 1 qui produit une reserve, 4 corrects. Seuls les KO
    # sont declares — marquer tout le dossier rendrait le corpus inutilisable comme
    # contre-epreuve.
    fautifs += [
        REPO / "evidence" / "selfspec" / nom
        for nom in ("arrondit_en_douce.py", "classe_lifo_trompeuse.py",
                    "classe_menteuse_masquee.py", "ment_sur_la_division.py")
    ]
    fautifs.append(REPO / "evidence" / "claims" / "rapport_fautif.md")
    assert len(fautifs) > 5, "le corpus doit exister pour que ce test ait un sens"

    non_declares = [
        f.relative_to(REPO).as_posix() for f in fautifs
        if not _corpus_volontaire(f.read_text(encoding="utf-8"))
    ]
    assert not non_declares, f"fixtures fautives non declarees : {non_declares}"


def test_le_corpus_sain_ne_se_declare_pas() -> None:
    """L'inverse compte autant : un fichier sain ne doit pas se dire fautif."""
    for chemin in sorted(REPO.glob("evidence/**/sains/*.py")) + [
        REPO / "evidence" / "claims" / "rapport_sain.md"
    ]:
        texte = chemin.read_text(encoding="utf-8")
        assert not _corpus_volontaire(texte), chemin
