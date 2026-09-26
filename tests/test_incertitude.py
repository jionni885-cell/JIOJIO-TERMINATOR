"""L'incertitude d'une mesure : le banc n'a pas le droit d'annoncer un ecart brut.

Le point de depart est une mesure reelle de ce depot : a `--runs 3` (15 essais par bras),
l'ecart d'isolation de l'effet valait +20,0 points et son intervalle de confiance
contenait ZERO. Le chiffre etait exact ; la conclusion qu'on en tirait, fausse.
"""

from __future__ import annotations

import pytest

from jio.bench.incertitude import (
    _quantile,
    ecart_a_la_une,
    intervalle_difference,
    intervalle_wilson,
)


# --------------------------------------------------------------------------- #
# 1. Le quantile normal : verifie contre la TABLE, pas contre lui-meme
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("seuil", "attendu"),
    [(0.90, 1.6449), (0.95, 1.9600), (0.98, 2.3263), (0.99, 2.5758), (0.999, 3.2905)],
)
def test_le_quantile_correspond_a_la_table(seuil: float, attendu: float) -> None:
    """Un quantile faux elargit ou retrecit TOUS les intervalles, en silence.

    Ce n'est pas une crainte theorique : le premier jet rendait 0,24 la ou la table dit
    1,96 — des intervalles cinq fois trop etroits, donc des ecarts declares significatifs
    qui ne l'etaient pas. Le test compare a la table, jamais a la fonction.
    """
    assert _quantile(seuil) == pytest.approx(attendu, abs=1e-3)


def test_un_seuil_hors_domaine_est_refuse() -> None:
    """Un seuil unilaterale ou absurde doit lever, pas produire un intervalle muet."""
    for seuil in (0.0, 0.5, 1.0, 1.5, -0.2):
        with pytest.raises(ValueError):
            _quantile(seuil)


# --------------------------------------------------------------------------- #
# 2. L'intervalle d'une proportion : correct aux EXTREMES, c'est la qu'il sert
# --------------------------------------------------------------------------- #


def test_sans_essai_lintervalle_est_total() -> None:
    """Ne rien avoir mesure et ne rien pouvoir dire sont la meme chose."""
    assert intervalle_wilson(0, 0) == (0.0, 1.0)


@pytest.mark.parametrize(("succes", "total"), [(0, 10), (10, 10), (14, 15), (1, 100)])
def test_lintervalle_contient_toujours_lobservation(succes: int, total: int) -> None:
    bas, haut = intervalle_wilson(succes, total)
    assert 0.0 <= bas <= succes / total <= haut <= 1.0


def test_les_extremes_ne_produisent_pas_dintervalle_vide() -> None:
    """0 erreur sur 15 essais ne veut PAS dire « 0 % d'erreur », et l'intervalle le dit.

    L'intervalle normal donnerait une largeur NULLE ici — « zero erreur, donc zero
    risque » — ce qui est exactement la conclusion que ce projet refuse.
    """
    bas, haut = intervalle_wilson(0, 15)
    assert bas == 0.0
    assert haut > 0.15, "15 essais sans erreur laissent une marge reelle"

    bas, haut = intervalle_wilson(15, 15)
    assert haut == 1.0
    assert bas < 0.85, "15 succes sur 15 ne prouvent pas 100 %"


def test_plus_il_y_a_dessais_plus_lintervalle_est_etroit() -> None:
    petit = intervalle_wilson(7, 10)
    grand = intervalle_wilson(700, 1000)
    assert (grand[1] - grand[0]) < (petit[1] - petit[0])


# --------------------------------------------------------------------------- #
# 3. L'ecart entre deux bras : la question qui decide de la conclusion
# --------------------------------------------------------------------------- #


def test_un_ecart_net_est_significatif() -> None:
    echantillon = [0.0] * 15
    ecart, intervalle, tranche = ecart_a_la_une(echantillon, [1.0] * 15)
    assert ecart == pytest.approx(100.0)
    assert tranche is True
    assert intervalle[0] > 0.0, "l'intervalle exclut zero"


