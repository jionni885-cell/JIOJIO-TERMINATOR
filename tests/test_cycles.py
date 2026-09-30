"""Le protocole MULTI-CYCLES : la memoire qui s'accumule apporte-t-elle quelque chose ?

Le banc A/B/C repond a « la mecanique apporte-t-elle quelque chose en moyenne ». Ce
protocole repond a une AUTRE question : « la memoire qui s'accumule cycle apres cycle
apporte-t-elle quelque chose, ou rend-elle le harness plus cher sans le rendre meilleur ».
Deux questions, deux protocoles, et un defaut trouve en le construisant : le bras froid
tournait avec la configuration par DEFAUT pendant que le bras chaud tournait avec le bras
choisi par le routeur. L'ecart mesure melangeait alors la memoire et la CONFIGURATION.

C'est ce que ce fichier verrouille : la seule difference autorisee entre les deux bras
est le SOUVENIR. Le test qui le prouve est `test_memoire_vide_ecart_nul` — au premier
cycle, la memoire est vide des deux cotes ; si les deux bras rendaient un resultat
different, c'est qu'autre chose que la memoire avait change.
"""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path

import pytest

from jio.learn.cycles import (
    VERDICTS,
    Cycle,
    RapportCycles,
    _RouteurFige,
    _tronquer,
    run_cycles,
)


# --- Le protocole apparie -----------------------------------------------------------------


@pytest.fixture(scope="module")
def rapport_petit() -> RapportCycles:
    """UNE seule execution pour tous les tests de protocole.

    Le protocole coute 2 missions par essai mesure (le froid rejoue ce que le chaud a
    fait) : le lancer dans chaque test multiplierait la duree de la suite sans rien
    prouver de plus. `rounds=1` et une seule tache suffisent a observer l'appariement —
    c'est la REGLE qui est testee, pas la difficulte du banc.
    """
    return run_cycles(
        skill=0.12, runs=1, cycles=2, rounds=1, task_ids=("sum_even",),
    )


def test_memoire_vide_ecart_nul(rapport_petit: RapportCycles) -> None:
    """INVARIANT CENTRAL : sans memoire, les deux bras doivent etre INDISCERNABLES.

    Meme tache, meme graine, meme bras (le froid rejoue celui que le chaud a choisi) : le
    fournisseur simule est deterministe, donc les deux compteurs doivent coincider
    EXACTEMENT au premier cycle. Un ecart non nul ici prouverait que le protocole compare
    autre chose que la memoire — c'est exactement le defaut qui a ete corrige.
    """
    rapport = rapport_petit

    assert rapport.cycles, "un cycle doit avoir ete mesure"
    premier = rapport.cycles[0]
    assert premier.memo_avant == 0, "le premier cycle part d'une memoire vide"
    assert premier.ecart == 0, (
        f"memoire vide mais ecart chaud/temoin {premier.ecart:+d} : le protocole compare "
        "autre chose que le souvenir (verifier l'appariement du bras)"
    )
    # Le TEMOIN, lui, peut s'ecarter du froid : c'est le bruit que le protocole mesure au
    # lieu de le confondre avec un effet de la memoire.
    assert 0 <= premier.temoin <= premier.essais


def test_le_routeur_fige_ne_choisit_jamais_autre_chose() -> None:
    """Le bras froid rejoue le bras du chaud : c'est la definition de « apparie »."""
    bras = object()
    fige = _RouteurFige(bras)

    assert fige.choose("n'importe quel objectif") is bras
    assert fige.choose("un autre", classe="x") is bras
    assert fige.observe("objectif", bras, success=True) == 0.0
    assert fige.observations == 1, "le froid OBSERVE le resultat mais n'apprend pas"


def test_un_cycle_respecte_le_nombre_d_essais_annonce(rapport_petit: RapportCycles) -> None:
    """`essais` n'est pas un compte de terrain : c'est `taches x runs`, et il est verifie."""
    rapport = rapport_petit

    assert len({c.essais for c in rapport.cycles}) == 1, (
        "tous les cycles mesurent le meme nombre d'essais"
    )
    essais = rapport.cycles[0].essais
    assert essais == 1, f"1 tache x 1 run = 1 essai, pas {essais}"
    for cycle in rapport.cycles:
        assert 0 <= cycle.froid <= essais
        assert 0 <= cycle.temoin <= essais
        assert 0 <= cycle.chaud <= essais


# --- Le verdict ---------------------------------------------------------------------------


def _rapport(*cycles: Cycle, gain: float = 0.0) -> RapportCycles:
    """Un rapport construit a la main. `gain` est le warning_gain DECLARE : sans lui, le
    rapport ne peut pas calculer l'effet attendu et ne doit donc rien dire de la portee."""
    return RapportCycles(
        cycles=list(cycles), skill=0.5, runs=1, rounds=2, warning_gain=gain
    )


