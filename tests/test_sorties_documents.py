"""Les exemples de sortie des documents sont-ils encore VRAIS ?

LE DEFAUT, et pourquoi aucun des neuf controles ne le voyait. Le README montrait
`jio artifacts --budget` avec « 11 fichier(s), ~5715 jetons » et des fichiers de contexte a
136/133/134 lignes. L'outil en disait 12, 6424, et 150/145/148. La porte annoncait pourtant
« 9 controles, VERDICT : COHERENT » : elle verifiait que la commande CITEE existe, que les
chiffres COMPTES sont justes, que les calculs de la prose tiennent — mais pas qu'un exemple de
sortie recopie est encore la sortie reelle. C'etait la seule classe d'affirmation du depot que
rien ne relisait, et c'est la plus fragile : elle est longue, datee, pleine de chiffres, et
personne ne relit une capture d'ecran.

Ce que ce fichier verifie, dans l'ordre ou le mecanisme peut casser :

  * il NE DETECTE PAS une sortie perimee (le cas du README, rejoue sur un document construit) ;
  * il DETECTE TROP : il accuse une mise en page, une couleur, un chemin absolu ou une duree.
    Ces trois-la changent sans rien dire, donc ils sont normalises AVANT comparaison — et le
    test le verifie, sans quoi le controle serait desactive a la premiere machine differente ;
  * il EXECUTE une commande d'un document hostile. La liste blanche est testee ligne par ligne,
    y compris les formes qui n'ont pas l'air d'une commande (`python -c`, `;`, `$(...)`,
    `--write`) : un document est un contenu hostile par defaut, et c'est ici que cela se prouve ;
  * il REPARE mal. La reparation ne doit jamais ecrire un bloc dont la commande echoue (cela
    presenterait une sortie d'erreur comme un resultat), et elle doit pouvoir etre annulee
    (sauvegarde `.avant-jio`).
"""

from __future__ import annotations

import json
from pathlib import Path

from jio.cli import main
from jio.verify.sorties import (
    blocs,
    commande_refusee,
    executer,
    liste,
    normaliser,
    reparer,
    verifier,
)

#: Un document minimal, sans dependance a ce depot : la commande `jio version` existe sur
#: n'importe quelle installation.
DOC_JUSTE = """# Essai

<!-- sortie: jio version -->
{sortie}
<!-- /sortie -->
"""


def _sortie_de(commande: str, racine: Path) -> tuple[int, tuple[str, ...]]:
    return executer(commande, racine)


def _document(racine: Path, corps: tuple[str, ...]) -> Path:
    """Ecrit un document avec un bloc `sortie-exacte` contenant exactement `corps`."""
    chemin = racine / "README.md"
    texte = ("# Essai\n\n<!-- sortie-exacte: jio version -->\n"
             + "\n".join(corps) + "\n<!-- /sortie-exacte -->\n")
    chemin.write_text(texte, encoding="utf-8")
    return chemin


def test_un_bloc_juste_est_verifie_sans_divergence(tmp_path: Path) -> None:
    """Le cas nominal : le document dit la meme chose que l'outil, donc il ne se passe rien."""
    _code, sortie = _sortie_de("jio version", tmp_path)
    chemin = _document(tmp_path, sortie)
    assert verifier(chemin.read_text(encoding="utf-8"), tmp_path) == []


def test_une_sortie_PERIMEE_est_detectee_et_situee(tmp_path: Path) -> None:
    """Le defaut du README, rejoue : un chiffre d'une autre epoque doit etre REFUTE.

    Et la divergence doit dire OU : un controle qui signale « un bloc est faux » sans nommer la
    ligne oblige a refaire le travail de l'outil.
    """
    _code, sortie = _sortie_de("jio version", tmp_path)
    _document(tmp_path, sortie)
    # On vieillit le document : un chiffre different de la realite.
    perime = (tmp_path / "README.md").read_text(encoding="utf-8").replace("jio", "jio")
    perime = perime.replace(sortie[0], "jio 0.0.0-perime", 1)
    (tmp_path / "README.md").write_text(perime, encoding="utf-8")
    divergences = verifier(perime, tmp_path)
    assert divergences, "une sortie perimee doit etre refutee"
    assert divergences[0].ligne > 0
    assert "0.0.0-perime" in divergences[0].attendu
    assert str(divergences[0]).count("l'outil rend") == 1


