"""Tests de l'ablation : la mesure doit dire la verite, y compris « je ne sais pas ».

Ce que ces tests protegent, dans l'ordre d'importance :

1. **McNemar exact** est verifie sur des valeurs qu'on peut calculer a la main. Un test
   statistique faux rendrait tous les verdicts faux, et personne ne le verrait ;
2. **la neutralisation fait ce qu'elle annonce** : le prover aveugle declare prouve, le
   panel complaisant garde le MEME nombre de voix (baisser le panel declencherait le
   controle de faisabilite et on mesurerait autre chose), le consensus sans quorum rend une
   decision atteinte ;
3. **le rapport ne conclut jamais trop** : zero dissociation donne « NON DISTINGUABLE »,
   jamais « inutile », et le texte le dit ;
4. **l'appariement** : tous les bras voient exactement le meme plan de missions. Un plan
   different d'un bras a l'autre mesurerait le tirage, pas le levier.
"""

from __future__ import annotations

import pytest
import json

from jio.bench.tasks import TASKS
from jio.bench.ablation import (
    LEVIERS,
    ConsensusPremierAvis,
    Comparaison,
    Issue,
    PanelSansRedTeam,
    PorteOuverte,
    ProverAveugle,
    RapportAblation,
    Bras,
    _activite_de_sens,
    _ecarts,
    _phrase_activite,
    appliquer,
    dissociations_requises,
    formater,
    levier,
    mcnemar_exact,
    mesurer,
)
from jio.audit.panel import DEFAULT_PERSONAS
from jio.core.types import MissionStatus, Verdict, Vote

# --------------------------------------------------------------------------- #
# 1. Le test statistique
# --------------------------------------------------------------------------- #


def test_mcnemar_exact_est_le_calcul_a_la_main() -> None:
    """Six dissociations unidirectionnelles donnent 2/2^6 = 3,1 % — pas 0,05 « environ »."""
    assert mcnemar_exact(6, 0) == pytest.approx(2 / 64)
    assert mcnemar_exact(0, 6) == pytest.approx(2 / 64)
    assert mcnemar_exact(10, 0) == pytest.approx(2 / 1024)
    # Symetrie : le sens ne change pas la probabilite bilaterale.
    for b, c in ((3, 1), (5, 2), (9, 4)):
        assert mcnemar_exact(b, c) == pytest.approx(mcnemar_exact(c, b))
    # Un partage equilibre ne prouve rien.
    assert mcnemar_exact(5, 5) == pytest.approx(1.0)
    # Zero dissociation : aucune donnee, donc aucune preuve (1.0, jamais 0.0).
    assert mcnemar_exact(0, 0) == 1.0


def test_le_seuil_de_conclusion_est_atteint_a_six_dissociations() -> None:
    """La note du rapport annonce « au moins 6 » : le test doit le dire pareil."""
    n = dissociations_requises(0.05)
    assert n == 6
    assert mcnemar_exact(n, 0) <= 0.05
    assert mcnemar_exact(n - 1, 0) > 0.05
    # Sous 1 %, il en faut 8 : la note serait fausse si le seuil changeait en silence.
    assert dissociations_requises(0.01) == 8


# --------------------------------------------------------------------------- #
# 2. Ce que « sans » veut dire
# --------------------------------------------------------------------------- #


def test_chaque_levier_dit_ce_que_sans_veut_dire() -> None:
    """Un levier sans phrase « sans » serait une ablation non declaree."""
    assert LEVIERS, "aucun levier mesure : le rapport serait vide"
    noms = [lev.nom for lev in LEVIERS]
    assert len(noms) == len(set(noms)), f"noms de leviers dupliques : {noms}"
    for lev in LEVIERS:
        assert lev.quoi.strip(), f"{lev.nom} : ce que la brique fait n'est pas ecrit"
        assert lev.sans.strip(), f"{lev.nom} : ce que « sans » veut dire n'est pas ecrit"
    with pytest.raises(KeyError) as exc:
        levier("levier-inexistant")
    assert "red-team" in str(exc.value), "l'erreur doit citer les leviers existants"


def test_le_prover_aveugle_declare_prouve_sans_executer() -> None:
    prover = ProverAveugle()
    res = prover.prove("x = 1", object(), hidden_checks={}, entrypoint="")
    assert res.passed, "un prover aveugle qui ne declare pas prouve ne mesure rien"
    assert prover.appels == 1
    assert res.hard_failures == ()
    # Le temoin existe MAIS ne contient aucune execution : c'est la forme sans substance.
    (temoin,) = res.witnesses
    assert temoin.command == "(aucune)"


