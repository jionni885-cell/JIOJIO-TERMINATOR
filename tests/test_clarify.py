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
    sans = analyser("corrige la borne de mutation")
    avec = analyser(
        "corrige la borne de mutation",
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
    assert "cible" in avec.manquants


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
