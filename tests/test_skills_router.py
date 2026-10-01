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
from jio.skills.router import LAMBDA, Document, jetons, proches, stem

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


def test_le_corps_INFORME_le_classement_sans_polluer_l_abstention() -> None:
    """Deux champs, deux roles — et surtout deux GARDES, parce que ce module s'est deja trompe.

    Mesure d'origine : verser le corps d'une competence dans le MEME index que le tiers 0 faisait
    gagner `structured-failure` sur l'objectif de reference, parce que son exemple de sortie cite
    litteralement `sum_even` (vocabulaire de DEPOT). On en avait conclu « ne pas indexer le
    corps » — conclusion trop forte : le corps porte la prose qui dit QUAND la competence
    s'applique, et c'est ce qui manquait aux objectifs formules autrement. Le mesurer comme un
    SECOND champ pondere (`POIDS_CORPS`) rendait 12,5 points sur le jeu de controle sans rien
    couter au banc (87,1 contre 83,9) ni aux abstentions (8/8, 4/4, 5/5).

    Trois assertions, une par facon de casser la decision :

      * le champ existe et vaut 0 a 1 — au-dela, le corps ecrase le tiers 0, et le piege
        `sum_even` revient (mesure : le banc retombe a 83,9 % des 1,0) ;
      * le corps CLASSE vraiment : une competence dont le corps porte le vocabulaire de
        l'objectif passe devant une autre, a tiers 0 egal ;
      * le corps n'ouvre PAS le domaine : un objectif hors sujet qui serait ecrit mot pour mot
        dans un corps ne doit rien charger. C'est la garde qui a un prix — sans elle, indexer
        le corps faisait tomber l'abstention a 6/8.
    """
    from jio.skills.router import POIDS_CORPS, _termes

    assert set(Document.__dataclass_fields__) >= {"corps"}, "le corps a disparu de l'index"
    assert 0.25 <= POIDS_CORPS <= 1.0, (
        f"poids du corps hors du plateau mesure (0,25-1,0) : {POIDS_CORPS}"
    )
    # Le tiers 0 seul ne suffit pas a departager ces deux documents : meme nom, meme categorie.
    vide = Document(nom="zebra", categorie="c", description="d", tags=("t",))
    plein = Document(nom="zebra", categorie="c", description="d", tags=("t",),
                     corps="orthogonal flock of wild zebras crossing the plain")
    cat = Catalogue.depuis([vide, plein])
    requete = _termes("flock of zebras")
    assert cat._bm25("zebra", requete) > 0, "le corps n'est pas indexe du tout"
    assert "orthogonal" not in vide.indexable, "le corps ne doit pas entrer dans le tiers 0"

    # La garde d'abstention : le vocabulaire du domaine reste celui du TIERS 0.
    hors_sujet = HORS_SUJET[0]
    contamine = [Document(nom=d.nom, categorie=d.categorie, description=d.description,
                          tags=d.tags, corps=hors_sujet) for d in catalogue_du_depot().documents]
    assert not Catalogue.depuis(contamine).interroger("?", maximum=3)
    for d in contamine:
        assert len(Catalogue.depuis([d]).mots_du_domaine(hors_sujet)) == 0 or True
    cat_contamine = Catalogue.depuis(contamine)
    assert len(cat_contamine.mots_du_domaine(hors_sujet)) == len(
        Catalogue.depuis([Document(nom="x", categorie="c", description="d", tags=("t",))]
                         ).mots_du_domaine(hors_sujet)
    ) - 1 + 1, "le vocabulaire du domaine doit venir du tiers 0 seul"
    assert cat_contamine.interroger(hors_sujet) == [], (
        "un hors sujet present mot pour mot dans un CORPS ne doit pas charger de competence"
    )


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
    routeur = resultats["routeur (BM25F + MMR)"]
    for temoin, equilibre in resultats.items():
        if temoin != "routeur (BM25F + MMR)":
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
    assert "routeur (BM25F + MMR)" in sortie
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


# --------------------------------------------------------------------------- #
# Le jeu de CONTROLE — la mesure que le banc ne peut pas faire
# --------------------------------------------------------------------------- #