def test_le_panel_complaisant_garde_le_nombre_de_voix() -> None:
    """Deux levier a la fois, non : si le panel retrecit, le moteur bloque la mission."""
    personas = list(DEFAULT_PERSONAS)
    panel = PanelSansRedTeam(personas)
    assert len(panel.critics) == len(personas)
    rapports = panel.run("x = 1", object())
    assert len(rapports) == len(personas)
    assert {r.vote.decision for r in rapports} == {Verdict.PASS}
    assert all(r.vote.confidence == 1.0 for r in rapports)


def test_le_consensus_sans_quorum_suit_le_premier_avis() -> None:
    moteur = ConsensusPremierAvis()
    votes = [
        Vote(agent="a", decision=Verdict.PASS, confidence=0.9),
        Vote(agent="b", decision=Verdict.FAIL, confidence=0.9),
        Vote(agent="c", decision=Verdict.FAIL, confidence=0.9),
    ]
    issue = moteur.decide(votes)
    assert issue.reached, "sans consensus, la decision est dite atteinte"
    assert issue.decision is Verdict.PASS, "c'est le PREMIER avis, meme minoritaire"
    assert issue.quorum_required == 1
    assert issue.effective_panel == 1
    # Et aucun vote du tout : la seule reponse honnete est l'abstention.
    vide = moteur.decide([])
    assert not vide.reached and vide.decision is Verdict.ABSTAIN


def test_la_porte_ouverte_accepte_tout() -> None:
    porte = PorteOuverte()
    assert porte.decide(0.0)[0], "une porte ouverte accepte meme une confiance nulle"
    assert porte.tau() == 0.0


def test_appliquer_neutralise_exactement_les_leviers_demandes() -> None:
    class FauxMoteur:
        def __init__(self) -> None:
            self.prover = object()
            self.panel = object()
            self.consensus = object()
            self.gate = object()
            self.monitor = object()
            self.memory = "memoire"
            self.bibliotheque = "biblio"
            self.router = "routeur"

            class Config:
                mutation_gate = True
                self_check = True
                differential = True
                temoins = True

            self.config = Config()

    intact = FauxMoteur()
    intact_config = (
        intact.config.mutation_gate,
        intact.config.self_check,
        intact.config.differential,
        intact.config.temoins,
    )
    moteur = appliquer(FauxMoteur(), ("preuve", "memoire", "mutation"))
    assert isinstance(moteur.prover, ProverAveugle)
    assert moteur.memory is None
    assert moteur.config.mutation_gate is False
    # Rien d'autre ne bouge : un levier qui en neutralise un autre fausserait tout.
    assert moteur.config.self_check is True
    assert moteur.config.differential is True
    assert moteur.config.temoins is True
    assert moteur.panel is not None and not isinstance(moteur.panel, PanelSansRedTeam)
    assert intact_config == (True, True, True, True)


# --------------------------------------------------------------------------- #
# 3. La mesure appariee
# --------------------------------------------------------------------------- #


def _executeur_truque():
    """Un executeur deterministe : le moteur « complet » reussit une mission sur deux.

    On ne teste pas ici le moteur (il a ses propres tests) : on teste la MECANIQUE de
    l'ablation — appariement, comptage, verdicts.
    """
    appels: list[tuple[int, int, tuple[str, ...]]] = []

    def executer(indice: int, graine: int, ablations: tuple[str, ...]) -> Issue:
        appels.append((indice, graine, ablations))
        complet = (indice + graine) % 2 == 0
        if not ablations:
            juste = complet
        elif ablations == ("preuve",):
            # Le retrait fait perdre les missions ou le moteur complet gagnait, ET
            # produit un mensonge : c'est le cas que le rapport doit hurler.
            juste = False
        else:
            juste = complet
        return Issue(
            juste=juste,
            livree=juste,
            reservee=not juste,
            silencieuse=(ablations == ("preuve",) and complet),
            abstention=False,
            appels=3,
        )

    return executer, appels


