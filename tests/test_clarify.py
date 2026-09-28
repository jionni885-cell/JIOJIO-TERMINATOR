"""La porte de clarification : poser les questions ESSENTIELLES, et jamais plus de trois.

Ce fichier existe pour une raison precise. Une IA a qui l'on dit « ameliore le projet » part
sans rien demander : elle choisit un perimetre, un format et un critere de reussite a la place
de son utilisateur, puis livre quelque chose de plausible qui repond a une autre question. Le
resultat est plus dangereux qu'une erreur visible, parce qu'il a l'air reussi.

L'inverse est un defaut aussi : quinze questions pour un objectif clair, et on ne lui parle
plus. Les tests ci-dessous tiennent donc LES DEUX bornes : elle DOIT poser ses questions sur
un objectif vague, et elle NE DOIT PAS en poser sur un objectif actionnable.

Chaque question doit par ailleurs payer son prix : `pourquoi` (la consequence de ne pas y
repondre) et `defaut` (l'hypothese prise a defaut de reponse). Une question sans consequence
ecrite est une question de confort, et ce test la refuse.
"""

from __future__ import annotations

import inspect

from jio.clarify import MAX_QUESTIONS, analyser, formater, resume

#: Un objectif VAGUE : un souhait, sans cible, sans critere, sans perimetre.
VAGUE = "ameliore le projet"

#: Un objectif ACTIONNABLE : une action, une cible nommee (`jio/verify/entropy.py`), un
#: critere (`doit rendre False`, `avec un test qui le prouve`).
PRECIS = (
    "corriger jio/verify/entropy.py : `_numeric_equal` doit rendre False quand aucun nombre "
    "n'est present, avec un test qui le prouve"
)


def test_un_objectif_vague_declenche_des_questions_bornees() -> None:
    """Un souhait ne se travaille pas : il se clarifie — au plus `MAX_QUESTIONS` questions.

    La borne n'est pas cosmetique : au-dela de trois questions, l'utilisateur ne clarifie plus
    son besoin, il repond a un questionnaire. Trois questions bien choisies couvrent la cible,
    le critere et le perimetre — les trois qui font echouer un travail.
    """
    analyse = analyser(VAGUE)
    assert analyse.actionnable is False
    assert 1 <= len(analyse.questions) <= MAX_QUESTIONS
    assert "cible" in analyse.manquants
    assert "critere" in analyse.manquants


def test_un_objectif_actionnable_ne_pose_AUCUNE_question() -> None:
    """Action + cible nommee + critere de succes : on travaille, on ne demande pas.

    Mesure a l'origine : la premiere version de la porte ne reconnaissait que les verbes a
    l'infinitif et cherchait un critere sous forme de chiffre. Un objectif parfaitement precis
    (« corriger X : Y doit rendre False, avec un test qui le prouve ») sortait donc avec des
    questions — un faux positif qui, a l'usage, apprend a ignorer la porte.
    """
    analyse = analyser(PRECIS)
    assert analyse.actionnable is True
    assert analyse.questions == ()
    assert analyse.manquants and "cible" not in analyse.manquants
    assert "critere" not in analyse.manquants
    assert "AUCUNE QUESTION" in formater(analyse)


def test_les_formes_conjuguees_sont_reconnues_comme_l_infinitif() -> None:
    """« ameliore », « corrige », « analyse » : les imperatifs portent autant d'information.

    Un utilisateur ecrit a l'imperatif. Un lexique d'infinitifs seuls rate l'action la plus
    courante et pose une question d'action sur un objectif qui en porte une. La recherche se
    fait sur le radical, et ces cas le prouvent.
    """
    for objectif, famille in (
        ("ameliore le module de verification", "amelioration"),
        ("corrige la borne de mutation", "correction"),
        ("analyse le journal de la derniere mission", "analyse"),
        ("documente la porte de clarification", "explication"),
        ("mesure le gain du harness", "analyse"),
    ):
        analyse = analyser(objectif)
        assert analyse.action != "(aucune action reconnue)", objectif
        assert analyse.action.startswith("vague:") is False or famille == "amelioration"