def test_un_extrait_est_accepte_et_ses_COUPURES_sont_declarees(tmp_path: Path) -> None:
    """Un README montre ce qui compte — mais il doit dire ce qu'il saute.

    Deux morceaux separes par `...` sont cherches dans l'ordre, apres la fin du precedent : un
    document qui remettrait les sections dans un autre ordre que la sortie reelle ne serait pas
    un extrait, ce serait une citation arrangee.

    La commande du test est `jio skills --seuil-balaye` et non `jio version` : le mecanisme ne se
    prouve pas sur une sortie d'une seule ligne, ou « premier » et « dernier » sont la meme
    ligne et ou aucun ordre ne peut etre mis a l'epreuve.
    """
    commande = "jio skills --seuil-balaye"
    _code, sortie = _sortie_de(commande, tmp_path)
    assert len(sortie) >= 4, "le test a besoin d'une sortie a plusieurs lignes"
    chemin = tmp_path / "README.md"
    texte = ("# Essai\n\n<!-- sortie: " + commande + " -->\n"
             + sortie[0] + "\n...\n" + sortie[-1] + "\n<!-- /sortie -->\n")
    chemin.write_text(texte, encoding="utf-8")
    assert verifier(chemin.read_text(encoding="utf-8"), tmp_path) == []

    # Meme contenu, ordre inverse : ce n'est plus un extrait, c'est une citation arrangee.
    chemin.write_text("# Essai\n\n<!-- sortie: " + commande + " -->\n"
                      + sortie[-1] + "\n...\n" + sortie[0] + "\n<!-- /sortie -->\n",
                      encoding="utf-8")
    assert verifier(chemin.read_text(encoding="utf-8"), tmp_path), (
        "un extrait a l'envers ne doit pas passer"
    )


def test_une_command_e_qui_ne_produit_PLUS_la_sortie_est_signalee(tmp_path: Path) -> None:
    """Un exemple qui montre une sortie que la commande ne produit plus est faux.

    Le cas typique : la commande a change de message. Le document, lui, n'a pas bouge.
    """
    chemin = tmp_path / "README.md"
    chemin.write_text("<!-- sortie: jio version -->\n  SORTIE D'UNE AUTRE EPOQUE\n"
                      "<!-- /sortie -->\n", encoding="utf-8")
    divergences = verifier(chemin.read_text(encoding="utf-8"), tmp_path)
    assert divergences
    assert "SORTIE D'UNE AUTRE EPOQUE" in divergences[0].attendu


# -- la securite : un document est un contenu HOSTILE ---------------------- #


def test_seul_jio_est_execute(tmp_path: Path) -> None:
    """Un controle qui executerait la commande ecrite dans un document serait un trou.

    Le test refuse les formes qui n'ont pas l'air d'une commande : `rm`, `python -c`, une
    deuxieme commande apres `;`, une substitution `$(...)`, et une option qui ecrit.
    """
    refus = [
        "rm -rf /",
        "python -c import os",
        "jio version; rm -rf /",
        "jio version && echo pris",
        "jio version > /tmp/x",
        "jio version `whoami`",
        "jio version $(whoami)",
        "jio artifacts --write",
        "jio chiffres --appliquer",
        "jio scan --fix",
        "jio pr --sortie /tmp/corps.md",
        "jio",
        "jio --help",
    ]
    for commande in refus:
        assert commande_refusee(commande), f"{commande!r} doit etre refuse"
    for acceptee in ("jio version", "jio skills --banc", 'jio skills "un objectif"'):
        assert commande_refusee(acceptee) is None, f"{acceptee!r} doit etre accepte"


def test_executer_REFUSE_aussi_les_memes_commandes(tmp_path: Path) -> None:
    """La liste blanche est dans `executer`, pas seulement dans une fonction de confort.

    Une garde qu'on peut oublier d'appeler n'est pas une garde : le refus doit etre dans le
    chemin d'execution lui-meme.
    """
    import pytest

    for commande in ("rm -rf /", "jio version; rm -rf /", "python -c pass"):
        with pytest.raises(ValueError):
            executer(commande, tmp_path)


