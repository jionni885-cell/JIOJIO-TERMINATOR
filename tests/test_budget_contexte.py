"""Le budget de contexte : ce que la configuration coute AVANT la premiere question.

Trois seuils mesures sur le terrain servent d'arbitre : ~150 lignes pour un fichier de
contexte (au-dela il est survole), ~5 000 jetons par competence, ~25 000 pour la
bibliotheque. Ce module verifie que la mesure est honnete — intervale, pas de fausse
precision — et que le rapport ne fabrique pas de total qu'aucune session ne paie.
"""

from __future__ import annotations

from pathlib import Path

from jio.artifacts.budget import (
    PAR_JETON_MAX,
    PAR_JETON_MIN,
    SEUILS,
    mesurer,
    resume,
    verdict,
)
from jio.artifacts.definitions import AGENTS, SKILLS

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# 1. La mesure : un intervalle, jamais une fausse precision
# --------------------------------------------------------------------------- #


def test_la_mesure_rend_un_intervalle_et_non_un_chiffre() -> None:
    """Un tokenizer reel est une dependance, et la mesure varie d'un modele a l'autre.

    Rendre un chiffre unique donnerait une precision que nous n'avons pas : la borne
    basse compte 3,2 caracteres par jeton (francais, code), la haute 4,4 (prose anglaise).
    """
    mesure = mesurer("x.md", "a" * 4400)

    assert mesure.jetons_min == round(4400 / PAR_JETON_MAX)
    assert mesure.jetons_max == round(4400 / PAR_JETON_MIN)
    assert mesure.jetons_min < mesure.jetons_max
    assert "~" in mesure.intervalle()


def test_les_lignes_vides_finales_ne_comptent_pas() -> None:
    """Elles ne se lisent pas, donc elles ne coutent rien."""
    assert mesurer("a.md", "un\ndeux\n\n\n").lignes == 2
    assert mesurer("b.md", "un\ndeux").lignes == 2


def test_un_fichier_hors_budget_est_signale_sans_ambiguite() -> None:
    """Deux verdicts distincts : DEPASSE (borne basse au-dessus) et « a verifier »."""
    enorme = mesurer("gros.md", "x " * 20_000)
    assert enorme.depasse(SEUILS["competence_jetons"])
    assert enorme.peut_depasser(SEUILS["competence_jetons"])

    petit = mesurer("petit.md", "x " * 100)
    assert not petit.peut_depasser(SEUILS["competence_jetons"])


# --------------------------------------------------------------------------- #
# 2. Le rapport ne fabrique pas de total qu'aucune session ne paie
# --------------------------------------------------------------------------- #


def test_un_ensemble_alternatif_ne_produit_pas_de_total() -> None:
    """Un outil ne lit qu'UN fichier de contexte : les additionner serait faux.

    Le premier jet de `jio artifacts --budget` annoncait « contexte injecte au demarrage :
    ~9 285 jetons » en sommant les cinq dialectes. Aucune session ne paie ce total : Claude
    lit CLAUDE.md, Cursor lit `.cursor/rules/jio.mdc`. Un chiffre faux dans un rapport sur
    le contexte est exactement ce que ce rapport existe pour eviter.
    """
    mesures = [mesurer("CLAUDE.md", "x" * 4000), mesurer("GEMINI.md", "x" * 4000)]

    avec_total = resume(mesures, "titre")
    sans_total = resume(mesures, "titre", total=False)

    assert any("TOTAL" in ligne for ligne in avec_total)
    assert not any("TOTAL" in ligne for ligne in sans_total)
    assert len(sans_total) < len(avec_total)


# --------------------------------------------------------------------------- #
# 3. Les artefacts REELS de ce depot tiennent dans leur budget
# --------------------------------------------------------------------------- #


def test_chaque_competence_tient_dans_les_5000_jetons() -> None:
    for skill in SKILLS:
        mesure = mesurer(skill.name, skill.body)
        assert not mesure.depasse(SEUILS["competence_jetons"]), (
            f"{skill.name} : {mesure.intervalle()} jetons, seuil "
            f"{SEUILS['competence_jetons']}"
        )