def test_chaque_question_PORTE_sa_consequence_et_son_defaut() -> None:
    """Une question sans consequence ecrite, ou sans hypothese, n'entre pas dans la porte.

    C'est la regle qui separe une question essentielle d'une question de confort. On l'exige
    pour CHAQUE question de CHAQUE cas vague : une seule exception suffirait a autoriser les
    autres, et la porte deviendrait un questionnaire.
    """
    for objectif in (
        VAGUE,
        "fais quelque chose de mieux",
        "analyse",
        "corrige le bug",
        "il faudrait ameliorer les performances",
    ):
        analyse = analyser(objectif)
        for question in analyse.questions:
            assert question.pourquoi.strip().endswith((".", "!")), question
            assert len(question.pourquoi) > 40, question
            assert question.defaut.strip(), question
            assert len(question.defaut) > 20, question
            # Le defaut ne dit jamais « je m'arrete et j'attends » : une porte qui bloque
            # sans proposer d'hypothese transforme une question en ultimatum.
            assert "j'attends" not in question.defaut


def test_le_mode_STRICT_bloque_et_le_mode_ASSUME_poursuit() -> None:
    """Meme objectif, deux comportements — et le mode est ecrit dans le verdict.

    `strict` : `bloquant` est vrai, l'appelant doit poser les questions (code 3).
    `assume` : on avance, mais les hypotheses prises sont DECLAREES. Un systeme qui avance en
    silence sur un objectif ambigu produit exactement le resultat plausible et faux que cette
    porte existe pour empecher.
    """
    strict = analyser(VAGUE, mode="strict")
    assume = analyser(VAGUE, mode="assume")
    assert strict.bloquant is True
    assert assume.bloquant is False
    assert strict.questions == assume.questions, "les questions ne dependent pas du mode"
    assert "BLOQUEE" in resume(strict).upper() or "bloquee" in resume(strict)
    assert "DECLAREES" in resume(assume).upper() or "declarees" in resume(assume)
    assert "0 question" in resume(analyser(PRECIS))


def test_un_mode_inconnu_est_REFUSE_et_un_objectif_vide_le_dit() -> None:
    """Un mode mal orthographie leve ; un objectif vide rend UNE question, pas une analyse.

    Mesure a l'origine : un mode libre (par exemple `"strict "` avec une espace, ou `"hard"`)
    se serait comporte comme `assume` SANS le dire : la porte aurait annonce un blocage qu'elle
    n'appliquait pas. Un objectif vide, lui, n'est pas ambigu — il est absent, et ca se dit.
    """
    import pytest

    with pytest.raises(ValueError, match="strict "):
        analyser(VAGUE, mode="strict ")  # espace finale : refusee, pas toleree
    with pytest.raises(ValueError):
        analyser(VAGUE, mode="hard")

    vide = analyser("")
    assert vide.actionnable is False
    assert vide.avancable is False
    assert len(vide.questions) == 1
    assert vide.questions[0].signal == "objectif"
    assert "rien" in vide.motif.lower() or "vide" in vide.motif.lower()


def test_le_contexte_peut_fournir_ce_qui_manque_a_l_objectif() -> None:
    """Un objectif court dans un projet documente n'est pas ambigu : la source existe.

    C'est le cas reel de ce depot : `AGENTS.md` et le README portent le perimetre, la source
    et le format. Sans contexte, la porte juge l'objectif seul — et le dit dans ses indices.
    """
    sans = analyser("corrige")
    avec = analyser(
        "corrige",
        contexte="Le fichier jio/verify/mutation.py porte MUTATION_BUDGET ; la suite doit rester verte.",
    )
    def signal(analyse, nom: str) -> bool:
        return next(s.present for s in analyse.signaux if s.nom == nom)

    # Le contexte ne peut fournir que des faits DU MONDE : la source et le perimetre. La
    # cible et le critere restent ceux de la demande — les deduire du projet serait choisir
    # a la place de l'utilisateur.
    assert signal(sans, "source") is False
    assert signal(avec, "source") is True
    assert signal(sans, "cible") is False and signal(avec, "cible") is False
    assert "cible" in avec.manquants, "la cible appartient a la demande, jamais au projet"


def test_le_verdict_est_lisible_par_une_machine() -> None:
    """`as_dict()` porte les signaux, les questions ET les hypotheses : de quoi decider.

    Une IA qui appelle la porte doit pouvoir extraire les questions sans analyser du texte
    formate pour un humain. Les hypotheses y figurent separement, parce que ce sont elles qui
    doivent etre recopiees en tete de livraison.
    """
    donnees = analyser(VAGUE).as_dict()
    assert donnees["actionnable"] is False
    assert isinstance(donnees["signaux"], dict) and len(donnees["signaux"]) == 6
    assert donnees["questions"] and "hypotheses" in donnees
    for question in donnees["questions"]:
        assert set(question) == {"signal", "question", "pourquoi", "defaut"}
    assert analyser(PRECIS).as_dict()["questions"] == []