def _executeur_avec_activite(actif: bool, identique: bool = False):
    """Un executeur dont les missions portent une empreinte d'activite.

    `actif=False` : la brique enlevee ne change RIEN a ce qui est compte — le banc ne
    l'exerce pas. `actif=True` : elle coupe un temoin execute, sans que le verdict bouge.
    `identique=True` : seuls des compteurs de VOLUME changent (jetons, evenements) — ce que
    l'instrument doit refuser de prendre pour de l'activite.
    """

    def executer(indice: int, graine: int, ablations: tuple[str, ...]) -> Issue:
        sans = bool(ablations)
        temoins = 4 if (not sans or not actif) else 3
        activite: dict[str, int] = {"temoins": temoins, "usage:events": 100 + indice}
        if identique:
            # Volume seulement : la valeur depend du bras, pas d'un observable de sens.
            activite["usage:events"] = 100 + indice + (1 if sans else 0)
            activite["temoins"] = 4
        return Issue(
            juste=True,
            livree=True,
            reservee=False,
            silencieuse=False,
            abstention=False,
            appels=1,
            activite=tuple(sorted(activite.items())),
        )

    return executer


def test_tous_les_bras_voient_le_meme_plan_de_missions() -> None:
    """L'appariement est la condition de validite : memes taches, memes graines."""
    executer, appels = _executeur_truque()
    rapport = mesurer(executer, taches=3, graines=2, leviers=["preuve", "porte"])
    plan = [(t, g) for t in range(3) for g in range(2)]
    assert rapport.n_missions == 6
    assert len(appels) == 6 * 3, "un bras manque des missions"
    assert [a[:2] for a in appels[:6]] == plan
    assert [a[:2] for a in appels[6:12]] == plan
    assert [a[:2] for a in appels[12:]] == plan
    # Le premier passage est celui du moteur complet, sans aucun levier neutralise.
    assert all(a[2] == () for a in appels[:6])


def test_un_mensonge_a_l_ablation_est_une_preuve_d_existence() -> None:
    executer, _ = _executeur_truque()
    rapport = mesurer(executer, taches=3, graines=2, leviers=["preuve", "porte"])
    preuve = next(c for c in rapport.leviers if c.nom == "preuve")
    assert preuve.silencieuses_avec == 0
    assert preuve.silencieuses_sans == 3
    assert preuve.verdict.startswith("PREUVE"), preuve.verdict
    porte = next(c for c in rapport.leviers if c.nom == "porte")
    assert porte.b == 0 and porte.c == 0
    assert porte.verdict == "NON DISTINGUABLE"


def test_zero_dissociation_ne_dit_jamais_inutile() -> None:
    """Le mot interdit. Un echantillon trop petit n'autorise pas a supprimer une brique."""
    executer, _ = _executeur_truque()
    rapport = mesurer(executer, taches=2, graines=1, leviers=["porte"])
    texte = formater(rapport)
    assert "NON DISTINGUABLE" in texte
    assert "inutile" not in texte.replace("n'est pas un levier inutile", "")
    assert "l'absence de preuve n'est pas la preuve de l'absence" in texte
    assert "il faudrait" in texte, "un non-distingue sans budget de mesure laisse sans prise"
    assert rapport.leviers[0].verdict == "NON DISTINGUABLE"
    assert rapport.leviers[0].ic_bas == 0.0 and rapport.leviers[0].ic_haut == 0.0


def test_le_rapport_se_lit_par_une_machine() -> None:
    executer, _ = _executeur_truque()
    rapport = mesurer(executer, taches=2, graines=2, leviers=["preuve", "red-team"])
    donnees = rapport.en_dict()
    assert donnees["n_missions"] == 4
    assert len(donnees["leviers"]) == 2
    assert donnees["complet"]["silencieuses"] == 0
    for levier_dict in donnees["leviers"]:
        assert levier_dict["nom"] in {"preuve", "red-team"}
        assert len(levier_dict["ic95_points"]) == 2
        assert levier_dict["verdict"]


def test_un_nom_de_levier_inconnu_leve_avant_de_mesurer() -> None:
    """Un nom faux doit lever AVANT la premiere mission : sinon on paie pour rien."""
    appels: list[str] = []

    def executer(indice: int, graine: int, ablations: tuple[str, ...]) -> Issue:
        appels.append("tourne")
        return Issue(juste=True, livree=True, reservee=False, silencieuse=False,
                     abstention=False, appels=1)

    with pytest.raises(KeyError):
        mesurer(executer, taches=1, graines=1, leviers=["pas-un-levier"])
    assert appels == []


