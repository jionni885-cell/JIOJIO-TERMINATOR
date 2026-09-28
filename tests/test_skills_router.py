"""Le routeur de competences : choisir, expliquer, et savoir dire NON.

POURQUOI CE FICHIER EXISTE. Le depot livre douze competences Hermes et une fiche de contexte qui
les enumere. Enumerees, elles ne servent pas : la litterature du domaine mesure qu'un agent
survole un contexte trop long, et que la recuperation CIBLEE bat le resume — 0,14 de precision en
tete contre 0,48 quand on remplace le resume par une interrogation. La bibliotheque ne vaut donc
que par la question qu'on lui pose : « pour CET objectif, lesquelles, et pourquoi ? ».

Les tests ci-dessous ne verifient pas « le routeur est bon » — c'est le banc qui le mesure, et il
tient en 39 objectifs ecrits par la personne qui a ecrit le routeur. Ils verifient trois choses,
qui sont les trois facons dont un tel mecanisme se casse :

  * il NE CLASSE PAS : le premier choix n'est pas le bon sur des cas de reference, y compris
    ecrits dans l'autre langue que l'index ;
  * il NE SAIT PAS DIRE NON : un objectif de plomberie (« traduire ce document ») lui fait
    charger une procedure qui ne s'applique pas — l'erreur la plus couteuse, parce qu'elle
    detourne le travail en plus de l'occuper ;
  * il N'EXPLIQUE PAS : un choix sans raison ne peut pas etre verifie, donc il n'est pas
    corrigeable — et un mecanisme non corrigeable se degrade sans que personne ne le voie.

Deux tests tiennent en outre des DECISIONS mesurees du module, celles qu'un refactoring
bien intentionne defairait : le corps des competences n'est PAS indexe (ses exemples citent le
vocabulaire du depot et coutaient 29 points de premier choix juste), et le seuil d'abstention
declare est bien celui que le balayage du banc retient (sinon la constante et la mesure divergent
en silence).
"""

from __future__ import annotations

import json

import pytest

from jio.cli import main
from jio.skills import (
    BANC,
    SEUIL_CONCEPTS,
    Catalogue,
    balayer_seuils,
    catalogue_du_depot,
    choisir,
    comparer,
    cout,
    mesurer,
)
from jio.skills.lexique import CLASSES, PONT, concept
from jio.skills.router import LAMBDA, Document, jetons, stem

#: Un objectif du banc, ecrit comme un utilisateur l'ecrirait. Il contient `sum_even`, qui est du
#: vocabulaire de DEPOT : c'est precisement le piege qui avait fait gagner `structured-failure`
#: quand les corps etaient indexes.
OBJECTIF_TEST = "Ajouter un test qui echoue quand sum_even compte les nombres impairs"

#: Des objectifs hors sujet, pris dans le banc : plomberie, redaction, traduction, menus.
HORS_SUJET = [o.texte for o in BANC if not o.positif]


def test_le_routeur_classe_le_bon_premier_choix() -> None:
    """Le premier choix est celui que l'agent lira en premier : c'est la metrique qui compte."""
    choix = choisir(OBJECTIF_TEST)
    assert choix, "aucune competence chargee pour un objectif de reference"
    assert choix[0].nom == "executable-proof"


def test_le_routeur_comprend_les_deux_langues() -> None:
    """L'index est en francais, l'utilisateur ecrit dans les deux langues.

    Ce cas mesure le pont : sans lui, « The same failure keeps coming back » ne partageait AUCUN
    mot avec la competence de memoire des echecs. Le routeur n'avait pas tort, il ne comprenait
    pas la question.
    """
    anglais = choisir("The same failure keeps coming back after two fixes")
    francais = choisir("Le meme bug revient trois fois de suite apres corrections")
    assert anglais and anglais[0].nom == "failure-memory"
    assert francais and francais[0].nom == "failure-memory"