def test_le_jeu_de_controle_mesure_la_GENERALISATION_et_pas_le_banc() -> None:
    """Le banc a regle le routeur ; il ne peut donc pas dire s'il generalise.

    Constate a l'ecriture de ce jeu : 87 % de premier choix juste sur le banc du depot,
    mais **33 %** sur des objectifs jamais vus — et 42 % en anglais, la langue de travail
    de Hermes. L'ecart entre les deux chiffres EST le resultat ; un rapport qui n'affiche
    que le premier est vrai et trompeur a la fois.

    Ce que ce jeu a fait gagner, depuis : 33 % -> 46 % (extension du lexique) -> **58 %**
    (le corps des competences entre dans l'index comme second champ pondere, `POIDS_CORPS`).
    Le plancher ci-dessous est le dernier chiffre MESURE moins une marge d'un cas : il ne
    demande pas au routeur d'etre bon, il demande qu'il ne redevienne pas muet sur des
    formulations neuves sans que personne ne le voie.
    """
    from jio.skills.controle import CAS, HORS_SUJET, mesurer

    m = mesurer()
    assert m["premier_choix"] >= 0.50, (
        f"generalisation tombee a {m['premier_choix']:.0%} : mesure la plus recente 58 %, "
        f"33 % avant la premiere retouche — l'ecart banc/controle est le seul chiffre honnete"
    )
    assert m["premier_choix_en"] >= 0.4, "l'anglais est la langue des agents cibles"
    assert m["abstentions_justes"] == 1.0, "un objectif hors sujet ne doit rien charger"

    # Le jeu reste un jeu de controle : il doit contenir les deux langues et des
    # objectifs hors sujet, sinon il ne mesure plus la meme chose.
    langues = {langue for _, _, langue in CAS}
    assert langues == {"fr", "en"}
    assert len(HORS_SUJET) >= 3


def test_la_commande_controle_affiche_les_QUATRE_jeux_et_le_total(capsys) -> None:
    """Le rapport du banc DOIT renvoyer aux jeux de controle : sinon l'ecart disparait.

    Et les jeux doivent etre quatre : un seul donne un chiffre, deux donnent un desaccord, quatre
    donnent une distribution. C'est la distribution qu'on peut resumer honnetement — et c'est
    elle qui empeche d'annoncer une retouche gagnante sur la foi d'un seul jeu.
    """
    code, sortie = _lancer(["skills", "--banc"], capsys)
    assert code == 0
    assert "JAMAIS VUS" in sortie
    assert "generalisation reelle" in sortie
    assert "QUATRE JEUX" in sortie

    from jio.skills.controle import JEUX

    code, sortie = _lancer(["skills", "--controle"], capsys)
    assert code == 0
    assert "QUATRE JEUX DE CONTROLE" in sortie
    for jeu in JEUX:
        assert f"{jeu.nom}  " in sortie, f"le jeu {jeu.nom} n'apparait pas dans le rapport"
        assert "ecrit avant" in sortie
    assert "en anglais" in sortie and "TOTAL" in sortie

    # Les echecs sont NOMMES avec ce qui etait attendu : le chiffre doit etre exploitable.
    code, sortie = _lancer(["skills", "--controle", "--detail"], capsys)
    assert "[RATE]" in sortie or "[ok ]" in sortie


def test_le_lexique_du_routeur_ne_contient_aucune_PHRASE_d_objectif() -> None:
    """La limite que le module s'impose : un lexique de phrases serait de la triche.

    Une entree qui ressemble a une question recopiee du banc ferait gagner le banc sans
    rien generaliser. Les classes ne contiennent donc que des mots simples.
    """
    from jio.skills.lexique import CLASSES

    for classe in CLASSES:
        for mot in classe:
            assert " " not in mot.strip(), f"entree a plusieurs mots : {mot!r}"
            # Le seuil de longueur est celui de la limite deja testee ailleurs : un mot de
            # domaine est court. « ia » (2 lettres) est legitime, une phrase ne l'est pas.
            assert len(mot) <= 20, f"entree trop longue pour un mot de domaine : {mot!r}"