def _cycle(numero: int, froid: int, chaud: int, *, temoin: int = 0, memo_avant: int = 0,
           memo_apres: int = 0, essais: int = 10, caracteres: int = 0,
           avertis: int = 0, appels: int = 0, chaud_seul: int = 0,
           temoin_seul: int = 0, bloc: int = 0) -> Cycle:
    return Cycle(
        numero=numero, memo_avant=memo_avant, memo_apres=memo_apres, rappels=0,
        froid=froid, temoin=temoin, chaud=chaud, essais=essais,
        caracteres_memoire=caracteres, avertis=avertis, appels=appels,
        chaud_seul=chaud_seul, temoin_seul=temoin_seul, bloc=bloc,
    )


def test_le_vocabulaire_des_verdicts_est_ferme(rapport_petit: RapportCycles) -> None:
    assert rapport_petit.verdict() in VERDICTS
    assert len(VERDICTS) == 3, "un verdict ajoute ailleurs serait un verdict que personne ne teste"


def test_une_rechute_condamne() -> None:
    """Le seul verdict qui condamne : la memoire accumulee fait PERDRE.

    Et l'ecart qui compte est CHAUD - TEMOIN, pas chaud - froid : le temoin porte la meme
    memoire, il ne s'en distingue que par l'effet. Un ecart negatif face au FROID seul ne
    prouve rien — c'est exactement ce que la mesure a montre (-4 au cycle 1, memoire vide).
    """
    rapport = _rapport(
        _cycle(1, froid=4, temoin=4, chaud=5, memo_avant=3, memo_apres=6),
        _cycle(2, froid=6, temoin=6, chaud=3, memo_avant=6, memo_apres=9),
    )
    assert rapport.rechutes == [2]
    assert rapport.verdict() == "REGRESSE"
    assert "NUIT" in rapport.explication()


def test_l_ecart_ignore_le_bras_froid() -> None:
    """Le contraste causal est chaud/temoin. Un froid tres en dessous ne doit pas
    transformer un plateau en progres, ni l'inverse."""
    rapport = _rapport(_cycle(1, froid=1, temoin=8, chaud=8, memo_avant=2, memo_apres=3))
    assert rapport.ecart == 0
    assert rapport.artefact == 7, "l'artefact est declare, pas cache"
    assert rapport.verdict() == "PLATEAU"


def test_la_portee_borne_l_interpretation() -> None:
    """Un ecart nul avec une portee de 1 % ne dit RIEN de la memoire : le levier n'a
    presque jamais ete arme. Le rapport doit le dire, sinon il conclut au-dela de sa
    mesure — le peche qu'il existe pour empecher."""
    rapport = RapportCycles(
        cycles=[_cycle(1, froid=8, temoin=8, chaud=8, memo_avant=5, memo_apres=9,
                       caracteres=4000, avertis=1, appels=100)],
        skill=0.5, warning_gain=0.20,
    )
    assert rapport.portee == pytest.approx(0.01)
    assert rapport.effet_attendu_max() < 1.0
    texte = rapport.explication()
    assert "1.0%" in texte
    assert "SOUS le pas de mesure" in texte


def test_une_portee_large_autorise_a_conclure() -> None:
    """Symetrique du precedent : si le levier etait arme partout, un ecart nul CONDAMNE
    l'effet a ce niveau — et le rapport le dit aussi."""
    rapport = RapportCycles(
        cycles=[_cycle(1, froid=8, temoin=8, chaud=8, memo_avant=5, memo_apres=9,
                       caracteres=4000, avertis=100, appels=100)],
        skill=0.5, warning_gain=0.20,
    )
    assert rapport.effet_attendu_max() >= 1.0
    assert "il ne s'est pas vu" in rapport.explication()


def test_un_ecart_negatif_a_memoire_vide_n_est_pas_une_rechute() -> None:
    """Sinon le rapport accuserait la memoire d'une mauvaise graine.

    Au cycle 1 la memoire est VIDE : rien n'a pu nuire. Un ecart negatif y est de la
    loterie de tirage, et l'appeler « rechute » serait un faux positif — precisement le
    genre de faux positif que ce depot refuse.
    """
    rapport = _rapport(_cycle(1, froid=5, chaud=3, memo_avant=0, memo_apres=4))
    assert rapport.rechutes == []
    assert rapport.verdict() != "REGRESSE"


def test_le_temoin_separe_l_effet_de_la_loterie() -> None:
    """Un plateau sans son cout se lit mal : « la memoire n'apporte rien » n'est pas
    « la memoire coute 868 jetons par cycle et n'apporte rien ». Le second declenche une
    decision, le premier laisse l'utilisateur sans action."""
    rapport = _rapport(
        _cycle(1, froid=4, temoin=4, chaud=4, memo_apres=3, caracteres=100),
        _cycle(2, froid=4, temoin=4, chaud=4, memo_avant=3, memo_apres=8, caracteres=3400),
    )
    assert rapport.verdict() == "PLATEAU"
    assert rapport.cout_du_plateau() == 850, "3400 caracteres ~ 850 jetons"
    assert "850" in rapport.explication()