def test_un_objectif_hors_sujet_ne_charge_RIEN() -> None:
    """Charger une procedure qui ne s'applique pas coute plus cher que ne rien charger.

    Le test porte sur les huit cas hors sujet du banc, pas sur un exemple choisi : un routeur qui
    repond toujours n'est pas un routeur, c'est un menu.
    """
    declenches = [texte for texte in HORS_SUJET if choisir(texte)]
    assert not declenches, f"procedure chargee pour du hors sujet : {declenches}"


def test_le_seuil_peut_etre_force() -> None:
    """L'abstention doit etre CONTOURNABLE : un refus definitif est une impasse pour l'utilisateur.

    Le seuil a 0 charge une competence pour un objectif hors sujet, ce qui est exactement ce que
    demande l'utilisateur qui veut voir le moins mauvais candidat — et ce que le seuil par defaut
    refuse de faire a sa place.
    """
    assert choisir("Traduire ce document en espagnol") == []
    choisi = choisir("Traduire ce document en espagnol", seuil=0)
    assert len(choisi) >= 1
    assert all(c.raisons for c in choisi), "un choix force doit tout de meme dire POURQUOI"


def test_chaque_choix_dit_pourquoi() -> None:
    """Un classement sans raison affichee ne peut pas etre verifie — donc pas corrige.

    Et le cout est porte par le choix lui-meme : c'est ce que la reponse coutera reellement au
    contexte de l'agent, face aux 6424 jetons des douze corps.
    """
    choix = choisir("Reduire de 80 % les jetons envoyes au modele")
    assert choix
    for c in choix:
        assert c.raisons, f"{c.nom} est retenu sans aucun terme en commun"
        assert c.cout_jetons > 0
    total = sum(d.cout_jetons for d in catalogue_du_depot().documents)
    assert cout(choix) < total


def test_le_classement_est_DETERMINISTE() -> None:
    """Deux fois la meme question, deux fois la meme reponse — sans quoi rien n'est reproductible.

    Les egalites de score sont tranchees par le nom, et les dictionnaires internes sont parcourus
    dans un ordre trie : un classement qui dependrait de l'ordre d'insertion d'un dictionnaire
    dependrait de la session, et un incident ne pourrait plus etre rejoue.
    """
    for texte in (OBJECTIF_TEST, "The two reviewers always agree", "cache invalide apres commit"):
        premier = [(c.nom, c.score) for c in choisir(texte)]
        second = [(c.nom, c.score) for c in choisir(texte)]
        assert premier == second


def test_le_corps_des_competences_n_est_PAS_indexe() -> None:
    """Decision mesuree, gardee par un test : le tiers 0 est ce qui sert a CHOISIR.

    Indexer le corps entier faisait gagner `structured-failure` sur l'objectif de reference, parce
    que son exemple de sortie cite litteralement `sum_even` — du vocabulaire de DEPOT, pas le
    sujet de la competence. L'ecart mesure valait 29 points de premier choix juste.

    Le controle est STRUCTUREL : un document indexable n'a pas de champ de corps. Si quelqu'un en
    ajoute un, ce test tombe avant que la mesure ne baisse.
    """
    champs = set(Document.__dataclass_fields__)
    assert not champs & {"body", "corps", "contenu", "texte"}, (
        "le corps d'une competence ne doit pas entrer dans l'index"
    )
    doc = Document(nom="x", categorie="c", description="d", tags=("t",))
    assert "x" in doc.indexable and "d" in doc.indexable


def test_les_documents_sont_priorises_par_nom_et_tags() -> None:
    """Le nom et les tags pesent plus que la description : ce sont les champs discriminants.

    Sur les douze competences, `hostile-content`, `abstention` et `decorrelation` disent le sujet
    mieux qu'une phrase de description. La ponderation retenue (3, 3) est celle du balayage ; le
    voisinage donne le meme resultat, donc ce n'est pas un equilibre sur le fil.
    """
    doc = Document(nom="alpha", categorie="gamma", description="delta", tags=("beta",))
    assert doc.indexable.count("alpha") == 3
    assert doc.indexable.count("beta") == 3
    assert doc.indexable.count("delta") == 1
    assert doc.indexable.count("gamma") == 1