def test_un_bloc_refuse_est_signale_sans_execution(tmp_path: Path) -> None:
    """Refuser silencieusement serait pire qu'executer : le document resterait cru."""
    chemin = tmp_path / "README.md"
    chemin.write_text("<!-- sortie: rm -rf / -->\n  tout va bien\n<!-- /sortie -->\n",
                      encoding="utf-8")
    divergences = verifier(chemin.read_text(encoding="utf-8"), tmp_path)
    assert divergences
    assert "REFUS" in divergences[0].motif


# -- la normalisation : ce qui change sans rien dire ------------------------ #


def test_la_normalisation_masque_COULEURS_CHEMINS_DUREES(tmp_path: Path) -> None:
    """Trois choses different d'une machine a l'autre sans qu'aucune ne soit une affirmation.

    Les masquer est ce qui rend le controle utilisable ailleurs qu'ici ; masquer davantage
    serait s'exempter soi-meme du controle.
    """
    brut = f"\x1b[32mok\x1b[0m en 1.7s depuis {tmp_path}/jio/x.py\n\n\n"
    lignes = normaliser(brut, tmp_path)
    assert lignes == ("ok en <duree> depuis <racine>/jio/x.py",)


def test_les_lignes_vides_de_BORD_ne_sont_pas_des_affirmations(tmp_path: Path) -> None:
    """La mise en page d'un bloc n'est pas son contenu : la comparer accuserait une forme."""
    _code, sortie = _sortie_de("jio version", tmp_path)
    chemin = tmp_path / "README.md"
    chemin.write_text("<!-- sortie-exacte: jio version -->\n\n\n" + "\n".join(sortie)
                      + "\n\n\n<!-- /sortie-exacte -->\n", encoding="utf-8")
    assert verifier(chemin.read_text(encoding="utf-8"), tmp_path) == []


# -- la reparation ---------------------------------------------------------- #


def test_la_reparation_reecrit_et_SAUVEGARDE(tmp_path: Path) -> None:
    """Reparer doit pouvoir etre annule : une ecriture sans retour arriere est un piege."""
    chemin = _document(tmp_path, ("  SORTIE D'UNE AUTRE EPOQUE",))
    code, signalements, message = reparer(chemin, tmp_path)
    assert code == 0, signalements
    assert "1 bloc(s) reecrit(s)" in message
    assert (tmp_path / "README.md.avant-jio").is_file()
    assert "SORTIE D'UNE AUTRE EPOQUE" in (tmp_path / "README.md.avant-jio").read_text()
    assert verifier(chemin.read_text(encoding="utf-8"), tmp_path) == []


def test_la_reparation_ne_reecrit_RIEN_quand_tout_est_juste(tmp_path: Path) -> None:
    """Le meme principe que la generation du corps de la PR : ce qui est deja juste n'est pas
    reecrit. Une reparation qui touche un fichier correct rend tout diff illisible."""
    _code, sortie = _sortie_de("jio version", tmp_path)
    chemin = _document(tmp_path, sortie)
    avant = chemin.read_text(encoding="utf-8")
    code, _signalements, message = reparer(chemin, tmp_path)
    assert code == 0
    assert "aucun bloc a reecrire" in message
    assert chemin.read_text(encoding="utf-8") == avant
    assert not (tmp_path / "README.md.avant-jio").exists(), "aucune sauvegarde sans ecriture"


def test_la_reparation_ne_reecrit_PAS_un_extrait(tmp_path: Path) -> None:
    """Un extrait perime est SIGNALE, pas reecrit : choisir les lignes a montrer demanderait de
    deviner l'intention de l'auteur, et ce depot ne devine pas."""
    chemin = tmp_path / "README.md"
    chemin.write_text("<!-- sortie: jio version -->\n  SORTIE D'UNE AUTRE EPOQUE\n"
                      "<!-- /sortie -->\n", encoding="utf-8")
    code, signalements, message = reparer(chemin, tmp_path)
    assert code == 1
    assert "aucun bloc a reecrire" in message
    assert any("SORTIE D'UNE AUTRE EPOQUE" in s for s in signalements)
    assert "SORTIE D'UNE AUTRE EPOQUE" in chemin.read_text(encoding="utf-8")


