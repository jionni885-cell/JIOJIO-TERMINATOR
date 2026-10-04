"""La couleur suit la SORTIE, elle n'est pas supposee.

DEFAUT MESURE, corrige ici : `jio run > rapport.txt` ecrivait sept sequences d'echappement ANSI
dans un fichier. `render_report` peignait par defaut, sans regarder ou sa sortie allait. Un
journal de CI affichait alors `^[[32m[OK]^[[0m`, un `diff` de rapports etait faux, et une
sequence collee dans un ticket apparaissait en caracteres de controle.

Une couleur est une commodite de TERMINAL. Ailleurs c'est du bruit. Ces tests verifient les
quatre regles, dans l'ordre ou elles s'appliquent, et ils forcent le flux au lieu de dependre du
terminal qui execute la suite : un test de couleur qui depend de `pytest` lance dans un tube
serait un test qui change de resultat selon la machine.
"""

from __future__ import annotations

import io

from jio.cli import COLORS, couleur_activee, render_report


class _Terminal(io.StringIO):
    """Un flux qui se declare terminal — ce que fait le vrai `sys.stdout` sous un TTY."""

    def isatty(self) -> bool:  # noqa: D102 — la seule chose que ce faux flux doit savoir faire
        return True


class _Fichier(io.StringIO):
    """Un flux qui se declare NON terminal — un tube, une redirection, un fichier."""

    def isatty(self) -> bool:  # noqa: D102
        return False


def test_un_terminal_est_peint_et_un_fichier_non() -> None:
    assert couleur_activee(_Terminal()) is True
    assert couleur_activee(_Fichier()) is False


def test_NO_COLOR_coupe_tout_meme_dans_un_terminal(monkeypatch) -> None:
    """Le standard https://no-color.org : present et NON VIDE. Une variable vide ne compte pas."""
    monkeypatch.setenv("NO_COLOR", "1")
    assert couleur_activee(_Terminal()) is False
    monkeypatch.setenv("NO_COLOR", "   ")
    assert couleur_activee(_Terminal()) is True, "une variable vide n'est pas une demande"


def test_JIO_NO_COLOR_existe_pour_ne_pas_toucher_NO_COLOR(monkeypatch) -> None:
    """Notre nom a nous : couper les couleurs de JIO sans changer le comportement des autres
    outils de la machine."""
    monkeypatch.setenv("JIO_NO_COLOR", "1")
    assert couleur_activee(_Terminal()) is False


def test_TERM_dumb_est_respecte(monkeypatch) -> None:
    monkeypatch.setenv("TERM", "dumb")
    assert couleur_activee(_Terminal()) is False


def test_un_flux_sans_isatty_ne_peint_pas() -> None:
    """Un objet sans `isatty` (ou ferme) ne doit pas faire planter la commande : il ne doit
    simplement pas recevoir de couleur."""
    assert couleur_activee(object()) is False
    assert couleur_activee(io.StringIO()) is False


def _rapport_reel():
    """Un VRAI `MissionReport`, produit par le moteur simule.

    Pourquoi pas un objet bricole : `render_report` lit une quinzaine de champs, et un faux
    rapport finirait par ne plus rien tester du tout — il suffirait qu'un champ nouveau
    apparaisse pour que le test echoue sur un attribut manquant, ce qui ne dit rien de la
    couleur. Ici, la sortie est exactement celle que l'utilisateur voit.
    """
    from jio.bench.tasks import TASKS
    from jio.cli import _simulated_engine
    from jio.core.types import Mission
    from jio.loop.engine import WorkItem

    tache = [t for t in TASKS if t.id == "sum_even"][0]
    moteur = _simulated_engine(tache, skill=0.9, seed=0, max_rounds=2)
    return moteur.run(
        Mission(objective=tache.objective, id="couleur", max_rounds=2),
        WorkItem(objective=tache.objective, entrypoint=tache.entrypoint,
                 checks=tache.checks, spec=tache.spec()),
    )


def test_le_rapport_ne_contient_AUCUNE_sequence_quand_la_sortie_n_est_pas_un_terminal() -> None:
    """Le defaut mesure : sept sequences ANSI dans un fichier redirige."""
    texte = render_report(_rapport_reel(), color=couleur_activee(_Fichier()))
    assert "\033[" not in texte
    assert "[OK]" in texte


def test_le_rapport_PEINT_quand_la_sortie_est_un_terminal() -> None:
    """L'autre moitie : la couleur doit exister quand il y a un humain devant. Sans ce test,
    « ne jamais colorer » passerait pour une reussite."""
    texte = render_report(_rapport_reel(), color=couleur_activee(_Terminal()))
    assert COLORS["ok"] in texte
    assert COLORS["reset"] in texte


def test_les_trois_autres_commandes_qui_peignent_suivent_la_meme_regle() -> None:
    """`_c` sans argument explicite consulte la sortie reelle : c'est le chemin par defaut, et
    c'est celui qui doit etre bon — pas seulement celui que les tests passent en parametre."""
    from jio.cli import _c

    assert _c("texte", "bad", False) == "texte"
    assert _c("texte", "bad", True).startswith(COLORS["bad"])
    # Le defaut, lui, depend du flux de sortie du processus : sous pytest, c'est un tube.
    assert "\033[" not in _c("texte", "bad")