def test_le_formateur_n_ampute_jamais_une_question() -> None:
    """Le texte affiche est enroule, jamais tronque : une question coupee n'est plus une question.

    Mesure a l'origine : la premiere version coupait chaque ligne a 100 caracteres, et la fin
    des questions disparaissait (« ...seulement te demander de me cr »). Une question tronquee
    fait douter de l'outil au moment precis ou il demande a etre cru.
    """
    analyse = analyser(VAGUE)
    plat = " ".join(formater(analyse).split())
    for question in analyse.questions:
        # Chaque question est presente EN ENTIER (espaces normalises) : rien n'est coupe.
        assert " ".join(question.question.split()) in plat
        assert " ".join(question.pourquoi.split()) in plat
        assert " ".join(question.defaut.split()) in plat
    # Aucune ligne ne se termine au milieu d'un mot du a une troncature : la derniere ligne
    # d'un paragraphe est soit vide, soit une phrase finie ou un mot entier.
    for ligne in formater(analyse).splitlines():
        assert len(ligne) <= 100, ligne


# --------------------------------------------------------------------------- #
# Le banc d'objectifs : la porte est MESUREE, pas supposee bonne
# --------------------------------------------------------------------------- #


def test_la_porte_ne_se_trompe_sur_AUCUN_objectif_du_banc() -> None:
    """Sur 41 objectifs reels annotes a la main : 0 faux positif, 0 faux negatif.

    C'est le test le plus important de ce fichier. Une porte de clarification qui demande a
    tort aprend a l'utilisateur a l'ignorer ; une porte qui ne demande pas quand il faut
    laisse le systeme choisir a sa place. Les deux se mesurent, et les deux doivent rester a
    zero — pas « faibles » : a zero, parce que le corpus est petit et annote.

    Quand ce test echoue, il ne dit pas « le seuil est depasse » : il nomme l'objectif et
    l'erreur, dans `jio/bench/objectifs.py`.
    """
    from jio.bench.objectifs import CORPUS, mesurer

    rapport = mesurer()
    assert rapport.total == len(CORPUS) >= 30, "le banc doit rester representatif"
    assert rapport.faux_positifs == 0, "\n".join(rapport.erreurs)
    assert rapport.faux_negatifs == 0, "\n".join(rapport.erreurs)
    assert rapport.signaux_oublies == 0, "\n".join(rapport.erreurs)
    assert rapport.signaux_en_trop == 0, "\n".join(rapport.erreurs)
    assert rapport.precision == 1.0 and rapport.rappel == 1.0
    assert rapport.max_questions <= MAX_QUESTIONS
    # ET le nombre annonce dans la docstring ci-dessus est verifie. Ce chiffre a deja menti
    # une fois (il annoncait 37 pour 38) : un nombre ecrit dans un test qui MESURE est le
    # pire endroit pour un nombre faux, parce qu'il est lu comme une mesure. Il est
    # desormais mesure lui aussi — la docstring se relit avec le banc."""
    nombre = f"Sur {len(CORPUS)} objectifs"
    texte = inspect.getdoc(test_la_porte_ne_se_trompe_sur_AUCUN_objectif_du_banc) or ""
    assert texte.startswith(nombre), (
        f"la docstring annonce {texte.splitlines()[0][:40]!r} et le banc en compte "
        f"{len(CORPUS)} : `jio chiffres --appliquer` ne corrige pas les docstrings, "
        "corrigez-la a la main"
    )


