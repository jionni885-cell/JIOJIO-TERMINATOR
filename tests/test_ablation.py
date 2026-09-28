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

from jio.bench.ablation import (
    LEVIERS,
    ConsensusPremierAvis,
    Issue,
    PanelSansRedTeam,
    PorteOuverte,
    ProverAveugle,
    appliquer,
    dissociations_requises,
    formater,
    levier,
    mcnemar_exact,
    mesurer,
)
from jio.audit.panel import DEFAULT_PERSONAS
from jio.core.types import Verdict, Vote

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
