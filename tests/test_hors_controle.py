"""Les zones declarees hors controle : une exemption, oui — une exemption muette, jamais.

Un document doit pouvoir raconter ses erreurs. Ce depot le fait partout (« il a annonce 187
tests verts quand la suite en comptait 520 », « l'artefact citait une commande qui n'existe
pas »). Sans exemption, deux consequences egalement mauvaises : le controle REPARE le recit
(il ecrit la valeur vraie du jour a la place du chiffre historique, et le document devient faux
par correction automatique), ou bien l'auteur supprime le recit et le depot perd la memoire de
ses defauts.

L'exemption est donc necessaire. Ce fichier tient les trois regles qui l'empechent de devenir
une porte de sortie :

  1. la zone est DECLAREE dans le document (jamais devinee par un controle) ;
  2. elle porte une RAISON ecrite, et une zone sans raison est refusee ;
  3. elle reste VISIBLE : le rapport d'ensemble la compte, la nomme et dit pourquoi.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jio.verify.hors_controle import (
    masquer,
    raisons,
    raisons_manquantes,
    zones,
)

RACINE = Path(__file__).resolve().parents[1]


def test_les_trois_formes_de_marqueurs_sont_reconnues() -> None:
    """Generique, `chiffres:` (historique), `prose:` : les trois ferment la meme zone.

    Le prefixe de domaine dit a QUEL controle l'auteur pensait ; il ne restreint pas
    l'exemption. Un marqueur qui n'exempterait que d'un controle obligerait a recopier le meme
    bloc trois fois — et le troisieme serait oublie.
    """
    texte = (
        "<!-- hors-controle: recit -->\ncontenu\n<!-- /hors-controle -->\n"
        "<!-- chiffres:hors-controle: chiffres historiques -->\ncontenu\n<!-- /chiffres:hors-controle -->\n"
        "<!-- prose:hors-controle: exemple de sortie -->\ncontenu\n<!-- /prose:hors-controle -->\n"
    )
    lignes, declarees = zones(texte)
    assert lignes == {1, 2, 3, 4, 5, 6, 7, 8, 9}
    assert declarees == ["recit", "chiffres historiques", "exemple de sortie"]


def test_une_exemption_sans_raison_est_signalee() -> None:
    """« Hors controle » tout court n'exempte rien : il faut dire POURQUOI.

    Une exemption sans raison est presque toujours une exemption qu'on ne saura plus justifier
    six mois plus tard — et a ce moment-la, personne n'osera la retirer.
    """
    texte = (
        "<!-- hors-controle -->\ncontenu\n<!-- /hors-controle -->\n"
        "<!-- hors-controle:   -->\nencore\n<!-- /hors-controle -->\n"
        "<!-- hors-controle: raison valable -->\nla\n<!-- /hors-controle -->\n"
    )
    assert raisons_manquantes(texte) == [1, 4]
    assert raisons(texte) == ["", "", "raison valable"]


def test_le_masquage_preserve_les_LONGUEURS_et_les_numeros_de_ligne() -> None:
    """Masquer, jamais supprimer : les positions des autres affirmations restent exactes.

    C'est le point technique qui compte. Un controle qui RETIRE des lignes decale toutes les
    positions suivantes, donc chaque message suivant pointe la mauvaise ligne — pire qu'un
    controle absent, parce qu'il envoie l'utilisateur au mauvais endroit.
    """
    texte = "avant\n<!-- hors-controle: recit -->\nzone\nexemptee\n<!-- /hors-controle -->\napres\n"
    masque = masquer(texte)
    assert len(masque) == len(texte)
    assert masque.count("\n") == texte.count("\n")
    assert masque.splitlines()[0] == "avant"
    assert masque.splitlines()[5] == "apres"
    assert all(not ligne.strip() for ligne in masque.splitlines()[1:5])


def test_un_controle_voit_la_zone_et_ne_la_condamne_pas(tmp_path: Path) -> None:
    """Le recit d'une erreur passe, la commande inventee hors zone echoue — et la zone est dite.

    Les deux moities de la regle dans un seul test, parce que c'est leur combinaison qui fait
    la valeur du mecanisme : exempter ne sert a rien si l'exemption est invisible.
    """
    from jio.verify.coherence import controler

    (tmp_path / "README.md").write_text(
        "<!-- hors-controle: recit d'une erreur passee -->\n"
        "Autrefois ce fichier citait `jio verify`, qui n'existait pas.\n"
        "<!-- /hors-controle -->\n"
        "Aujourd'hui on lance `jio run` et `jio coherence`.\n"
        "`jio bidule-invente` reste une erreur.\n",
        encoding="utf-8",
    )
    constat = next(c for c in controler(tmp_path).constats if c.controle == "commandes")
    assert not constat.ok
    assert any("bidule-invente" in d for d in constat.details)
    assert not any("jio verify" in d for d in constat.details)
    assert "1 zone(s) declaree(s) hors controle" in constat.resume
    assert any("recit d'une erreur passee" in d for d in constat.details)


def test_une_zone_sans_raison_FAIT_ECHOUER_le_portail(tmp_path: Path) -> None:
    """Une exemption muette est un echec, pas un silence : la porte se ferme.

    Sans cette regle, la sortie de secours deviendrait le chemin principal : il suffirait
    d'ecrire un marqueur pour ne plus etre controle, et le portail se viderait de son sens.
    """
    from jio.verify.coherence import controler

    (tmp_path / "README.md").write_text(
        "<!-- hors-controle -->\n"
        "`jio bidule-invente` ici ne compte pas.\n"
        "<!-- /hors-controle -->\n",
        encoding="utf-8",
    )
    constat = next(c for c in controler(tmp_path).constats if c.controle == "commandes")
    assert not constat.ok
    assert "SANS RAISON" in constat.resume
    assert any("ligne 1" in d for d in constat.details), constat.details


def test_la_prose_respecte_la_meme_regle_que_les_chiffres() -> None:
    """Un calcul faux dans une zone exemptee n'est plus bloque ; hors zone, il l'est encore.

    Ce test traverse les deux modules (`hors_controle` et `claims`) parce que c'est la que la
    premiere version s'etait trompee : le masquage etait pose dans l'enveloppe `extraction`
    alors que `verifier` passe par la fonction de base. Le recit restait bloquant, et le
    portail l'a montre sur le README de ce depot.
    """
    from jio.verify.claims import verifier

    hors_zone = "<!-- hors-controle: recit -->\nLe total valait 2 + 2 = 5 autrefois.\n<!-- /hors-controle -->\n"
    dans_la_zone = "Le total vaut 2 + 2 = 5.\n"

    assert not verifier(hors_zone).bloquantes, "un recit ne doit pas bloquer"
    assert verifier(dans_la_zone).bloquantes, "un calcul faux bien vivant doit bloquer"


@pytest.mark.parametrize("marqueur", ["hors-controle", "chiffres:hors-controle", "prose:hors-controle"])
def test_le_marqueur_est_reconnu_meme_colle_au_texte(marqueur: str) -> None:
    """Le marqueur fonctionne seul sur sa ligne, sans exiger de mise en forme particuliere."""
    texte = f"<!-- {marqueur}: raison -->\nx\n<!-- /hors-controle -->\n"
    assert zones(texte)[1] == ["raison"]


def test_le_README_du_depot_declare_ses_exemptions_AVEC_raison() -> None:
    """Le depot applique sa propre regle : aucune exemption muette dans ses documents.

    Une regle qu'on n'applique pas a soi-meme n'est pas une regle, c'est un discours.
    """
    texte = (RACINE / "README.md").read_text(encoding="utf-8")
    assert raisons_manquantes(texte) == []
    declarees = raisons(texte)
    assert len(declarees) >= 3
    assert all(len(raison) > 10 for raison in declarees), declarees