def test_le_banc_contient_LES_DEUX_cas_et_des_objectifs_des_deux_langues() -> None:
    """Un banc qui ne contient que des cas faciles mesure la facilite du banc.

    On exige donc : des objectifs actionnables ET des objectifs ambigus, dans les deux
    langues, et au moins un cas limite (une action destructrice parfaitement claire, ou la
    porte ne doit PAS demander « sur quoi ? »).
    """
    from jio.bench.objectifs import CORPUS

    actionnables = [o for o in CORPUS if o.attendu]
    ambigus = [o for o in CORPUS if not o.attendu]
    assert len(actionnables) >= 8 and len(ambigus) >= 15
    assert any("test" in o.texte and o.attendu for o in CORPUS)
    assert any(o.texte.startswith(("fix ", "add ")) for o in CORPUS), "aucun objectif anglais"
    assert any("supprimer" in o.texte for o in CORPUS), "aucun cas limite destructeur"
    for item in CORPUS:
        assert item.note, f"objectif sans justification : {item.texte!r}"


def test_les_regles_de_decision_de_la_porte_sont_Ecrites() -> None:
    """Les trois regles qui decident quelles questions sont essentielles sont verifiables.

    Elles ont chacune ete payees par une mesure (six faux positifs, un faux negatif) : les
    ecrire ici sous forme de test empeche de les casser par megarde au prochain reglage.
    """
    # 1. `source` et `format` ne declenchent JAMAIS de question a eux seuls.
    analyse = analyser("corrige jio/verify/entropy.py, _numeric_equal doit rendre False, "
                       "avec un test qui le prouve")
    assert analyse.actionnable and analyse.questions == ()
    assert "source" in analyse.manquants or "format" in analyse.manquants, (
        "ce cas doit bien laisser au moins un signal non essentiel absent"
    )

    # 2. Le critere peut etre IMPLIQUE par l'action et la cible, mais seulement alors.
    clair = analyser("supprimer jio/artifacts/doctrine.py")
    assert clair.actionnable, "supprimer un fichier nomme est une mission claire"
    vague = analyser("ajoute des tests")
    assert not vague.actionnable, "« ajoute des tests » n'a ni cible ni critere"

    # 3. `perimetre` n'est demande que si la cible ET le critere manquent.
    signaux = {q.signal for q in analyser("ameliore le projet").questions}
    assert "perimetre" in signaux
    # Cible ET critere absents (« corrige le bug ») : le perimetre rejoint les questions.
    signaux = {q.signal for q in analyser("corrige le bug").questions}
    assert {"cible", "critere", "perimetre"} <= signaux
    # Cible presente, critere absent (« corrige jio/verify/entropy.py ») : PAS de question de
    # perimetre. Le travail a un objet precise ; demander ce qui est interdit serait du
    # confort, et c'est ce confort qui a produit six faux positifs sur trente et un cas.
    signaux = {q.signal for q in analyser("corrige jio/verify/entropy.py").questions}
    assert signaux == {"critere"}


def test_la_borne_de_questions_est_un_NOMBRE_fige_et_pas_un_renvoi_a_elle_meme() -> None:
    """`MAX_QUESTIONS == 3`, et la borne MORD : le pire objectif en recoit exactement 3.

    Mesure a l'origine : `jio mutants` a montre que ce `3` pouvait passer a `4` sans qu'aucun
    test ne bouge — parce que les tests comparaient `len(questions) <= MAX_QUESTIONS`, donc la
    constante se comparait a elle-meme. Un objet qui se cite en guise de preuve ne prouve rien.

    On exige donc les deux : la valeur, ET le comportement au-dela (quatre signaux manquants
    doivent rendre trois questions, pas quatre).
    """
    from jio.clarify import MAX_QUESTIONS

    assert MAX_QUESTIONS == 3
    # « fais en sorte que ca marche mieux » : action, cible, critere ET perimetre manquent.
    pire = analyser("fais en sorte que ca marche mieux")
    assert len(pire.manquants) >= 4
    assert len(pire.questions) == MAX_QUESTIONS, "la borne doit mordre, pas seulement exister"


def test_le_classement_des_questions_suit_leur_POIDS() -> None:
    """La question dont l'ignorance coute le plus passe devant — mesurable, pas cosmetique.

    `Question.poids` vaut 3 pour la cible et le critere, 2 pour la source et le perimetre, 1
    pour le format et l'action. Le tri est verifie en comparant les poids rendus : si le tri
    disparaissait, l'ordre du catalogue le masquerait la plupart du temps — et un jour ou
    l'ordre changerait, la porte poserait d'abord la question la moins utile.
    """
    analyse = analyser("ameliore le projet")
    poids = [q.poids for q in analyse.questions]
    assert poids == sorted(poids, reverse=True), poids
    assert all(p >= 1 for p in poids)
    # Un poids manquant dans la construction leverait : le champ est obligatoire.
    import dataclasses

    from jio.clarify import Question

    assert dataclasses.fields(Question)[-1].default is dataclasses.MISSING, (
        "un poids par defaut serait une valeur que personne n'utilise"
    )


