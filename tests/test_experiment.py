"""Le protocole A/B/C de l'auto-amelioration : la seule comparaison causale du depot.

Trois bras, et un seul contraste qui prouve quelque chose : B -> C. Les deux bras envoient
le MEME prompt avec une memoire identique ; seul l'effet d'avertissement change. Si ce
reglage ne s'appliquait pas reellement, les trois bras mesureraient la meme chose et le
depot annoncerait un gain d'auto-amelioration qui n'existe pas.

Mesure a l'origine : `jio mutants` a montre que l'affectation `provider.warning_gain =
gain` pouvait etre remplacee par `pass` sans qu'aucun test ne bouge — le protocole n'avait
aucun test a lui.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jio.learn.experiment import ABCResult, _set_warning_gain, run_abc


class _Fournisseur:
    def __init__(self, gain: float = 0.0) -> None:
        self.warning_gain = gain


class _FournisseurSansGain:
    """Un fournisseur qui n'a pas l'attribut : il doit etre laisse tel quel, pas casse."""

    def __init__(self) -> None:
        self.marque = "intact"


def test_l_effet_d_avertissement_est_regle_sur_les_generateurs() -> None:
    classe = type("Moteur", (), {})
    moteur = classe()
    a, b = _Fournisseur(gain=0.0), _Fournisseur(gain=1.0)
    autre = _FournisseurSansGain()
    moteur.generators = [a, b, autre]

    _set_warning_gain(moteur, 0.20)
    assert a.warning_gain == 0.20
    assert b.warning_gain == 0.20
    assert autre.marque == "intact", "un generateur sans cet attribut ne doit pas etre touche"

    # Le bras TEMOIN vaut exactement 0 : c'est ce qui separe B de C.
    _set_warning_gain(moteur, 0.0)
    assert a.warning_gain == 0.0 and b.warning_gain == 0.0


def test_un_moteur_sans_generateur_ne_plante_pas() -> None:
    """`getattr(engine, "generators", ())` : un moteur incomplet ne doit pas lever."""
    _set_warning_gain(type("Moteur", (), {})(), 0.2)


def test_le_protocole_abc_tourne_et_rend_ses_trois_bras() -> None:
    """Une execution courte, mais REELLE : trois bras, un resultat par tache.

    On ne verifie pas ici que l'auto-amelioration « marche » (cela depend de la competence
    simulee, et le rapport du depot le mesure) : on verifie que le protocole tourne, qu'il
    rend les trois bras, et que le bras temoin est bien un bras a part.
    """
    resultat = run_abc(skill=0.12, runs=1, rounds=2, task_ids=("sum_even",))
    assert isinstance(resultat, ABCResult)
    assert resultat.total == 1, f"une tache demandee, {resultat.total} mesuree(s)"
    cold, control, warm = resultat.per_task["sum_even"]
    assert cold in (0, 1) and control in (0, 1) and warm in (0, 1)
    # Le total des trois bras doit correspondre a ce qui a ete enregistre : un compteur
    # qui derive ferait afficher un taux calcule sur autre chose que ce qui a tourne.
    assert resultat.cold_success == cold
    assert resultat.control_success == control
    assert resultat.warm_success == warm
    # Les proprietes du protocole doivent rester coherentes avec les compteurs.
    assert resultat.isolated_gain == pytest.approx(resultat.warm_rate - resultat.control_rate)
    assert resultat.lottery_artifact == pytest.approx(
        resultat.control_rate - resultat.cold_rate
    )
    # `intervalle` rend (ecart, (bas, haut), tranche) : l'ecart en POINTS et son IC95.
    ecart, (bas, haut), tranche = resultat.intervalle(
        resultat.control_success, resultat.warm_success
    )
    assert bas <= ecart <= haut and isinstance(tranche, bool)
    # La memoire vit sur disque, mais dans un dossier TEMPORAIRE : rien ne doit apparaitre
    # dans le depot (le protocole serait alors dependant de la machine qui le lance).
    assert not Path(".jio/learn").exists()


def test_un_resultat_vierge_ne_compte_aucune_reussite() -> None:
    """Les compteurs de `ABCResult` partent de ZERO.

    Un compteur qui part de 1 annonce une reussite qui n'a pas eu lieu, et TOUS les taux
    calcules a partir de lui seraient faux — y compris le gain d'auto-amelioration que le
    depot publie. Mesure a l'origine : `jio mutants` a montre que ces deux constantes
    pouvaient passer a 1 sans qu'aucun test ne bouge.
    """
    vierge = ABCResult()
    assert (vierge.cold_success, vierge.control_success, vierge.warm_success) == (0, 0, 0)
    assert (vierge.total, vierge.recorded, vierge.missions_with_recall) == (0, 0, 0)
    assert vierge.cold_rate == 0.0 and vierge.control_rate == 0.0 and vierge.warm_rate == 0.0
    assert vierge.isolated_gain == 0.0 and vierge.lottery_artifact == 0.0