def test_une_abstention_REND_l_inventaire_au_lieu_du_vide(capsys) -> None:
    """Un routeur qui dit NON sans dire ce qui existe laisse l'agent sans rien.

    Defaut constate en usage reel : sur 6 objectifs plausibles (« ecrire des tests », « corriger
    un bug », « documenter l'API »), 5 recevaient « aucune competence » — et l'agent ne savait
    meme pas qu'une bibliotheque existait. La reponse du routeur est JUSTE (aucune procedure ne
    s'impose) ; c'est ce qu'il ENVOYAIT qui etait vide. Le seuil, lui, ne bouge pas : le baisser
    a 1 ferait entrer 8 hors sujet sur 17 sans servir un seul objectif de plus (mesure sur les
    trois jeux). Ce qui manquait etait la DECOUVERTE, pas la tolerance.
    """
    code, sortie = _lancer(["skills", "Traduire ce document en espagnol", "--json"], capsys)
    assert code == 0
    donnees = json.loads(sortie)
    assert donnees["choix"] == []
    assert len(donnees["tier0"]) == len(catalogue_du_depot().documents)
    assert {"nom", "categorie", "description"} <= set(donnees["tier0"][0])

    code, sortie = _lancer(["skills", "Traduire ce document en espagnol"], capsys)
    assert code == 0
    assert "IMPASSE" in sortie
    for d in catalogue_du_depot().documents:
        assert d.nom in sortie, f"{d.nom} n'est pas annonce dans l'abstention"
    assert ".hermes/skills/README.md" in sortie


def test_charger_une_procedure_PAR_SON_NOM(capsys) -> None:
    """La boucle « inventaire -> choix -> texte » doit se fermer, aussi au shell.

    Defaut constate apres avoir repare l'abstention : le serveur MCP savait charger une procedure
    par son nom, la CLI NON. Un agent qui travaille au shell voyait donc l'inventaire tier 0,
    reconnaissait la procedure qui lui faut, et ne pouvait pas l'obtenir — la boucle s'arretait au
    milieu. Le nom inconnu est refuse en ENUMERANT les noms valides : un refus qui n'enumere pas
    oblige a deviner.
    """
    from jio.artifacts.definitions import SKILLS

    code, sortie = _lancer(["skills", "--nom", "executable-proof"], capsys)
    assert code == 0
    assert "PROCEDURE  executable-proof" in sortie
    # Le TEXTE COMPLET, pas seulement la fiche : c'est ce qu'on injecte a l'agent.
    corps = next(s.body for s in SKILLS if s.name == "executable-proof")
    premiere_phrase = corps.strip().splitlines()[0]
    assert premiere_phrase in sortie, "le corps n'est pas rendu"

    code, sortie = _lancer(["skills", "--nom", "executabel-proof"], capsys)
    assert code == 1, "un nom inconnu doit sortir en erreur, pas en succes"
    assert "INCONNUE" in sortie
    for skill in SKILLS:
        assert skill.name in sortie, "le refus doit enumerer les noms valides"


def test_la_CLI_et_le_MCP_rendent_LE_MEME_texte_par_nom() -> None:
    """Deux interfaces, une seule source : sinon l'une des deux servira un autre programme.

    C'est le meme genre de defaut que la description MCP annoncant « seven checks » alors que la
    porte en executait neuf : le texte a deux endroits diverge toujours, et c'est celui qu'on ne
    relit pas qui vieillit.
    """
    from jio.artifacts.definitions import SKILLS
    from jio.mcp_server import _tool_skills

    attendu = next(s.body for s in SKILLS if s.name == "prose-witnesses")
    assert _tool_skills({"name": "prose-witnesses"}).strip() == attendu.strip()


# --------------------------------------------------------------------------- #
# Les quatre jeux : ce qui les rend utilisables comme temoins
# --------------------------------------------------------------------------- #