def test_le_cout_d_un_retrait_qui_ne_ment_pas_est_ecrit() -> None:
    """Le cas mesure : la preuve retiree coute des REFUS, pas des mensonges.

    Les autres briques retiennent alors la livraison. Ce n'est pas « inutile » — c'est une
    redondance, et le rapport doit le dire avec ces mots, pas avec une conclusion
    triomphale qu'aucune donnee ne porte.
    """
    executer, _ = _executeur_truque()
    rapport = mesurer(executer, taches=3, graines=2, leviers=["preuve"])
    texte = formater(rapport)
    assert "d'autres briques ont retenu la livraison" in texte
    assert rapport.leviers[0].refus_supplementaires == 3


# --------------------------------------------------------------------------- #
# 4. Les deux metriques : juste ET livrable
# --------------------------------------------------------------------------- #


def _executeur_livraison(effet: str):
    """Un executeur ou le levier ne change PAS la justesse, seulement la livraison.

    C'est le cas mesure sur ce depot : retirer le red-team ou le consensus ne rend pas le
    moteur faux, il l'empeche de livrer SANS RESERVE. Un rapport qui ne regarde que la
    justesse declare alors ces briques « non distinguees » alors qu'elles decident de
    l'utilite du resultat.

      * `propre` : le bras prive de la brique ne livre plus sans reserve ;
      * `cout`   : le bras prive de la brique livre MIEUX que le moteur complet.
    """

    def executer(indice: int, graine: int, ablations: tuple[str, ...]) -> Issue:
        if not ablations:
            livree = effet != "cout"        # le moteur complet
        else:
            livree = effet == "cout"        # le bras prive de la brique
        return Issue(
            juste=True,
            livree=livree,
            reservee=not livree,
            silencieuse=False,
            abstention=False,
            appels=3,
        )

    return executer


def test_retirer_une_brique_qui_rend_le_resultat_LIVRABLE_se_voit() -> None:
    """La justesse ne bouge pas, la livraison propre s'effondre : c'est une preuve."""
    executer = _executeur_livraison("propre")
    rapport = mesurer(executer, taches=4, graines=2, leviers=["red-team"])
    levier_ = rapport.leviers[0]
    assert levier_.justes_avec == levier_.justes_sans == 8
    assert levier_.b == 0 and levier_.c == 0, "aucune difference de justesse"
    assert levier_.b_propre == 8 and levier_.c_propre == 0
    assert levier_.p_propre <= 0.05
    assert levier_.verdict == "PREUVE (livraison propre)", levier_.verdict
    texte = formater(rapport)
    assert "livraisons sans reserve : 8 perdue(s) contre 0 gagnee(s)" in texte


def test_un_levier_dont_le_retrait_AMELIORE_est_declare_comme_un_cout() -> None:
    """Le sens inverse doit etre dit, pas etouffe : c'est une question posee au levier."""
    executer = _executeur_livraison("cout")
    rapport = mesurer(executer, taches=4, graines=2, leviers=["mutation"])
    levier_ = rapport.leviers[0]
    assert levier_.livraisons_propres_perdues < 0
    assert levier_.verdict == "COUT MESURE", levier_.verdict
    assert len(rapport.couts) == 1 and rapport.couts[0].nom == "mutation"
    texte = formater(rapport)
    assert "a justifier, ou a interroger" in texte


# --------------------------------------------------------------------------- #
# Le progres : une mesure longue qui ne dit rien est indistinguable d'un blocage
# --------------------------------------------------------------------------- #


def test_l_ablation_SIGNALE_son_avancement_a_chaque_mission() -> None:
    """`avancer` est appele une fois par mission, et le total annonce est le vrai.

    Mesure a l'origine : `jio ablation` tourne plusieurs minutes sur une machine a deux coeurs
    en n'affichant RIEN — ni progression, ni duree, ni estimation. Une commande muette pendant
    plusieurs minutes est indistinguable d'une commande bloquee, et le seul recours est de
    l'interrompre : c'est-a-dire de ne jamais obtenir la mesure.

    Le total est verifie ICI, et pas seulement le nombre d'appels : un total faux rendrait
    l'estimation de temps fausse, et une estimation fausse est pire que pas d'estimation — elle
    fait interrompre une mesure qui allait finir.
    """
    executer, _appels = _executeur_truque()
    vus: list[str] = []
    rapport = mesurer(executer, taches=3, graines=2, leviers=["preuve", "red-team"],
                      avancer=vus.append)

    missions_par_bras = 3 * 2
    assert len(vus) == missions_par_bras * 3, "un signal par mission, bras complet compris"
    assert vus[0] == f"complet 1/{len(vus)}"
    assert vus[-1].endswith(f"{len(vus)}/{len(vus)}")
    assert any(libelle.startswith("sans preuve") for libelle in vus)
    assert any(libelle.startswith("sans red-team") for libelle in vus)
    # Le rapport lui-meme ne depend pas du signalement : c'est un canal, pas un calcul.
    sans_signal = mesurer(_executeur_truque()[0], taches=3, graines=2,
                          leviers=["preuve", "red-team"])
    assert sans_signal.prouves == rapport.prouves
    assert len(sans_signal.leviers) == len(rapport.leviers)