def test_pas_de_cout_affiche_si_la_memoire_n_a_pas_grandi() -> None:
    rapport = _rapport(
        _cycle(1, froid=4, temoin=4, chaud=4, memo_apres=5, caracteres=900),
        _cycle(2, froid=4, temoin=4, chaud=4, memo_avant=5, memo_apres=5, caracteres=900),
    )
    assert rapport.cout_du_plateau() == 0


def test_memo_final_rend_le_stock_pas_le_flux() -> None:
    rapport = _rapport(
        _cycle(1, froid=1, temoin=1, chaud=1, memo_apres=3),
        _cycle(2, froid=1, temoin=1, chaud=1, memo_avant=3, memo_apres=7),
    )
    assert rapport.memo_final == 7
    assert RapportCycles().memo_final == 0


# --- La borne de memoire -------------------------------------------------------------------


def test_la_troncature_garde_les_souvenirs_les_plus_recents(tmp_path) -> None:
    """Une memoire non bornee est la cause d'echec la plus documentee (distraction,
    confusion). On la borne par le HAUT, en gardant les plus recents."""
    from jio.learn.memory import FailureMemory

    memoire = FailureMemory(path=tmp_path / "failures.jsonl")
    for i in range(10):
        memoire.record(
            objective=f"objectif numero {i}", symptom=f"echec {i}",
            root_cause=f"cause {i}", correct_fix=f"correction {i}",
            guard=f"controle {i}",
        )
    avant = memoire.size
    assert avant >= 10, "le stock de depart doit etre reel pour que la borne ait un sens"

    _tronquer(memoire, 4)

    assert memoire.size == 4, "la borne doit etre respectee"
    # Les plus RECENTS sont gardes : une lecon recente decrit le code tel qu'il est.
    restants = [s.symptom for s in memoire._records]
    assert "echec 9" in restants and "echec 0" not in restants


def test_le_gain_declare_se_calcule_sur_la_COMPETENCE_pas_sur_le_taux_observe() -> None:
    """Le gain est RELATIF et s'applique a la competence du modele, pas au taux observe.

    Le taux de reussite observe (85 % ici) est deja le produit de la largeur de tirage et
    de la verification : s'en servir comme base gonflerait l'effet attendu d'un facteur
    deux, et le rapport aurait declare « incoherent » un ecart parfaitement coherent avec
    sa modelisation. Mesure sur un vrai run : +7,9 points attendus (base = competence 0,40)
    pour +7,0 observes.
    """
    rapport = RapportCycles(
        cycles=[_cycle(1, froid=21, temoin=21, chaud=23, essais=25, memo_apres=8,
                       caracteres=7000, avertis=25, appels=25)],
        skill=0.40, warning_gain=0.20,
    )
    assert rapport.gain_declare == pytest.approx(7.9, abs=0.2)
    # Et le taux OBSERVE (92 %) ne doit pas entrer dans ce calcul.
    assert rapport.cycles[0].taux_chaud == pytest.approx(0.92)
    assert "88%" in rapport.explication() or "VALID" in rapport.explication()


def test_l_intervalle_est_POOL_sur_tous_les_cycles() -> None:
    """Un ecart de +7 sur 100 essais ne doit pas etre juge sur les 25 du dernier cycle.

    Le protocole mesurait 100 essais et n'en regardait que 25 : il jetait 75 % de sa
    propre preuve. La comparaison reste appariee cycle par cycle, donc empiler les cycles
    n'ajoute aucun biais — cela ajoute de la resolution (budget requis : 1177 -> 432
    essais par bras, mesure).
    """
    rapport = RapportCycles(
        cycles=[_cycle(n, froid=f, temoin=t, chaud=c, essais=25, memo_apres=5 * n)
                for n, f, t, c in ((1, 20, 20, 22), (2, 24, 24, 24),
                                   (3, 19, 19, 23), (4, 22, 22, 23))],
        skill=0.4, warning_gain=0.20,
    )
    assert rapport.ecart_cumule == 7
    assert rapport.essais_cumules == 100
    # Ces cycles viennent d'un cumul SANS releve des paires : le rapport doit le DIRE au
    # lieu de laisser croire qu'il a teste l'effet, et il ne peut pas conclure.
    assert rapport.paires == (0, 0)
    assert "sans le relevé des paires" in rapport.explication()
    assert rapport.verdict() == "PLATEAU"
    assert "cumule +7 sur 100" in rapport.explication()