def test_un_catalogue_vide_ne_leve_pas() -> None:
    """Un cas limite qui doit rendre une reponse, pas une exception."""
    vide = Catalogue.depuis([])
    assert vide.interroger("n'importe quoi") == []
    assert Catalogue.depuis([Document("a", "c", "d", ())]).interroger("") == []


# -- le banc, qui juge le routeur ------------------------------------------- #


def test_le_routeur_bat_ses_temoins() -> None:
    """Sans ecart aux temoins, le routeur serait du decor a retirer plutot qu'a defendre.

    `alphabetique` chiffre ce que vaut un choix qui ne regarde pas l'objectif ; `mots-cles bruts`
    ce que BM25, sa saturation et sa normalisation de longueur apportent. Le deuxieme temoin est
    le vrai juge : c'est l'ablation.
    """
    resultats = {nom: equilibre for nom, _, equilibre in comparer()}
    routeur = resultats["routeur (BM25 + MMR)"]
    for temoin, equilibre in resultats.items():
        if temoin != "routeur (BM25 + MMR)":
            assert routeur > equilibre, f"le routeur ne bat pas {temoin}"
    # `tout charger` a un rappel parfait par construction : s'il gagne, c'est que le routeur ne
    # sert a rien. Il ne doit pas gagner.
    assert resultats["tout charger"] < 0.9


def test_le_seuil_declare_est_celui_du_banc() -> None:
    """La constante du module et la mesure doivent dire la MEME chose, ou l'une des deux ment.

    Un seuil ecrit a la main qui derive du balayage est un seuil qu'on ne peut plus defendre : on
    affirmerait une valeur que la mesure ne soutient plus.
    """
    balayage = balayer_seuils()
    meilleur, equilibre, abstentions, _ = max(balayage, key=lambda ligne: (ligne[1], ligne[0]))
    assert meilleur == SEUIL_CONCEPTS
    assert abstentions == len([o for o in BANC if not o.positif]), (
        "le seuil retenu doit s'abstenir sur TOUS les cas hors sujet"
    )
    assert equilibre >= 0.9


def test_le_rappel_coute_et_le_cout_est_DIT() -> None:
    """Le banc publie aussi ce que le routeur rate : un rapport qui ne montre que ses succes ment.

    Le seuil d'abstention fait perdre des objectifs pertinents. Ces cas sont listes dans
    `Rapport.erreurs` et non caches : c'est le prix de l'abstention, et il doit etre lisible.
    """
    rapport = mesurer()
    manquees = [l for l in rapport.erreurs if "MANQUEE" in l]
    assert manquees, "un banc ou le routeur ne rate rien ne mesure probablement rien"
    assert all("obtenu" in ligne for ligne in manquees)
    assert rapport.precision1_servis >= rapport.precision1, (
        "la precision conditionnelle ne peut pas etre pire que la precision totale"
    )


# -- le lexique et ses bornes ----------------------------------------------- #


def test_un_concept_a_une_seule_identite_par_RADICAL() -> None:
    """Defaut mesure et corrige : « outil » et « outils » comptaient DEUX concepts.

    Deux objectifs de plomberie passaient ainsi le seuil d'evidence et faisaient charger une
    competence hors sujet. L'identite d'un concept est son radical, jamais sa forme ecrite.
    """
    assert concept("outil") == concept("outils")
    assert concept("convert") == concept("convertir")
    assert concept("test") == concept("tests")
    assert concept("preuve") != concept("semaine")


def test_le_lexique_ne_contient_pas_de_PHRASE() -> None:
    """Un lexique qui contiendrait une question entiere serait un tour de passe-passe sur le banc.

    Le pont doit rester du vocabulaire de domaine : quelques mots par classe, jamais une entree
    qui ressemble a un objectif. C'est ce qui distingue une table d'equivalences d'un entrainement
    deguise.
    """
    for classe in CLASSES:
        for mot in classe:
            assert " " not in mot, f"« {mot} » est une expression, pas un mot de domaine"
            assert len(mot) <= 20, f"« {mot} » est trop long pour un mot de domaine"
    assert len(PONT) >= 100, "un pont trop maigre ne relierait rien"
    assert len(CLASSES) >= 10