def test_sans_callback_l_ablation_ne_LEVE_pas() -> None:
    """Le signalement est optionnel : un appelant qui n'en veut pas n'a rien a fournir.

    C'est l'autre bord, et il protege l'API : `mesurer` est appele par des tests, par la CLI et
    par d'anciens scripts. Rendre le parametre obligatoire aurait casse les trois sans rien
    apporter a la mesure.
    """
    rapport = mesurer(_executeur_truque()[0], taches=2, graines=1, leviers=["preuve"])
    assert rapport.leviers


# --------------------------------------------------------------------------- #
# 5. L'activite : « le banc ne l'exerce pas » n'est pas « la brique ne sert a rien »
# --------------------------------------------------------------------------- #


def test_un_compteur_de_volume_n_est_pas_de_l_activite() -> None:
    """Sans ce filtre, les douze leviers paraissent actifs et l'instrument se tait en parlant.

    Mesure a l'origine : `usage:events` bougeait pour TOUTES les ablations (142 -> 104),
    comme il bougerait pour n'importe quel changement de chemin de code.
    """
    empreinte = {"temoins": 4, "temoins_ok": 3, "votes": 5, "usage:events": 142, "sujet_caracteres": 630}
    assert _activite_de_sens(empreinte) == (("temoins", 4), ("temoins_ok", 3), ("votes", 5))
    # Le volume seul ne compte pas comme un ecart de sens.
    assert _ecarts({"usage:events": 1}, {"usage:events": 2}) == (("usage:events", 1, 2),)
    assert _activite_de_sens({"usage:events": 1}) == _activite_de_sens({"usage:events": 2})


def test_les_ecarts_de_sens_passent_avant_les_compteurs_de_volume() -> None:
    """L'apercu du rapport doit parler du travail, pas du trafic."""
    ecarts = _ecarts({"usage:events": 900, "constat:mutation": 1}, {"usage:events": 10})
    assert [cle for cle, _, _ in ecarts][0] == "constat:mutation"


def test_activite_identique_dit_que_le_banc_n_exerce_pas_la_brique() -> None:
    rapport = mesurer(
        _executeur_avec_activite(actif=False), taches=2, graines=2, leviers=["porte"]
    )
    porte = rapport.leviers[0]
    assert porte.missions_activite_differente == 0
    assert porte.observations_avec > 0, "l'instrument doit avoir compte quelque chose"
    texte = formater(rapport)
    assert "ACTIVITE IDENTIQUE" in texte
    assert "Le banc, tel qu'il est, ne la met donc pas a l'epreuve" in texte
    # Le conseil de l'ancien rapport serait une fausse piste payee en heures.
    assert "aucune puissance d'echantillon ne conclura" in texte
    assert "il en faudrait au moins" not in texte.split("VERDICTS")[1]


def test_du_volume_qui_bouge_ne_suffit_pas_a_declarer_la_brique_active() -> None:
    rapport = mesurer(
        _executeur_avec_activite(actif=False, identique=True),
        taches=2,
        graines=2,
        leviers=["porte"],
    )
    porte = rapport.leviers[0]
    assert porte.missions_activite_differente == 0
    assert "compteurs de VOLUME bougent" in formater(rapport)


def test_une_brique_qui_agit_sans_changer_le_verdict_est_dite_agissante() -> None:
    rapport = mesurer(
        _executeur_avec_activite(actif=True), taches=2, graines=2, leviers=["porte"]
    )
    porte = rapport.leviers[0]
    assert porte.missions_activite_differente == 4
    ecarts = {cle: (avec, sans) for cle, avec, sans in porte.ecarts_activite}
    # Les comptes sont des TOTAUX de bras : 4 missions x 4 temoins contre 4 x 3.
    assert ecarts["temoins"] == (16, 12)
    texte = formater(rapport)
    assert "la brique AGIT sur 4/4 mission(s)" in texte
    assert "REDONDANTE" in texte, "aucune dissociation : le mot doit rester mesure"
    # Et l'instrument publie les nombres, pas seulement la phrase.
    donnees = rapport.en_dict()["leviers"][0]
    assert donnees["missions_activite_differente"] == 4
    assert donnees["observations_avec"] == donnees["observations_sans"] + 4
    assert {"cle": "temoins", "complet": 16, "sans": 12} in donnees["ecarts_activite"]