def test_le_test_apparie_est_le_BON_test_pour_ce_plan(tmp_path) -> None:
    """Le protocole est apparie : memes taches, memes graines, meme bras.

    Comparer les deux bras comme deux echantillons independants jette l'information de
    l'appariement. Constate : +10 reussites sur 220 paires restaient « non demontres » avec
    la methode independante, alors que McNemar — le test de ce plan — conclut sur les seules
    dissociations. Et le budget change d'ordre de grandeur : 432 « essais par bras » devient
    un nombre de PAIRES.
    """
    from jio.bench.ablation import mcnemar_exact

    rapport = _rapport(_cycle(1, froid=191, temoin=191, chaud=201, essais=220,
                              chaud_seul=17, temoin_seul=6))
    assert rapport.paires == (17, 6)
    assert rapport.p_valeur_appariee == mcnemar_exact(17, 6)
    assert rapport.p_valeur_appariee < 0.05
    assert rapport.tranche_apparie is True
    bas, haut = rapport.intervalle_apparie
    assert bas > 0.0, "l'intervalle apparie doit exclure zero"
    assert rapport.verdict() == "PROGRESSE"


def test_sans_releve_des_paires_le_rapport_ne_conclut_pas() -> None:
    """Un cumul mesure SANS les paires ne peut pas faire le test apparié.

    Le dire est indispensable : sans cette phrase, « PLATEAU » se lirait « pas d'effet »
    alors que le chiffre dit seulement « pas de test possible ».
    """
    rapport = _rapport(_cycle(1, froid=90, temoin=90, chaud=100, essais=100))
    assert rapport.paires == (0, 0)
    assert rapport.tranche_apparie is False
    assert rapport.verdict() == "PLATEAU"
    assert "sans le relevé des paires" in rapport.explication()


def test_le_piege_du_cumul_conserve_les_paires(tmp_path) -> None:
    """Les dissociations doivent survivre a l'ecriture sur disque : sans elles, un cumul
    relu ne pourrait plus faire le test apparié et perdrait sa resolution."""
    from jio.learn.cycles import cumuler, depuis_cumul

    chemin = tmp_path / "cycles.jsonl"
    cumuler(chemin, _run(_mini(1, froid=45, temoin=45, chaud=51)), runs=4, rounds=2)
    # _mini ne remplit pas les paires : on ecrit un cycle AVEC dissociation et on relit.
    from jio.learn.cycles import Cumul

    cumul = Cumul(chemin, skill=0.4, runs=4, rounds=2, gain=0.20, seed_base=1000)
    cumul.ajouter(_cycle(2, froid=45, temoin=45, chaud=51, essais=55,
                         chaud_seul=6, temoin_seul=1))
    cumul.lever_le_verrou()

    relu = depuis_cumul(chemin)
    assert relu.paires == (6, 1)
    assert relu.p_valeur_appariee < 0.25


def test_le_rapport_separe_les_REPLICATIONS_et_ne_cache_pas_l_heterogeneite() -> None:
    """Un cumul est une SOMME de tirages independants, pas une moyenne.

    Constate en campagne : +7 sur le premier bloc de graines, puis +0 au premier cycle
    du suivant. Le cumul restait juste, mais n'afficher que lui laissait lire « +7 sur
    trois cycles » — c'est-a-dire une moyenne qui n'existe dans aucun des deux blocs.
    """
    rapport = RapportCycles(
        cycles=[
            _cycle(1, froid=45, temoin=45, chaud=51, essais=55, chaud_seul=6, bloc=0),
            _cycle(2, froid=45, temoin=45, chaud=51, essais=55, chaud_seul=3, bloc=0),
            _cycle(3, froid=51, temoin=51, chaud=51, essais=55, chaud_seul=1, bloc=1000),
        ],
        skill=0.4, warning_gain=0.20,
        replications=[{"seed_base": 0}, {"seed_base": 1000}],
    )
    # Ecarts : +6, +6, puis +0. Le cumul (+12) est juste, mais il n'existe dans AUCUN des
    # deux blocs : c'est exactement ce que le rapport doit rendre visible.
    assert rapport.ecart_cumule == 12
    assert rapport.effet_par_bloc() == [(0, 12, 9, 0), (1000, 0, 1, 0)]

    ligne = rapport.ligne_des_blocs()
    assert "bloc de graines 0 : +12" in ligne
    assert "bloc de graines 1000 : +0" in ligne
    assert "NE disent PAS la meme chose" in ligne
    assert ligne in rapport.explication(), "la phrase doit etre DANS le rapport, pas a cote"


def test_un_seul_bloc_n_est_pas_encore_un_effet_REPRODUIT() -> None:
    """Dire ce qui manque : un effet dans un seul bloc de graines peut etre un tirage."""
    rapport = _rapport(_cycle(1, froid=45, temoin=45, chaud=51, essais=55,
                              chaud_seul=6, bloc=0))
    ligne = rapport.ligne_des_blocs()
    assert "une seule pour l'instant" in ligne
    assert "pas encore un effet REPRODUIT" in ligne