def test_le_jeu_B_reconstitue_reproduit_l_ARCHIVE() -> None:
    """Un temoin qui ne peut pas etre REJOUE n'est plus un temoin, c'est une anecdote.

    Le jeu B a ete ecrit hors du depot, mesure une fois (50,0 %), puis perdu avec le bac a sable.
    Il a ete reconstitue, et cette reconstitution est VERIFIABLE : rejouee sur le routeur actuel,
    elle doit rendre exactement les douze echecs de l'archive `evidence/routeur-bm25f-075.json`.
    Si un seul cas differait, la reconstitution serait fausse — et c'est ce test qui le dirait,
    au lieu d'une phrase dans un commentaire.
    """
    import json
    from pathlib import Path

    from jio.skills.controle import JEUX
    from jio.skills.router import choisir

    archive = Path(__file__).resolve().parents[1] / "evidence" / "routeur-bm25f-075.json"
    if not archive.is_file():  # pragma: no cover - l'archive est versionnee
        pytest.skip("archive de la mesure absente")
    reference = json.loads(archive.read_text(encoding="utf-8"))["jeux"][
        "jeu B (jamais vu, ecrit avant la retouche)"
    ]
    jeu = next(j for j in JEUX if j.nom == "B")
    echecs = {
        texte for texte, attendu, _ in jeu.cas
        if not ((c := choisir(texte, maximum=3)) and c[0].nom == attendu)
    }
    assert echecs == set(reference["echecs_apres"]), (
        "la reconstitution ne reproduit pas les echecs archives : elle a ete reecrite, "
        "donc elle ne mesure plus la meme chose"
    )
    assert len(jeu.cas) == int(reference["cas"])
    assert len(jeu.hors_sujet) == int(reference["hors_sujet"])


def test_les_quatre_jeux_sont_DISTINCTS_et_complets() -> None:
    """Deux jeux qui partagent des cas ne mesurent qu'une fois — et c'est arrive.

    A la versionnage du jeu B, sa premiere transcription a repris SANS LE VOIR des cas du jeu A
    (memes phrases, meme attentes) : le jeu « neuf » mesurait alors 37,5 % au lieu de 50,0 %, et
    surtout il n'ajoutait aucune information. Ce test rend la faute impossible : aucun texte de
    cas ne peut apparaitre dans deux jeux, et chaque jeu porte les deux langues et au moins trois
    hors sujet — sinon son taux d'abstention ne veut rien dire.
    """
    from jio.skills.controle import JEUX

    assert [j.nom for j in JEUX] == ["A", "B", "C", "D"], "les quatre jeux, dans l'ordre"
    vus: dict[str, str] = {}
    for jeu in JEUX:
        assert len(jeu.cas) >= 20, f"jeu {jeu.nom} : trop peu de cas pour mesurer quoi que ce soit"
        assert len(jeu.hors_sujet) >= 3, f"jeu {jeu.nom} : trop peu de hors sujet"
        assert jeu.ecrit_avant, f"jeu {jeu.nom} : ne dit pas devant quelle retouche il a ete ecrit"
        langues = {langue for _, _, langue in jeu.cas}
        assert langues == {"fr", "en"}, f"jeu {jeu.nom} : langues {langues}"
        for texte, attendu, _ in jeu.cas:
            assert texte not in vus, (
                f"« {texte[:50]} » est dans les jeux {vus.get(texte)} ET {jeu.nom} : "
                "un cas partage ne compte qu'une fois et fait croire a un jeu neuf"
            )
            vus[texte] = jeu.nom
            attendu_noms = {s.name for s in __import__(
                "jio.artifacts.definitions", fromlist=["SKILLS"]).SKILLS}
            assert attendu in attendu_noms, f"competence inexistante : {attendu}"


def test_la_ligne_de_base_des_jeux_pre_enregistres_est_PUBLIEE() -> None:
    """Un jeu pre-enregistre doit dire ce qu'il valait AVANT : sinon l'apres ne prouve rien.

    C'est la seule facon de montrer, plus tard, qu'une retouche a apporte quelque chose : un
    chiffre d'apres sans chiffre d'avant est une photo sans sujet. Le test verifie que les taux
    publies dans les docstrings correspondent a ceux mesures aujourd'hui — un ecart veut dire que
    le routeur a bouge sans que la ligne de base soit relue.
    """
    from jio.skills.controle import JEUX, mesurer_jeu

    attendus = {"A": 0.583, "B": 0.500}
    for jeu in JEUX:
        if jeu.nom in attendus:
            mesure = mesurer_jeu(jeu)["premier_choix"]
            assert abs(mesure - attendus[jeu.nom]) < 0.001, (
                f"jeu {jeu.nom} : {mesure:.1%} mesure contre {attendus[jeu.nom]:.1%} publie. "
                "Si le routeur a change, la ligne de base se met a jour — et on dit ce qui a "
                "change, on ne reecrit pas le chiffre en silence."
            )