def test_l_instrument_se_tait_quand_il_n_a_rien_compte() -> None:
    """« Je n'ai pas regarde » ne s'ecrit pas comme « il ne s'est rien passe »."""
    vide = Comparaison(
        nom="porte", quoi="q", sans="s", n=1, justes_avec=1, justes_sans=1, livrees_avec=1,
        livrees_sans=1, reservees_avec=0, reservees_sans=0, silencieuses_avec=0,
        silencieuses_sans=0, abstentions_avec=0, abstentions_sans=0, appels_avec=1.0,
        appels_sans=1.0, b=0, c=0, p_exact=1.0, ic_bas=0.0, ic_haut=0.0, b_propre=0,
        c_propre=0, p_propre=1.0,
    )
    assert _phrase_activite(vide) == ""


def test_les_ecarts_qui_vont_contre_la_brique_sont_nommes() -> None:
    """Une brique qui degrade la ou elle agit doit etre signalee, pas defendue."""
    degrade = Comparaison(
        nom="x", quoi="q", sans="s", n=10, justes_avec=8, justes_sans=9, livrees_avec=8,
        livrees_sans=9, reservees_avec=0, reservees_sans=0, silencieuses_avec=0,
        silencieuses_sans=0, abstentions_avec=0, abstentions_sans=0, appels_avec=1.0,
        appels_sans=1.0, b=0, c=3, p_exact=0.25, ic_bas=0.0, ic_haut=0.0, b_propre=0,
        c_propre=2, p_propre=0.5,
        missions_activite_differente=3, observations_avec=20, observations_sans=22,
        ecarts_activite=(("temoins", 20, 22),),
    )
    phrase = _phrase_activite(degrade)
    assert "CONTRE elle" in phrase
    assert "5 contre 0" in phrase


# --------------------------------------------------------------------------- #
# 6. Le banc branche ce que le chemin reel fait tourner (plus de leviers-fantomes)
# --------------------------------------------------------------------------- #


def test_le_banc_d_ablation_branche_l_apprentissage(capsys) -> None:
    """Retirer memoire/bibliotheque/routeur ne doit pas etre l'ablation d'un FANTOME.

    Incident mesure : `jio run` branche la memoire des echecs, la bibliotheque de temoins
    et le routeur de confiance (`_attach_learning`), mais le banc ne le faisait pas — les
    trois leviers retiraient None et l'instrument d'activite disait « le banc ne l'exerce
    pas » sur trois briques que le chemin REEL charge, lui. Verrou : sur une mesure reelle
    (2 missions, levier routeur), le retrait doit changer un observable de sens au moins
    une fois — le routeur arme un budget journalise, donc `integrite_etapes` differe des
    la premiere mission. Si ce test devient rouge avec `missions_activite_differente == 0`,
    quelqu'un a debranche `_attach_learning` du banc.
    """
    import argparse as _argparse

    from jio.cli import cmd_ablation

    args = _argparse.Namespace(
        missions=2, levers="routeur", skill=0.35, rounds=4, fidelite=1.0,
        sans_oracle=False, json=True,
    )
    code = cmd_ablation(args)
    assert code in (0, 1), "une mesure doit se terminer, meme avec un defaut affiche"
    sortie = capsys.readouterr().out
    rapport = json.loads(sortie[sortie.index("{"):])
    routeur = rapport["leviers"][0]
    assert routeur["nom"] == "routeur"
    assert routeur["missions_activite_differente"] > 0, (
        "le levier routeur ressort fantome : le banc ne branche plus l'apprentissage"
    )
    assert routeur["ecarts_activite"], "aucun ecart : meme cause que ci-dessus"