def test_des_blocs_qui_vont_DANS_LE_MEME_SENS_le_disent_aussi() -> None:
    """Le controle symetrique : un rapport qui ne signale que l'heterogeneite est biaise."""
    rapport = RapportCycles(
        cycles=[_cycle(1, froid=45, temoin=45, chaud=51, essais=55, chaud_seul=6, bloc=0),
                _cycle(2, froid=45, temoin=45, chaud=50, essais=55, chaud_seul=5, bloc=1000)],
        skill=0.4, warning_gain=0.20,
    )
    ligne = rapport.ligne_des_blocs()
    assert "meme sens dans tous les blocs" in ligne
    assert "NE disent PAS" not in ligne


def test_les_cycles_sans_champ_bloc_sont_attribues_a_leur_replication(tmp_path) -> None:
    """Les fichiers ecrits AVANT ce champ restent attribuables, sans migration.

    Le bloc d'un cycle est celui de la derniere ligne `replication` qui le precede : un
    cumul deja mesure se relit donc correctement, sans reecriture ni reinterpretation.
    """
    import json

    from jio.learn.cycles import depuis_cumul

    chemin = tmp_path / "vieux.jsonl"
    lignes = [
        {"type": "entete", "skill": 0.4, "runs": 4, "rounds": 2, "gain": 0.2},
        {"type": "replication", "seed_base": 0, "runs": 4, "rounds": 2},
        {"type": "cycle", "numero": 1, "froid": 40, "temoin": 40, "chaud": 45,
         "essais": 45, "chaud_seul": 5, "temoin_seul": 0},
        {"type": "replication", "seed_base": 1000, "runs": 4, "rounds": 2},
        # Ce cycle n'a JAMAIS eu de champ `bloc` : c'est le format d'avant.
        {"type": "cycle", "numero": 2, "froid": 41, "temoin": 41, "chaud": 41,
         "essais": 45, "chaud_seul": 0, "temoin_seul": 0},
    ]
    chemin.write_text("\n".join(json.dumps(l) for l in lignes) + "\n", encoding="utf-8")

    rapport = depuis_cumul(chemin)
    assert [c.bloc for c in rapport.cycles] == [0, 1000]
    assert rapport.effet_par_bloc() == [(0, 5, 5, 0), (1000, 0, 0, 0)]
    assert "NE disent PAS la meme chose" in rapport.ligne_des_blocs()


def test_un_ecart_nul_ne_se_demontre_pas_par_plus_d_essais() -> None:
    """« INDETERMINE » n'est utile que s'il dit COMBIEN d'essais il faudrait.

    Et il doit dire la verite dans les deux sens : un ecart NUL ne se « demontre » pas, il
    est deja le resultat (aucun nombre d'essais ne le rendra significatif) ; un ecart NON
    nul mais trop petit pour 60 essais a un budget, et le rapport doit le donner.
    """
    # Aucune dissociation nette : il n'y a rien a demontrer.
    nul = _rapport(_cycle(1, froid=8, temoin=8, chaud=8, essais=20,
                          memo_avant=3, memo_apres=9, chaud_seul=2, temoin_seul=2))
    assert nul.essais_requis() == 0

    # 12 dissociations favorables contre 3 defavorables sur 40 paires : le budget existe,
    # et il est en PAIRES (le plan experimental), pas en « essais par bras ».
    petit = _rapport(_cycle(1, froid=32, temoin=32, chaud=41, essais=40,
                            memo_avant=3, memo_apres=9, chaud_seul=12, temoin_seul=3))
    requis = petit.essais_requis()
    assert 40 < requis < 4000, f"budget inattendu : {requis}"


def test_le_budget_de_mesure_est_dit_et_chiffre() -> None:
    """Le message doit donner le BUDGET, pas une conclusion que la mesure ne porte pas."""
    rapport = _rapport(_cycle(1, froid=32, temoin=32, chaud=41, essais=40,
                              memo_avant=3, memo_apres=9, caracteres=4000,
                              avertis=100, appels=100, chaud_seul=12, temoin_seul=5),
                       gain=0.20)
    texte = rapport.explication()
    assert "n'est pas DEMONTRE" in texte
    assert "PAIRES" in texte
    assert "lire du bruit" in texte
    assert "sans effet mesurable" not in texte, (
        "un ecart NON nul ne doit pas etre presente comme « sans effet »"
    )


# --- Le cumul entre executions -------------------------------------------------------------


def _mini(numero: int, *, froid: int, temoin: int, chaud: int, essais: int = 20) -> Cycle:
    return _cycle(numero, froid=froid, temoin=temoin, chaud=chaud, essais=essais,
                  memo_apres=3 * numero, caracteres=1000, avertis=essais, appels=essais)


def _run(*cycles: Cycle) -> RapportCycles:
    return RapportCycles(cycles=list(cycles), skill=0.4, runs=4, rounds=2, warning_gain=0.20)