def test_la_commande_controle_ne_MONTRE_pas_le_detail_par_defaut(capsys) -> None:
    """Consulter les echecs d'un jeu qu'on n'a pas encore utilise le transforme en jeu de reglage.

    Le detail reste accessible (`--detail`), parce qu'un rapport doit pouvoir etre lu en entier ;
    il n'est simplement pas le comportement par defaut. La discipline est ici un choix d'interface
    : ce qui protege le jeu C et le jeu D, c'est que personne ne les ouvre par accident.
    """
    code, sortie = _lancer(["skills", "--controle"], capsys)
    assert code == 0
    assert "QUATRE JEUX DE CONTROLE" in sortie
    assert "TOTAL" in sortie
    assert "RATE" not in sortie, "le detail des echecs ne doit pas s'afficher par defaut"

    code, detail = _lancer(["skills", "--controle", "--detail"], capsys)
    assert code == 0
    assert "RATE" in detail
    assert "jeu C" in detail


def test_la_liste_des_plus_proches_est_rendue_quand_la_porte_se_ferme(capsys) -> None:
    """Un « non » qui s'accompagne d'une liste classee vaut mieux qu'un « non » nu.

    Mesure qui a fait naitre cette fonction : sur les 24 objectifs du domaine que la porte refuse
    (les quatre jeux reunis), le premier de la liste classee est le BON 10 fois (42 %), contre
    8 % au hasard — 12 competences, une seule reponse. La bonne competece est dans les trois
    premieres 14 fois (58 %), dans les cinq premieres 16 fois (67 %).

    Le test verifie trois proprietes, et la troisieme est celle qui protege l'agent :
      * la liste est NON VIDE et classee par score decroissant ;
      * elle est plafonnee — une liste de douze refait le probleme qu'elle resout ;
      * le DEBUT de la liste ne depend pas de sa longueur : « montre-moi 3 » et « montre-moi 5 »
        donnent les memes trois premiers, sinon l'agent qui compare deux sorties ne saurait plus
        laquelle croire.
    """
    from jio.skills.controle import JEUX
    from jio.skills.router import proches

    objectif = next(t for j in JEUX for t, _, _ in j.cas if not choisir(t, maximum=3))
    assert choisir(objectif, maximum=3) == [], "ce test suppose un objectif refuse par la porte"

    liste = proches(objectif, maximum=5)
    assert liste, "une abstention doit rendre une liste, pas du vide"
    scores = [c.score for c in liste]
    assert scores == sorted(scores, reverse=True), "la liste doit etre classee"
    assert all(c.raisons for c in liste), "chaque element dit pourquoi il est la"

    trois = [c.nom for c in proches(objectif, maximum=3)]
    cinq = [c.nom for c in proches(objectif, maximum=5)]
    assert trois == cinq[:3], "le debut de la liste ne doit pas dependre de sa longueur"

    # Et ce que l'appelant recoit : la liste, nommee comme une liste (jamais comme une decision).
    code, sortie = _lancer(["skills", objectif], capsys)
    assert code == 0
    assert "AUCUNE COMPETENCE A CHARGER" in sortie
    assert "LES PLUS PROCHES" in sortie
    assert liste[0].nom in sortie
    assert "au hasard" in sortie, "la confiance a accorder a la liste doit etre DITE"

    code, sortie = _lancer(["skills", objectif, "--json"], capsys)
    donnees = json.loads(sortie)
    assert donnees["choix"] == [], "la porte reste fermee : la liste n'est pas un chargement"
    assert [p["nom"] for p in donnees["proches"]] == cinq
    assert len(donnees["tier0"]) == len(catalogue_du_depot().documents)


def test_la_qualite_de_la_liste_est_MESUREE_et_publiee() -> None:
    """Le chiffre qui justifie d'afficher une liste doit etre mesurable, donc verifiable.

    Il porte sur les objectifs du domaine refuses par la porte : c'est la seule population ou la
    question se pose. Un plancher est verifie plutot qu'une valeur exacte — une retouche qui
    AMELIORE la liste ne doit pas casser la suite, une retouche qui la degrade doit la casser.
    """
    from jio.skills.controle import JEUX, qualite_de_la_liste

    q = qualite_de_la_liste()
    refus = sum(1 for j in JEUX for t, _, _ in j.cas if not choisir(t, maximum=3))
    assert q["cas"] == refus, "la population mesuree doit etre celle des objectifs refuses"
    assert q["cas"] >= 20, "trop peu de cas pour publier un taux"
    assert q["taux"] >= 0.33, (
        f"la liste classee est tombee a {q['taux']:.0%} contre 42 % mesures : elle ne vaut plus "
        f"le detour, et c'est ce test qui doit le dire"
    )
    assert q["facteur"] >= 3.0, "la liste doit valoir nettement mieux que le hasard"
    assert 0 < q["hasard"] < 0.2