def test_le_banc_nettoie_son_etat_d_apprentissage() -> None:
    """Un banc qui laisse des etats derriere lui contamine la mesure SUIVANTE."""
    import glob
    import os
    import tempfile

    avant = set(glob.glob(os.path.join(tempfile.gettempdir(), "jio-ablation-etat-*")))
    import argparse as _argparse

    from jio.cli import cmd_ablation

    cmd_ablation(_argparse.Namespace(
        missions=1, levers="memoire", skill=0.35, rounds=4, fidelite=1.0,
        sans_oracle=False, json=True,
    ))
    apres = set(glob.glob(os.path.join(tempfile.gettempdir(), "jio-ablation-etat-*")))
    assert apres - avant == set(), "le banc a laisse un dossier d'etat derriere lui"


def test_la_tache_a_spec_partielle_exerce_le_differentiel(capsys) -> None:
    """`differentiel` ne peut pas se montrer sur des specifications TOTALES.

    Mesure : sur les cinq taches archives, le levier ressort muet sur TOUT regime (defaut,
    sans oracle, competence 0,05 a 0,9) — deux implementations correctes y coincident sur
    toute entree. La tache `mean_partial` ajoute ce qui manque : l'oracle se tait sur la
    liste vide, deux implementations LEGITIMES divergent (`ZeroDivisionError` contre
    `0.0`), le differentiel les sonde et l'aveu devient un constat nomme. Verrou : retirer
    la brique doit faire disparaitre ce constat, au moins une fois sur deux missions
    (graines fixes — la mesure est deterministe).
    """
    import argparse as _argparse

    from jio.cli import cmd_ablation

    cmd_ablation(_argparse.Namespace(
        missions=2, levers="differentiel", taches="mean_partial", skill=0.7, rounds=4,
        fidelite=1.0, sans_oracle=False, json=True,
    ))
    sortie = capsys.readouterr().out
    rapport = json.loads(sortie[sortie.index("{"):])
    differentiel = rapport["leviers"][0]
    assert differentiel["nom"] == "differentiel"
    constats = {e["cle"]: (e["complet"], e["sans"]) for e in differentiel["ecarts_activite"]}
    assert constats.get("constat:divergence", (0, 0))[0] > 0, (
        "la tache partielle ne produit plus de constat de divergence : soit la tache a "
        "ete serree (la spec parle maintenant de la liste vide), soit le differentiel a "
        "ete debranche"
    )
    assert differentiel["missions_activite_differente"] > 0


def test_une_tache_inconnue_est_refusee_avec_un_nom(capsys) -> None:
    """Une faute de frappe dans --taches ne doit pas mesurer le banc VIDE en silence."""
    import argparse as _argparse

    from jio.cli import cmd_ablation

    code = cmd_ablation(_argparse.Namespace(
        missions=2, levers="differentiel", taches="mean_partiel", skill=0.7, rounds=4,
        fidelite=1.0, sans_oracle=False, json=True,
    ))
    sortie = capsys.readouterr()
    assert code == 2, "une tache inconnue est une erreur d'appel, pas une mesure vide"
    assert "mean_partiel" in sortie.err


# --------------------------------------------------------------------------- #
# 7. Les observables de decision : composition des votes et filtre de decision
# --------------------------------------------------------------------------- #


def test_la_composition_des_votes_et_la_sentinelle_entrent_dans_l_empreinte() -> None:
    """« 5 votes » ne dit pas si le panel a statue a l'unanime ou a une voix.

    La sentinelle `avis_en_phase` est l'observable du CONSENSUS : la decision retenue
    suit-elle le vote majoritaire ? Sans elle, le passage du quorum au « premier avis
    decide » est invisible — les voix brutes ne bougent pas, seule la coherence
    voix -> decision bouge.
    """
    from types import SimpleNamespace

    from jio.cli import _empreinte_activite

    rapport_unanime = SimpleNamespace(
        witnesses=(), findings=(), votes=[
            SimpleNamespace(decision=Verdict.PASS), SimpleNamespace(decision=Verdict.PASS),
        ],
        integrity=None, usage={}, subject="", status=MissionStatus.DELIVERED,
    )
    empreinte = dict(_empreinte_activite(rapport_unanime))
    assert empreinte["votes_pass"] == 2 and empreinte["votes_fail"] == 0
    assert empreinte["avis_en_phase"] == 1, "majorite pass, livre : en phase"

    rapport_contredit = SimpleNamespace(
        witnesses=(), findings=(), votes=[
            SimpleNamespace(decision=Verdict.PASS), SimpleNamespace(decision=Verdict.FAIL),
            SimpleNamespace(decision=Verdict.FAIL),
        ],
        integrity=None, usage={}, subject="", status=MissionStatus.DELIVERED,
    )
    empreinte = dict(_empreinte_activite(rapport_contredit))
    assert empreinte["votes_pass"] == 1 and empreinte["votes_fail"] == 2
    assert empreinte["avis_en_phase"] == 0, "majorite fail, livre : la decision contredit"