def test_deux_bras_identiques_ne_prouvent_aucun_effet() -> None:
    """0 point d'ecart : l'intervalle contient zero, et le dit."""
    bras = [1.0, 0.0] * 8
    ecart, intervalle, tranche = ecart_a_la_une(bras, list(bras))
    assert ecart == pytest.approx(0.0)
    assert intervalle[0] < 0.0 < intervalle[1]
    assert tranche is False


def test_lecart_mesure_sur_ce_depot_est_declare_indetermine() -> None:
    """Le cas qui a motive ce module : +20,0 points sur 15 essais par bras.

    C'est le resultat REEL du banc a `--runs 3` (11/15 contre 14/15). Le banc annoncait
    « le gain vient bien de la VERIFICATION » ; a ce nombre d'essais, la formulation
    correcte est « indéterminé ». Un rapport qui affirme l'un pour l'autre fait dire a
    ses chiffres plus qu'ils ne portent.
    """
    sans_verification = [1.0] * 11 + [0.0] * 4
    avec_verification = [1.0] * 14 + [0.0] * 1
    ecart, intervalle, tranche = ecart_a_la_une(sans_verification, avec_verification)
    assert ecart == pytest.approx(20.0)
    assert intervalle[0] < 0.0 < intervalle[1], "l'intervalle contient zero"
    assert tranche is False, "donc l'ecart n'est PAS demontre a ce nombre d'essais"


def test_ecart_a_la_une_ne_rend_jamais_un_intervalle_absurde() -> None:
    """Sans essai d'un cote, l'ignorance est totale : l'intervalle est [-1 ; +1]."""
    assert intervalle_difference([], [1.0] * 10) == (-1.0, 1.0)


# --------------------------------------------------------------------------- #
# 4. Le budget de mesure : « indéterminé » n'est une réponse que s'il est actionnable
# --------------------------------------------------------------------------- #


def test_le_budget_grandit_quand_leffet_retrecit() -> None:
    """Un petit effet demande plus d'essais : c'est ce qui rend le verdict lisible."""
    from jio.bench.incertitude import essais_necessaires

    gros = essais_necessaires(0.50, 0.80)
    moyen = essais_necessaires(0.50, 0.60)
    petit = essais_necessaires(0.50, 0.55)
    assert 0 < gros < moyen < petit


def test_un_effet_nul_ne_se_demontre_pas() -> None:
    """Aucun nombre d'essais ne prouvera une difference nulle : la fonction le dit."""
    from jio.bench.incertitude import essais_necessaires

    assert essais_necessaires(0.5, 0.5) == 0


def test_le_budget_explique_lecart_mesure_sur_ce_depot() -> None:
    """+1,7 point a 60 essais par bras : indémontrable en pratique, et chiffrable.

    C'est le resultat REEL du banc a `--runs 12`. Le banc affichait « +20,0 points » a
    `--runs 3` ; a 60 essais l'ecart tombe a +1,7 point, et il faudrait plus de dix mille
    essais par bras pour le demontrer. La bonne lecture n'est ni « pas d'effet » ni
    « effet demontre » : c'est « effet non etabli, et voici le prix de la preuve ».
    """
    from jio.bench.incertitude import essais_necessaires

    assert essais_necessaires(0.750, 0.767) > 10_000
    # Le meme calcul sur l'ecart observe a `--runs 3` : atteignable, lui.
    assert essais_necessaires(0.733, 0.933) < 200


# --------------------------------------------------------------------------- #
# 5. Le banc de memoire porte la meme exigence : un ecart nu n'est pas un resultat
# --------------------------------------------------------------------------- #