def test_une_commande_en_echec_n_est_JAMAIS_presentee_comme_un_resultat(tmp_path: Path) -> None:
    """Reecrire la sortie d'une commande qui echoue presenterait une erreur comme un resultat."""
    chemin = tmp_path / "README.md"
    chemin.write_text("<!-- sortie-exacte: jio sous-commande-inexistante -->\n  peu importe\n"
                      "<!-- /sortie-exacte -->\n", encoding="utf-8")
    _code, signalements, _message = reparer(chemin, tmp_path)
    assert signalements
    assert "peu importe" in chemin.read_text(encoding="utf-8"), "le bloc ne doit pas etre reecrit"


# -- l'interface et l'integration a la porte -------------------------------- #


def test_la_liste_dit_ce_que_le_document_promet(tmp_path: Path) -> None:
    """Verifier sans executer : de quoi relire un contrat avant de le signer."""
    _code, sortie = _sortie_de("jio version", tmp_path)
    chemin = _document(tmp_path, sortie)
    lignes = liste(chemin.read_text(encoding="utf-8"))
    assert len(lignes) == 1
    assert "EXACTE" in lignes[0] and "jio version" in lignes[0]


def test_aucun_bloc_declare_ne_veut_pas_dire_aucun_controle(tmp_path: Path) -> None:
    """La difference entre « rien a verifier » et « tout est verifie » est le coeur de ce depot."""
    (tmp_path / "README.md").write_text("# Rien\n\n```\njio version\n```\n", encoding="utf-8")
    assert blocs((tmp_path / "README.md").read_text(encoding="utf-8")) == []
    assert verifier((tmp_path / "README.md").read_text(encoding="utf-8"), tmp_path) == []


def test_la_commande_sorties_explique_le_balisage(tmp_path: Path, monkeypatch, capsys) -> None:
    """Sans bloc declare, la commande ENSEIGNE le contrat au lieu de rendre un faux vert."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("# Rien\n", encoding="utf-8")
    code = main(["sorties"])
    sortie = capsys.readouterr().out
    assert code == 0
    assert "aucun exemple declare" in sortie
    assert "sortie-exacte:" in sortie


def test_la_commande_sorties_est_lisible_par_une_machine(tmp_path: Path, monkeypatch, capsys) -> None:
    """L'appelant automatise a besoin du VERDICT et de la liste, pas d'un recit."""
    monkeypatch.chdir(tmp_path)
    _code, sortie = _sortie_de("jio version", tmp_path)
    _document(tmp_path, sortie)
    assert main(["sorties", "--json"]) == 0
    donnees = json.loads(capsys.readouterr().out)
    assert donnees["blocs"] == 1
    assert donnees["divergences"] == []


def test_la_porte_verifie_les_exemples_declares(tmp_path: Path) -> None:
    """L'integration qui compte : `jio coherence` doit compter les exemples verifies.

    Sans cela, la brique serait une commande de plus que personne ne lance — exactement ce que
    ce depot refuse d'accumuler.
    """
    from jio.verify.coherence import _controle_documents

    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_rien.py").write_text("def test_ok():\n    assert True\n",
                                                     encoding="utf-8")
    _code, sortie = _sortie_de("jio version", tmp_path)
    _document(tmp_path, sortie)
    constat = _controle_documents(tmp_path)
    assert "exemple(s) de sortie d'outil verifie(s)" in constat.resume
    assert constat.ok

    # Et si le document ment, la porte le dit — avec la ligne.
    (tmp_path / "README.md").write_text(
        "<!-- sortie-exacte: jio version -->\n  version inventee\n<!-- /sortie-exacte -->\n",
        encoding="utf-8")
    constat = _controle_documents(tmp_path)
    assert not constat.ok
    assert any("version inventee" in detail for detail in constat.details)