def test_un_filtre_de_decision_n_est_pas_un_banc_muet() -> None:
    """Mesure reelle (porte, regime correle) : la brique n'agit sur AUCUN observable de
    mission mais deplace les livraisons. L'ancienne lecture disait « le banc ne l'exerce
    pas, aucune puissance d'echantillon ne conclura » — faux : elargir EST ce qui peut
    trancher, chaque dissociation rapproche du seuil."""
    filtre = Comparaison(
        nom="porte", quoi="q", sans="s", n=10, justes_avec=10, justes_sans=10,
        livrees_avec=3, livrees_sans=4, reservees_avec=3, reservees_sans=2,
        silencieuses_avec=0, silencieuses_sans=0, abstentions_avec=0, abstentions_sans=0,
        appels_avec=7.0, appels_sans=7.0, b=0, c=1, p_exact=1.0, ic_bas=0.0, ic_haut=0.0,
        b_propre=0, c_propre=1, p_propre=1.0,
        missions_activite_differente=0, observations_avec=500, observations_sans=500,
        ecarts_activite=(),
    )
    phrase = _phrase_activite(filtre)
    assert "FILTRE DE DECISION" in phrase
    assert "0 contre 1" in phrase
    assert "--missions" in phrase, "elargir est exactement ce qui peut trancher ici"
    rapport = RapportAblation(complet=Bras(nom="complet"), leviers=[filtre],
                              n_missions=10, taches=5, graines=2)
    texte = formater(rapport)
    assert "aucune puissance d'echantillon ne conclura" not in texte


# --------------------------------------------------------------------------- #
# 8. La calibration de la porte : la borne conforme repond au cout mesure
# --------------------------------------------------------------------------- #


def test_les_points_de_calibration_mesurent_les_candidats() -> None:
    """Chaque candidat du banc devient un point (score = fraction de checks, verite
    connue). La solution correcte fait 1,0 ; un distracteur qui echoue fait moins."""
    from jio.bench.tasks import TASKS
    from jio.cli import _points_de_calibration

    points = _points_de_calibration(list(TASKS))
    parfaits = [p for p in points if p.score == 1.0]
    assert all(p.correct for p in parfaits), "score 1,0 sans verite : calibration mentie"
    assert any(not p.correct and p.score < 1.0 for p in points), "aucun distracteur echoue"
    # Deterministe : memes taches, memes points.
    assert _points_de_calibration(list(TASKS)) == points


def test_la_borne_conforme_refuse_un_seuil_plus_bas_sur_ces_points() -> None:
    """MESURE qui repond au cout de la porte : avec 20 points du banc (5 corrects), la
    borne (erreurs+1)/(acceptes+1) <= alpha n'autorise AUCUN tau < 1 — (0+1)/(5+1) = 0,167
    > 0,05. Calibrer rend donc la porte PLUS stricte (0,90 -> 1,00) : le cout mesure en
    corrèle est le prix de la garantie, pas un défaut de réglage."""
    from jio.cli import _points_de_calibration
    from jio.gate.conformal import ConformalGate

    porte = ConformalGate(alpha=0.05)
    porte.observe_many(_points_de_calibration(list(TASKS)))
    assert porte.calibrated, "20 points doivent suffire a declencher la calibration"
    assert porte.tau() == 1.0, (
        "la borne a change : la lecture « le prix du fail-closed » doit etre re-mesuree"
    )


def test_le_regime_calibre_est_annonce_dans_l_en_tete(capsys) -> None:
    """Un chiffre sans son regime ne se compare pas : --calibree doit ecrire le tau
    mesure et le nombre de points, AVANT le tableau."""
    import argparse as _argparse

    from jio.cli import cmd_ablation

    code = cmd_ablation(_argparse.Namespace(
        missions=1, levers="porte", taches="", skill=0.35, rounds=2, fidelite=1.0,
        sans_oracle=False, correlee=True, calibree=True, json=True,
    ))
    sortie = capsys.readouterr().out
    assert code in (0, 1)
    assert "porte CALIBREE" in sortie
    assert "tau = " in sortie and "20 points" in sortie