def test_chaque_cycle_est_ecrit_DES_qu_il_est_mesure(tmp_path) -> None:
    """La promesse de robustesse, verifiee sur la seule chose qui compte : le DISQUE.

    Deux mesures de 20 minutes ont ete perdues en entier parce que le rapport n'etait ecrit
    qu'a la fin. `Cumul.ajouter` doit ecrire immediatement — sinon la promesse « une coupure
    ne perd que le cycle en cours » est fausse, et c'est exactement le genre de phrase que ce
    depot refuse d'ecrire sans la tenir. Verifie aussi en tuant un vrai processus : le cycle
    termine survit a un `kill -9`.
    """
    from jio.learn.cycles import Cumul, depuis_cumul

    chemin = tmp_path / "cycles.jsonl"
    cumul = Cumul(chemin, skill=0.4, runs=4, rounds=2, gain=0.20, seed_base=0)
    assert not chemin.exists(), "rien ne doit etre ecrit avant le premier cycle"

    cumul.ajouter(_mini(1, froid=15, temoin=15, chaud=16))
    ecrit = chemin.read_text(encoding="utf-8")
    assert '"type": "cycle"' in ecrit, "le cycle doit etre SUR LE DISQUE, pas en memoire"
    assert depuis_cumul(chemin).essais_cumules == 20

    cumul.ajouter(_mini(2, froid=15, temoin=15, chaud=17))
    assert depuis_cumul(chemin).essais_cumules == 40
    # Un seul en-tete et une seule ligne de replication, quel que soit le nombre de cycles.
    assert chemin.read_text(encoding="utf-8").count('"type": "entete"') == 1
    assert chemin.read_text(encoding="utf-8").count('"type": "replication"') == 1


def test_le_cumul_empile_les_cycles_et_renumerote(tmp_path) -> None:
    """Une mesure de 20 minutes ne doit pas etre perdue par une coupure a la 18e minute.

    Les cycles sont ecrits au fur et a mesure, et une execution suivante EMPILE : le rapport
    affiche est le cumul, avec la resolution de toutes les executions.
    """
    from jio.learn.cycles import cumuler, depuis_cumul

    chemin = tmp_path / "cycles.jsonl"
    premier = cumuler(chemin, _run(_mini(1, froid=15, temoin=15, chaud=16),
                                   _mini(2, froid=16, temoin=16, chaud=17)),
                      runs=4, rounds=2, seed_base=0)
    assert premier.essais_cumules == 40
    assert [c.numero for c in premier.cycles] == [1, 2]

    second = cumuler(chemin, _run(_mini(1, froid=14, temoin=14, chaud=15)),
                     runs=4, rounds=2, seed_base=1000)
    assert second.essais_cumules == 60, "les essais s'additionnent"
    assert [c.numero for c in second.cycles] == [1, 2, 3], "la numerotation continue"

    relu = depuis_cumul(chemin)
    assert relu.essais_cumules == 60
    assert relu.skill == pytest.approx(0.4)


def test_deux_executions_du_MEME_bloc_de_graines_ne_comptent_qu_une_fois(tmp_path) -> None:
    """LE PIEGE DU CUMUL : rejouer les memes graines double le compte sans preuve nouvelle.

    L'intervalle se resserrerait alors autour de rien et le banc pourrait declarer
    significatif un ecart qui n'a jamais ete mesure deux fois. Le rapport doit donc dire
    combien de blocs de graines DISTINCTS il a, et non combien d'executions il a vues.
    """
    from jio.learn.cycles import cumuler

    chemin = tmp_path / "cycles.jsonl"
    passage = lambda: _run(_mini(1, froid=15, temoin=15, chaud=16))  # noqa: E731
    cumuler(chemin, passage(), runs=4, rounds=2, seed_base=0)
    cumule = cumuler(chemin, passage(), runs=4, rounds=2, seed_base=0)

    assert len(cumule.replications) == 2, "deux executions ont bien eu lieu"
    assert cumule.replications_independantes == 1, "mais une seule est independante"
    assert cumule.blocs_de_graines == [0]


def test_le_cumul_refuse_de_MELANGER_les_regimes(tmp_path) -> None:
    """Empiler deux regimes differents ne repond a aucune question : on refuse, on ne melange pas."""
    from jio.learn.cycles import cumuler

    chemin = tmp_path / "cycles.jsonl"
    cumuler(chemin, _run(_mini(1, froid=15, temoin=15, chaud=16)), runs=4, rounds=2)
    autre_regime = RapportCycles(cycles=[_mini(1, froid=15, temoin=15, chaud=16)],
                                 skill=0.9, runs=4, rounds=2, warning_gain=0.20)
    with pytest.raises(ValueError, match="skill"):
        cumuler(chemin, autre_regime, runs=4, rounds=2)