# --------------------------------------------------------------------------- #
# Le mandat de poursuite : la question est « jusqu'ou », pas « quoi faire »
# --------------------------------------------------------------------------- #


def test_un_mandat_de_poursuite_demande_JUSQU_OU_et_pas_QUELLE_ACTION() -> None:
    """« Continue » n'est pas une phrase sans verbe : c'est un mandat qui HERITE son action.

    Mesure a l'origine : « continue avec les axes » sortait avec la question « quelle ACTION
    attends-tu ? (corriger / ecrire / analyser…) ». A un utilisateur qui venait de dire quoi
    faire, cette question apprend une seule chose : que la porte ne lit pas. Et la vraie
    question — jusqu'ou continuer — n'etait meme pas posee.
    """
    for objectif, cible_ecrite in (
        ("continue avec les axes et ne t'arrete pas avant que tout soit parfait", True),
        ("ne t'arrête pas avant que tout soit parfait, continue", False),   # accents
        ("keep going until the whole thing is solid", False),               # anglais
        ("carry on", False),                                                # anglais court
    ):
        analyse = analyser(objectif)
        assert analyse.action == "poursuite", (objectif, analyse.action)
        # La cible est PRESENTE : ecrite si la phrase la nomme, HERITEE sinon — et dans ce cas
        # c'est ecrit noir sur blanc, pour qu'on puisse contester la lecture.
        cible = next(s for s in analyse.signaux if s.nom == "cible")
        assert cible.present, (objectif, cible)
        assert ("heritee du mandat" in cible.indice) is not cible_ecrite, (objectif, cible)
        assert "cible" not in [q.signal for q in analyse.questions], objectif
        signaux = [q.signal for q in analyse.questions]
        assert "action" not in signaux, (objectif, signaux)
        if signaux:
            assert signaux == ["critere"], (objectif, signaux)
            assert "Jusqu'ou dois-je continuer" in analyse.questions[0].question
            assert "cycle" in analyse.questions[0].defaut


def test_un_mandat_borne_ne_pose_AUCUNE_question() -> None:
    """Un mandat qui dit sa borne est decidables : zero question.

    On ne se protege pas d'un mandat, on se protege d'un mandat SANS FIN. Celui-ci dit ou il
    s'arrete : la porte doit le laisser partir.
    """
    analyse = analyser("continue jusqu'a ce que 3 cycles ne trouvent plus d'axe")
    assert analyse.questions == (), [q.signal for q in analyse.questions]


# --------------------------------------------------------------------------- #
# Les verbes : position, langue, et le nom qui n'est pas un verbe
# --------------------------------------------------------------------------- #


def test_l_action_reconnue_est_le_verbe_le_PLUS_TOT_de_la_phrase() -> None:
    """Le premier verbe de la phrase, pas le premier du dictionnaire.

    Mesure a l'origine : « ameliore la lisibilite du README pour que les nouveaux arrivants
    trouvent l'installation en moins de 2 minutes » sortait avec l'action « livraison » — le nom
    « installation » croisait le radical de « installer ». Annoncer une action que l'utilisateur
    n'a pas ecrite est pire qu'une action manquante : c'est une lecture fausse presentee comme
    une lecture.
    """
    analyse = analyser(
        "ameliore la lisibilite du README pour que les nouveaux arrivants trouvent "
        "l'installation en moins de 2 minutes"
    )
    assert analyse.action == "vague:amelioration", analyse.action
    assert analyse.questions == (), "cible nommee + critere observable : rien a demander"

    # Et l'inverse : une phrase mixte est tranchee par la POSITION, pas par l'ordre des tables.
    mixte = analyser("corrige le bug, puis add a test qui le prouve")
    assert mixte.action == "correction", mixte.action