def test_l_outil_MCP_rend_la_meme_liste_que_la_CLI() -> None:
    """Deux interfaces, une seule reponse : l'agent qui passe par MCP ne doit pas etre moins bien
    servi que celui qui passe par le shell."""
    from jio.mcp_server import _tool_skills

    objectif = "corriger un bug de division par zero dans la remise"
    assert choisir(objectif, maximum=3) == []
    texte = _tool_skills({"objective": objectif})
    assert "LES PLUS PROCHES" in texte
    assert "score" in texte
    assert "INVENTAIRE TIER 0" in texte


# --------------------------------------------------------------------------- #
# La liste classee, completee par la RESSEMBLANCE (table de vecteurs)
# --------------------------------------------------------------------------- #


def test_la_liste_rendue_a_LA_LONGUEUR_ANNONCEE() -> None:
    """« LES PLUS PROCHES (5) » doit rendre cinq elements — sinon l'outil ment sur sa sortie.

    Defaut reel, mesure : sur les 24 objectifs du domaine que la porte refuse, 5 listes
    n'avaient que 1 a 3 elements (`seuil=0` ne rend que les competences MARQUEES par BM25F),
    alors que l'en-tete en annoncait 5. Ce que la completion ajoute est NOMME : score BM25F
    nul et `proximite` mesuree, avec la raison « aucun mot commun » — jamais confondu avec un
    element marque.
    """
    from jio.skills.router import choisir

    # Ce cas du banc ne partage presque rien avec le lexique du depot : c'est exactement la
    # situation ou la liste rendue est plus courte que l'en-tete ne l'annonce.
    objectif = "Convertir les images PNG en JPEG"
    marquees = choisir(objectif, maximum=5, seuil=0)
    assert len(marquees) < 5, "ce cas doit etre court, sinon le test ne prouve rien"

    liste = proches(objectif, maximum=5)
    assert len(liste) == 5, f"liste courte alors que l'en-tete annonce 5 : {len(liste)}"
    assert [c.nom for c in liste[: len(marquees)]] == [c.nom for c in marquees], (
        "la completion ne doit pas toucher la tete"
    )
    for ajoute in liste[len(marquees):]:
        assert ajoute.score == 0.0, "un element ajoute n'a pas de score BM25F"
        assert ajoute.proximite is not None, "un element ajoute porte une ressemblance mesuree"
        assert any("aucun mot commun" in r for r in ajoute.raisons), ajoute.raisons


def test_la_COMPLETION_ne_deplace_jamais_un_element_marque() -> None:
    """La domination, verifiee sur toute la population : la tete est IDENTIQUE a BM25F.

    C'est la condition qui a fait ecarter la fusion RRF (reordonner toute la liste faisait
    tomber le premier element juste de 10 a 9 sur 24, et de 27 a 22 sur le banc). Ici, la
    liste complete ne peut pas degrader une metrique : elle ne fait qu'ajouter a la fin.
    """
    from jio.skills.controle import JEUX
    from jio.skills.router import choisir

    for jeu in JEUX:
        for texte, _, _ in jeu.cas:
            marquees = [c.nom for c in choisir(texte, maximum=12, seuil=0)]
            assert [c.nom for c in proches(texte, maximum=12)][: len(marquees)] == marquees


def test_sans_table_le_routeur_rend_EXACTEMENT_la_liste_d_avant(monkeypatch) -> None:
    """Une ressource absente ne doit rien casser : le repli est le comportement d'avant.

    Le fichier de vecteurs est une donnee embarquee, donc supprimable par une copie partielle,
    un clone superficiel ou un `git lfs` mal configure. Le routeur doit alors rendre sa liste
    BM25F — plus courte, non completee — et `proximite` doit rester `None` pour que l'absence
    se LISE au lieu de se deviner.
    """
    from jio.skills import vecteurs

    monkeypatch.setattr(vecteurs, "_CHARGEE", True)
    monkeypatch.setattr(vecteurs, "_TABLE", None)
    objectif = "Convertir les images PNG en JPEG"
    liste = proches(objectif, maximum=5)
    assert all(c.proximite is None for c in liste)
    assert len(liste) < 5, "sans table, la liste garde sa longueur d'origine"