def test_le_banc_de_memoire_rend_un_intervalle_et_un_budget() -> None:
    """Meme exigence que pour le banc de code : IC95 et verdict, pas un chiffre nu.

    Mesure reelle de ce depot (`jio learn --runs 8`, 40 essais par bras) : les deux
    ecarts valent +0,0 point avec un intervalle [-12,1 ; +12,1]. Le banc dit donc
    « indéterminé a cet echantillon », et non « pas d'effet » — la nuance est le sujet.
    """
    from jio.learn.experiment import ABCResult

    resultat = ABCResult(cold_success=20, control_success=20, warm_success=20, total=40)
    ecart, (bas, haut), tranche = resultat.intervalle(20, 20)
    assert ecart == pytest.approx(0.0)
    assert bas < 0.0 < haut
    assert tranche is False
    assert resultat.budget_de_mesure() == 0, "un effet nul ne se demontre pas"
    assert resultat.budget_du_bruit() == 0


def test_un_gain_net_du_banc_de_memoire_est_significatif() -> None:
    """Et quand l'effet est franc, le banc doit pouvoir le dire sans prudence excessive."""
    from jio.learn.experiment import ABCResult

    resultat = ABCResult(cold_success=10, control_success=10, warm_success=35, total=40)
    ecart, (bas, haut), tranche = resultat.intervalle(10, 35)
    assert ecart == pytest.approx(62.5)
    assert bas > 0.0 and tranche is True
    assert resultat.budget_de_mesure() > 0


def test_une_entropie_de_risque_FAIBLE_seule_est_dite_confiante() -> None:
    """`confident` est vrai pour « faible », et pour lui SEUL.

    Mesure a l'origine : `jio mutants` a montre que l'egalite `risk == "faible"` pouvait
    devenir une INEGALITE sans qu'aucun test ne bouge. Le systeme se serait alors declare
    confiant quand le risque est MOYEN ou ELEVE — l'inverse exact de sa fonction, et sur le
    signal qui decide d'accepter une reponse.
    """
    from jio.verify.entropy import EntropyResult

    def resultat(risque: str) -> bool:
        return EntropyResult(
            entropy=0.1, clusters=1, samples=4, dominant_share=1.0, risk=risque
        ).confident

    assert resultat("faible") is True
    assert resultat("moyen") is False
    assert resultat("eleve") is False


def test_un_ensemble_vide_est_un_risque_ELEVE_pas_une_confiance() -> None:
    """Sans reponse a comparer, il n'y a rien a conclure : le risque est maximal.

    Mesure a l'origine : `jio mutants` a montre que les compteurs de ce cas (`clusters=0`,
    `samples=0`) pouvaient passer a 1 sans qu'aucun test ne bouge. Zero echantillon annonce
    comme un echantillon donnerait une entropie calculee sur rien.
    """
    from jio.verify.entropy import semantic_entropy

    vide = semantic_entropy([])
    assert (vide.clusters, vide.samples) == (0, 0)
    assert vide.risk == "eleve" and vide.confident is False
    assert vide.entropy == 1.0
    # Les entrees blanches comptent comme absentes : elles n'apportent aucune information.
    blanc = semantic_entropy(["", "   ", "\n"])
    assert (blanc.clusters, blanc.samples) == (0, 0)

def test_deux_textes_SANS_nombre_ne_sont_pas_declares_numeriquement_egaux() -> None:
    """`_numeric_equal` : sans nombre des deux cotes, il n'y a aucune egalite a conclure.

    Mesure a l'origine : `jio mutants` a montre que ce `return False` pouvait devenir `True`
    sans qu'aucun test ne bouge. Deux reponses sans aucun nombre auraient alors ete jugees
    « identiques » : l'entropie se serait effondree, le systeme se serait declare CONFIANT,
    et il l'aurait fait sur deux textes qui peuvent dire l'inverse l'un de l'autre.
    """
    from jio.verify.entropy import _numeric_equal

    assert _numeric_equal("aucun nombre ici", "rien du tout") is False
    assert _numeric_equal("le total est 12.0", "le total est 12") is True
    assert _numeric_equal("le total est 12", "le total est 13") is False
