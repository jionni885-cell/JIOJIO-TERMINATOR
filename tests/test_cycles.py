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


def _rapport(*cycles: Cycle) -> RapportCycles:
    return RapportCycles(cycles=list(cycles), skill=0.5, runs=1, rounds=2)


def _cycle(numero: int, froid: int, chaud: int, *, temoin: int = 0, memo_avant: int = 0,
           memo_apres: int = 0, essais: int = 10, caracteres: int = 0,
           avertis: int = 0, appels: int = 0) -> Cycle:
    return Cycle(
        numero=numero, memo_avant=memo_avant, memo_apres=memo_apres, rappels=0,
        froid=froid, temoin=temoin, chaud=chaud, essais=essais,
        caracteres_memoire=caracteres, avertis=avertis, appels=appels,
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
        warning_gain=0.20,
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
        warning_gain=0.20,
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


def test_le_rapport_vide_ne_leve_pas() -> None:
    """Un rapport sans cycle s'affiche quand meme : un echec doit etre lisible."""
    rapport = RapportCycles()
    assert rapport.verdict() == "PLATEAU"
    assert rapport.explication() == "aucun cycle mesure."
    assert rapport.total_essais == 0


# --- La ligne de commande -------------------------------------------------------------------


def test_zero_cycle_reste_l_ab() -> None:
    """`--cycles 0` (defaut) ne doit PAS changer le comportement d'origine : sans cette
    option, `jio learn` reste la comparaison A/B, et son code de sortie ne bouge pas."""
    from jio.cli import build_parser

    args = build_parser().parse_args(["learn"])
    assert args.cycles == 0


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