def test_le_stemmer_ne_mange_pas_les_mots_courts() -> None:
    """Un radical trop agressif rapproche des mots sans rapport et rend le choix inexpliquable.

    La borne est la meme que celle de la porte de clarification : on ne retire un suffixe que
    s'il reste au moins quatre caracteres.
    """
    assert stem("test") == "test"
    assert stem("tests") == "test"
    assert stem("tester") == "test"
    assert stem("idee") == "idee"
    assert stem("outils") == "outil"


def test_les_jetons_perdent_accents_et_mots_outils() -> None:
    """« securite » et « sécurité » doivent se rencontrer : ce depot s'ecrit sans accents."""
    assert jetons("Sécurité du contexte") == ["securite", "contexte"]
    assert "le" not in jetons("le test de la preuve")
    assert "exploit" in jetons("Exploit!")


def test_la_diversification_est_bornee() -> None:
    """`lambda` reste dans (0, 1] : a 0, le classement ignorerait la pertinence ; a 1, il
    chargerait trois fois la meme competence."""
    assert 0.0 < LAMBDA <= 1.0
    choix = choisir("Un test executable prouve le resultat", maximum=3)
    noms = [c.nom for c in choix]
    assert len(noms) == len(set(noms))


# -- la porte publique : `jio skills` --------------------------------------- #


def _lancer(arguments: list[str], capsys) -> tuple[int, str]:
    code = main(arguments)
    return code, capsys.readouterr().out


def test_la_commande_skills_repond(capsys) -> None:
    """Une commande qui n'explique pas son usage n'existe pas pour celui qui la decouvre."""
    code, sortie = _lancer(["skills"], capsys)
    assert code == 0
    assert "usage" in sortie
    assert "competences disponibles" in sortie


def test_la_commande_skills_classe_et_explique(capsys) -> None:
    code, sortie = _lancer(["skills", OBJECTIF_TEST], capsys)
    assert code == 0
    assert "executable-proof" in sortie
    assert "pourquoi" in sortie
    assert "cout d'injection" in sortie


def test_la_commande_skills_est_lisible_par_une_machine(capsys) -> None:
    """L'appelant automatise est un cas d'usage reel : le routeur doit servir un agent, pas
    seulement un humain devant un terminal."""
    code, sortie = _lancer(["skills", OBJECTIF_TEST, "--json"], capsys)
    assert code == 0
    donnees = json.loads(sortie)
    assert donnees["choix"][0]["nom"] == "executable-proof"
    assert donnees["choix"][0]["raisons"]
    # L'abstention doit etre un resultat lisible, pas une absence de reponse.
    code, sortie = _lancer(["skills", "Traduire ce document en espagnol", "--json"], capsys)
    assert code == 0
    assert json.loads(sortie)["choix"] == []


def test_la_commande_skills_publie_ses_mesures(capsys) -> None:
    """Le banc et le seuil s'affichent a la demande : le routeur ne demande pas d'etre cru."""
    code, sortie = _lancer(["skills", "--banc"], capsys)
    assert code == 0
    assert "routeur (BM25 + MMR)" in sortie
    assert "mots-cles bruts" in sortie
    assert "alphabetique" in sortie
    assert "LIMITE de l'affirmation" in sortie

    code, sortie = _lancer(["skills", "--seuil-balaye"], capsys)
    assert code == 0
    assert "<- retenu" in sortie
    assert str(SEUIL_CONCEPTS) in sortie


@pytest.mark.parametrize("objectif", [o.texte for o in BANC if o.positif][:12])
def test_aucun_objectif_du_banc_ne_fait_planter_le_routeur(objectif: str) -> None:
    """Un routeur qui leve une exception en pleine mission coute plus cher qu'un routeur muet."""
    choix = choisir(objectif)
    assert isinstance(choix, list)