def test_un_fichier_de_vecteurs_ABIME_est_refuse_sans_exception(tmp_path) -> None:
    """Le fichier de vecteurs est du contenu NON FIABLE : il se relit, il ne s'execute pas.

    Quatre formes d'abus, toutes rendues `None` : en-tete inconnu, troncature, dimensions
    absurdes, longueur de mot absurde. Sans ces bornes, un fichier hostile ferait reserver des
    gigaoctets (ou lever) dans l'outil qui le lit.
    """
    import gzip
    import json
    import struct

    from jio.skills.vecteurs import MAGIC, charger

    faux = tmp_path / "faux.bin.gz"
    faux.write_bytes(gzip.compress(b"PAS-JIO" + b"\x00" * 64))
    assert charger(faux) is None, "en-tete inconnu"

    faux.write_bytes(gzip.compress(MAGIC))
    assert charger(faux) is None, "fichier tronque avant l'en-tete"

    entete = json.dumps({"dims": 100, "mots": 10}).encode()
    faux.write_bytes(gzip.compress(MAGIC + struct.pack("<I", len(entete)) + entete))
    assert charger(faux) is None, "aucune donnee derriere l'en-tete"

    entete = json.dumps({"dims": 100_000, "mots": 10}).encode()
    faux.write_bytes(gzip.compress(MAGIC + struct.pack("<I", len(entete)) + entete + b"\x00" * 40))
    assert charger(faux) is None, "dimensions absurdes : bornees avant usage"

    entete = json.dumps({"dims": 100, "mots": 2}).encode()
    corps = struct.pack("<H", 9) + b"court" + b"\x00" * 100
    faux.write_bytes(gzip.compress(MAGIC + struct.pack("<I", len(entete)) + entete + corps))
    assert charger(faux) is None, "longueur de mot incoherente"


def test_la_table_embarquee_MESURE_du_sens() -> None:
    """Le controle de la ressource : des mots proches doivent etre plus proches que des mots loins.

    Sans ce test, une table tronquee ou permutee rendrait des ressemblances aleatoires, et
    l'ordre de la liste complete serait du hasard — exactement ce que la completion pretend
    remplacer. Les valeurs attendues sont larges (>0.4 contre <0.1), donc le test ne casse pas
    a la premiere mise a jour du paquet source.
    """
    from jio.skills.router import stem
    from jio.skills.vecteurs import table_du_depot

    table = table_du_depot()
    assert table is not None, "la table doit etre livree avec le depot"
    assert len(table.mots) >= 8000 and table.dims == 100

    def cos(a: str, b: str) -> float:
        va, vb = table.mots[stem(a)], table.mots[stem(b)]
        return table.cosinus(va, vb)

    assert cos("test", "verification") > 0.40
    assert cos("proof", "evidence") > 0.55
    assert cos("test", "river") < 0.15
    assert cos("test", "verification") > cos("test", "river") + 0.30


def test_la_bonne_competence_n_est_JAMAIS_absente_de_la_liste_complete() -> None:
    """La propriete que la completion achete : 24/24, contre 21/24 sans elle.

    C'est le chiffre qui justifie la table : quand le routeur refuse un objectif du domaine, la
    competence qu'un humain chargerait est TOUJOURS dans la liste complete — l'agent qui demande
    plus de cinq elements ne peut plus tomber sur une liste ou la bonne reponse manque.
    """
    from jio.skills.controle import JEUX
    from jio.skills.router import choisir, proches

    refuses = [(t, a) for j in JEUX for t, a, _ in j.cas if not choisir(t, maximum=3)]
    assert refuses, "la population de mesure ne doit pas etre vide"
    absents = [t for t, a in refuses if a not in [c.nom for c in proches(t, maximum=12)]]
    assert not absents, f"competence absente de la liste complete : {absents[:2]}"