def test_la_bibliotheque_de_competences_tient_dans_les_25000_jetons() -> None:
    total = sum(mesurer(s.name, s.body).jetons for s in SKILLS)
    assert total < SEUILS["bibliotheque_jetons"], f"{total} jetons"


def test_aucun_fichier_de_contexte_ne_depasse_150_lignes() -> None:
    """Au-dela, un fichier de contexte est survole, pas lu."""
    for chemin in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        fichier = REPO / chemin
        if not fichier.is_file():
            continue
        mesure = mesurer(chemin, fichier.read_text(encoding="utf-8"))
        assert mesure.lignes <= SEUILS["contexte_lignes"], (
            f"{chemin} : {mesure.lignes} lignes pour un seuil de {SEUILS['contexte_lignes']}"
        )


def test_le_verdict_utilise_la_ligne_pour_le_contexte_et_le_jeton_pour_une_competence() -> None:
    """Deux budgets differents, une seule fonction — et pas la meme unite."""
    long_mais_leger = mesurer("CLAUDE.md", "a\n" * 200)  # 200 lignes, tres peu de jetons
    # Assez lourd pour que meme la borne BASSE depasse 5 000 jetons : un cas ambigu
    # (« a verifier ») ne doit pas se melanger aux depassements fermes.
    court_mais_lourd = mesurer("SKILL.md", "mot " * 8000)

    verdicts = verdict(
        [long_mais_leger, court_mais_lourd],
        est_competence=lambda chemin: chemin.endswith("SKILL.md"),
    )
    texte = "\n".join(verdicts)
    assert "2 fichier(s) DEPASSENT" in texte
    assert "CLAUDE.md" in texte and "SKILL.md" in texte


def test_le_verdict_est_vide_de_bruit_quand_tout_tient() -> None:
    verdicts = verdict([mesurer("petit.md", "x " * 50)])
    assert any("Aucun fichier ne depasse" in ligne for ligne in verdicts)


# --------------------------------------------------------------------------- #
# 4. La coherence avec ce qui est REELLEMENT charge par chaque outil
# --------------------------------------------------------------------------- #


def test_chaque_agent_opencode_est_mesurable_et_bornant() -> None:
    """Un agent est charge a la demande : il doit rester petit pour rester chargeable."""
    for agent in AGENTS:
        assert agent.prompt, agent.name
        mesure = mesurer(agent.name, agent.prompt)
        assert mesure.lignes < 200, f"{agent.name} : {mesure.lignes} lignes"


def test_les_trois_seuils_sont_ceux_qui_ont_ete_mesures() -> None:
    """Ces trois nombres sont des MESURES de terrain, pas des reglages de confort.

    150 lignes : au-dela, un fichier de contexte (`AGENTS.md`) est survole plutot que lu ;
    5 000 jetons : la limite d'UNE competence ; 25 000 : la bibliotheque entiere. Le
    rapport les CITE dans ses messages — un seuil qui glisse d'une unite ferait dire au
    rapport autre chose que ce qu'il a mesure.

    Mesure a l'origine : `jio mutants` a montre que les trois constantes pouvaient toutes
    changer de 1 sans qu'aucun test ne bouge, parce que tous les tests les lisaient
    SYMBOLIQUEMENT (`SEUILS[...]`).
    """
    assert SEUILS == {
        "contexte_lignes": 150,
        "competence_jetons": 5_000,
        "bibliotheque_jetons": 25_000,
    }


def test_les_deux_limites_de_competence_ne_peuvent_pas_diverger() -> None:
    """`MAX_COMPETENCE` (audit des competences) doit valoir le seuil du budget de contexte.

    Deux constantes pour une seule limite, c'est une limite qui tombera : le jour ou l'une
    bouge, l'audit d'une competence et sa mesure de contexte ne diraient plus la meme chose,
    et rien ne le signalerait.
    """
    from jio.artifacts.audit_skills import MAX_COMPETENCE

    assert MAX_COMPETENCE == SEUILS["competence_jetons"]