def test_les_verbes_anglais_sont_reconnus_sans_mordre_sur_les_noms() -> None:
    """Le depot est bilingue : une porte qui ne lit qu'une langue se tait sur la moitie des cas.

    Les formes anglaises sont cherchees en MOTS ENTIERS, et c'est une decision, pas un detail :
    par radical, « additional » mordrait sur « add ». Ce test fixe les deux bords.
    """
    assert analyser("add a test to tests/test_start.py proving jio start is idempotent").action \
        == "ecriture"
    assert analyser("reduce additional latency in the engine").action == "performance"
    # « additional » n'est PAS une action : le mot entier, pas le radical.
    assert analyser("the additional latency must stay under 20 ms").action == \
        "(aucune action reconnue)"


def test_le_critere_de_COMPORTEMENT_est_reconnu_meme_elide() -> None:
    """« pour qu'il compte les jours feries » EST un critere : il est observable.

    L'elision « qu' » echappait au motif « (pour|afin) que » : la porte demandait le critere a un
    objectif qui venait de le donner. Une lettre manquante, une question inutile.
    """
    analyse = analyser(
        "corrige le calcul de moyenne dans le rapport hebdo pour qu'il compte les jours feries"
    )
    assert analyse.actionnable, analyse.manquants
    assert analyse.questions == ()


def test_un_verbe_vague_est_NOMME_comme_tel_et_sans_question_de_confort() -> None:
    """« ameliore » est reconnu ET declare vague : la famille seule ne promet rien.

    Deux exigences tenues ensemble : l'action doit etre reconnue (sinon la porte affiche « aucune
    action reconnue » sur un verbe qui existe), et elle doit etre ANNONCEE comme vague (sinon
    elle ferait passer un souhait pour une mission). Cible nommee + critere observable : malgre
    le verbe vague, il n'y a rien a demander.
    """
    assert analyser(VAGUE).action == "vague:amelioration"
    assert analyser(VAGUE).actionnable is False
    assert analyser("ameliore la lisibilite du README en moins de 30 lignes").questions == ()


# --------------------------------------------------------------------------- #
# Le banc : ce qu'il compte, et dans quels sens il regarde
# --------------------------------------------------------------------------- #


def test_le_banc_compte_les_QUESTIONS_posees_et_pas_un_booleen() -> None:
    """Le seul critere que l'utilisateur ressent : la porte a-t-elle demande quelque chose ?

    Se servir de `Analyse.actionnable` comme intermediaire produisait une accusation fausse : un
    objectif a verbe vague mais cible nommee et critere observable ne recoit AUCUNE question, et
    le banc le comptait en faux positif. Un banc qui compte faux ce qui ne coute rien pousse a
    « corriger » la porte dans le mauvais sens — c'est-a-dire a lui faire poser des questions
    inutiles.
    """
    from jio.bench.objectifs import Objectif, mesurer

    objectif = Objectif(
        "ameliore la lisibilite du README pour qu'il tienne en moins de 30 lignes",
        True, frozenset(), "verbe vague, mais cible nommee et critere observable",
    )
    analyse = analyser(objectif.texte)
    assert analyse.actionnable is False, "le verbe reste vague"
    assert analyse.questions == (), "et pourtant il n'y a rien a demander"
    rapport = mesurer((objectif,))
    assert (rapport.vrais_negatifs, rapport.faux_positifs) == (1, 0)
    assert rapport.exact, rapport.erreurs


def test_le_banc_regarde_les_signaux_DANS_LES_DEUX_SENS() -> None:
    """Voir ce qui manque, ET ne pas croire manquant ce qui est ecrit.

    Le second sens manquait : sur un mandat de boucle, la porte annoncait l'action absente et
    proposait « quelle action attends-tu ? » a un utilisateur qui venait de la donner. Aucune
    mesure ne pouvait le voir, puisque le banc ne comparait que dans un sens.
    """
    from jio.bench.objectifs import Objectif, mesurer

    # Une annotation qui declare « rien ne manque » sur un objectif qui n'a ni cible ni critere :
    # l'erreur est dans l'annotation, et le banc doit la nommer.
    menteur = Objectif("corrige le bug", False, frozenset(), "annotation incomplete, exprès")
    rapport = mesurer((menteur,))
    assert rapport.signaux_en_trop >= 2, rapport.erreurs
    assert not rapport.exact
    assert any("SIGNAL EN TROP" in e for e in rapport.erreurs)

    # Et le corpus REEL ne contient aucune erreur de ce genre.
    complet = mesurer()
    assert complet.signaux_en_trop == 0, "\n".join(complet.erreurs)
    assert complet.signaux_oublies == 0, "\n".join(complet.erreurs)