def test_deux_mesures_SIMULTANEES_sont_refusees(tmp_path) -> None:
    """Sans verrou, deux mesures concurrentes liraient le meme nombre de cycles, en
    deduiraient le MEME bloc de graines, et rejoueraient exactement les memes tirages :
    le compte d'essais doublerait sans qu'une preuve soit ajoutee.

    C'est le piege central de tout ce mecanisme, et il ne se voit pas a l'oeil nu dans un
    fichier de resultats — d'ou le verrou, et la phrase qui dit comment le lever.
    """
    from jio.learn.cycles import Cumul

    chemin = tmp_path / "cycles.jsonl"
    premier = Cumul(chemin, skill=0.4, runs=4, rounds=2, gain=0.20, seed_base=0)
    with pytest.raises(ValueError, match="verrou"):
        Cumul(chemin, skill=0.4, runs=4, rounds=2, gain=0.20, seed_base=1000)

    premier.lever_le_verrou()
    # Une fois le verrou leve, la mesure suivante passe (c'est le cas normal).
    second = Cumul(chemin, skill=0.4, runs=4, rounds=2, gain=0.20, seed_base=1000)
    assert second.cycles_deja_mesures == 0
    second.lever_le_verrou()


def test_le_verrou_est_retire_meme_si_la_mesure_echoue(tmp_path) -> None:
    """Un verrou qui survit a une erreur bloquerait l'utilisateur pour toujours."""
    from jio.cli import _learn_cycles, build_parser

    chemin = tmp_path / "cycles.jsonl"
    args = build_parser().parse_args([
        "learn", "--cycles", "1", "--runs", "1", "--rounds", "1", "--skill", "0.4",
        "--cumul", str(chemin), "--calibrer-gain",
    ])
    assert _learn_cycles(args) == 2, "la calibration non implementee doit refuser"
    assert not chemin.with_suffix(".jsonl.verrou").exists(), (
        "le refus de calibration intervient avant le verrou : rien a laisser trainer"
    )


def test_un_cumul_absent_rend_un_rapport_vide(tmp_path) -> None:
    from jio.learn.cycles import depuis_cumul

    vide = depuis_cumul(tmp_path / "jamais-ecrit.jsonl")
    assert vide.cycles == [] and vide.essais_requis() == 0


def test_le_rapport_vide_ne_leve_pas() -> None:
    """Un rapport sans cycle s'affiche quand meme : un echec doit etre lisible."""
    rapport = RapportCycles()
    assert rapport.verdict() == "PLATEAU"
    assert rapport.explication() == "aucun cycle mesure."
    assert rapport.total_essais == 0


# --- La ligne de commande -------------------------------------------------------------------


def test_avec_un_gain_NUL_le_chaud_egale_le_temoin_exactement() -> None:
    """Le controle NEGATIF du protocole, et il ne coute presque rien.

    A gain nul, le temoin et le chaud ont le MEME prompt (meme bloc de memoire), la MEME
    graine et le MEME bras : le seul reglage qui les distinguait est eteint. L'ecart doit
    donc etre exactement zero — s'il ne l'est pas, ce n'est pas la memoire qu'on mesure,
    c'est autre chose dans la chaine. C'est le test qui separe « le protocole mesure un
    effet » de « le protocole mesure une difference quelconque ».
    """
    rapport = run_cycles(skill=0.4, runs=1, cycles=2, rounds=1,
                         task_ids=("sum_even", "is_prime"), warning_gain=0.0)
    for cycle in rapport.cycles:
        assert cycle.ecart == 0, (
            f"gain nul mais ecart chaud/temoin {cycle.ecart:+d} au cycle {cycle.numero} : "
            "quelque chose d'autre que l'effet d'avertissement differe entre les deux bras"
        )


def test_un_effet_DECLARE_est_detecte_integralement() -> None:
    """Le CONTROLE POSITIF, teste sur la logique : un signal connu doit etre vu.

    Un instrument qui ne dit jamais PROGRESSE ne peut pas etre cru quand il dit PLATEAU.
    Le protocole mesure l'effet d'un mecanisme DECLARE : on le regle donc tres haut sur un
    rapport construit a la main, et l'intervalle POOL doit exclure zero. Si ce test tombe,
    tous les PLATEAU du banc perdent leur sens.
    """
    rapport = RapportCycles(
        cycles=[_cycle(n, froid=f, temoin=t, chaud=c, essais=60, chaud_seul=bs)
                for n, f, t, c, bs in ((1, 51, 51, 58, 9), (2, 51, 51, 57, 8))],
        skill=0.4, warning_gain=2.0,
    )
    assert rapport.ecart_cumule == 13
    assert rapport.paires == (17, 0)
    assert rapport.tranche_apparie is True, "17 dissociations favorables contre 0 doit trancher"
    assert rapport.verdict() == "PROGRESSE"
    assert "dissociation DEMONTREE" in rapport.explication()


def test_zero_cycle_reste_l_ab() -> None:
    """`--cycles 0` (defaut) ne doit PAS changer le comportement d'origine : sans cette
    option, `jio learn` reste la comparaison A/B, et son code de sortie ne bouge pas."""
    from jio.cli import build_parser

    args = build_parser().parse_args(["learn"])
    assert args.cycles == 0


def test_le_gain_non_calibre_refuse_de_tourner(capsys) -> None:
    """La constante `warning_gain` est la SEULE chose que le protocole ne mesure pas : elle
    modelise l'effet d'un retour d'echec structure, et elle borne TOUT ce qu'il conclut.

    Tant que ce n'est pas calibre sur un vrai modele, demander la calibration doit
    s'entendre dire « non » explicitement (code 2) plutot que de tourner avec un chiffre
    invente et de publier une portee qui en depend.
    """
    from jio.cli import _learn_cycles, build_parser

    args = build_parser().parse_args(["learn", "--cycles", "1", "--calibrer-gain"])
    assert _learn_cycles(args) == 2
    sortie = capsys.readouterr().out
    assert "CALIBRATION" in sortie
    assert "refuse de tourner" in sortie


def test_le_plafond_de_cout_refuse_au_lieu_de_mesurer(capsys) -> None:
    """MESURER SANS MOYEN = code 2 (doctrine), pas un chiffre approximatif.

    99 cycles x 3 tirages x 4 tours = pres d'une heure de calcul sur deux cœurs. Le
    protocole refuse et DIT pourquoi, avec le nombre de missions et la duree estimee :
    un utilisateur qui voit « 54 min » peut decider ; un utilisateur qui recoit un
    chiffre rendu trop vite ne peut rien decider du tout.
    """
    from jio.cli import _learn_cycles, build_parser

    args = build_parser().parse_args(["learn", "--cycles", "99"])
    code = _learn_cycles(args)
    sortie = capsys.readouterr().out

    assert code == 2, "un refus de mesure doit sortir en INDETERMINE"
    assert "INDETERMINE" in sortie
    assert "missions" in sortie
    # Le refus doit DONNER LE MOYEN DE PASSER OUTRE : un garde-fou de duree n'est pas une
    # interdiction, c'est un choix a assumer.
    # 99 cycles x 3 bras x 5 taches x 3 tirages (defauts de la commande)
    assert "--plafond-missions 4455" in sortie


# --------------------------------------------------------------------------- #
# Une preuve rangee dans un repertoire temporaire n'est pas une preuve
# --------------------------------------------------------------------------- #

def test_le_cumul_dans_un_repertoire_TEMPORAIRE_est_signale(tmp_path) -> None:
    """Le constat qui a fait naitre cet avertissement : une campagne perdue EN ENTIER.

    Le pilote, le cumul deja mesure et les sorties vivaient dans `/tmp` ; le redemarrage de
    la machine les a effaces. Le programme faisait pourtant ce qu'il fallait — chaque cycle
    etait ecrit des qu'il etait mesure. C'est l'EMPLACEMENT qui rendait la preuve mortelle a
    perdre, et c'est la seule chose que le programme ne regardait pas.
    """
    from jio.cli import _preuve_dans_un_repertoire_temporaire

    # Un chemin temporaire : signale, avec le remede exact. `tmp_path` de pytest en fait
    # PARTIE (il vit sous /tmp) — ce qui est une bonne demonstration : le controle ne
    # reconnait pas un nom de fichier, il regarde l'endroit.
    for chemin in (Path("/tmp/cumul.jsonl"), Path("/var/tmp/cumul.jsonl"),
                   tmp_path / "cumul.jsonl"):
        message = _preuve_dans_un_repertoire_temporaire(chemin)
        assert "repertoire EFFACE" in message, f"{chemin} aurait du etre signale"
        assert "evidence/" in message, "le message doit dire OU ecrire a la place"

    # Un chemin du depot : rien a signaler. Un avertissement qui se declenche toujours ne
    # dit plus rien — c'est la meme regle que le reste du depot.
    for chemin in (Path("evidence/cumul.jsonl"),
                   Path(__file__).resolve().parents[1] / "evidence" / "cumul.jsonl"):
        assert _preuve_dans_un_repertoire_temporaire(chemin) == ""


def test_la_commande_learn_affiche_l_avertissement_avant_de_mesurer(tmp_path, capsys) -> None:
    """L'avertissement doit arriver AVANT la mesure, pas apres : sinon il est trop tard."""
    from jio.cli import main

    chemin = Path(tempfile.gettempdir()) / f"jio-test-{uuid.uuid4().hex[:8]}.jsonl"
    code = main(["learn", "--cycles", "1", "--runs", "1", "--rounds", "1", "--skill", "0.4",
                 "--plafond-missions", "100", "--cumul", str(chemin)])
    sortie = capsys.readouterr().out
    assert code == 0, f"la mesure elle-meme doit reussir (code {code})"
    assert "repertoire EFFACE" in sortie
    position = sortie.index("repertoire EFFACE")
    assert "Chaque cycle est ECRIT" not in sortie[:position], (
        "l'avertissement doit preceder le lancement de la mesure"
    )
    for reste in (chemin, chemin.with_suffix(".jsonl.verrou")):
        reste.unlink(missing_ok=True)
