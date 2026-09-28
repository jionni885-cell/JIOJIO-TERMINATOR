"""Les codes de sortie : une doctrine, et un garde-fou contre la derive.

DEFAUT MESURE, corrige ici : `jio run` rendait **1** aussi bien pour « livre AVEC une reserve
nommee » que pour « ABSTENTION : rien n'a pu etre prouve ». Un appelant — script, hook, agent —
ne pouvait donc pas distinguer « j'ai un livrable, avec une reserve a lever » de « je n'ai rien,
et il me manque quelque chose ». Ce sont deux ACTIONS differentes : corriger, ou fournir.

Les codes sont donc declares une fois (`jio/core/codes.py`) avec, pour chacun, l'action qu'il
demande. Et ce fichier va plus loin qu'une table : il LIT `jio/cli.py` et exige qu'aucun
`return <n>` n'invente un code hors doctrine. Un code de sortie est un contrat avec les
scripts des autres ; il ne doit pas pouvoir apparaitre par accident dans une fonction.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from jio.core.codes import (
    ACTION,
    CODES,
    EN_ATTENTE,
    INDETERMINE,
    OK,
    PROBLEME,
    TABLE,
    code_de_mission,
)
from jio.core.types import MissionStatus


def test_la_table_couvre_LES_QUATRE_etats_de_mission() -> None:
    """Aucun etat ne doit tomber dans un `except` avec un code par defaut : chacun est decide."""
    assert set(TABLE) == set(MissionStatus)
    assert TABLE[MissionStatus.DELIVERED] == OK
    assert TABLE[MissionStatus.DELIVERED_WITH_RESERVATION] == PROBLEME
    assert TABLE[MissionStatus.ABSTAINED] == INDETERMINE
    assert TABLE[MissionStatus.FAILED] == PROBLEME


def test_une_reserve_n_est_pas_une_faute_mais_pas_un_quitus() -> None:
    """« Livre avec reserve » doit se distinguer d'« OK » ET de « rien du tout »."""
    assert code_de_mission(MissionStatus.DELIVERED) == 0
    assert code_de_mission(MissionStatus.DELIVERED_WITH_RESERVATION) == 1
    assert code_de_mission(MissionStatus.ABSTAINED) == 2
    assert code_de_mission(MissionStatus.ABSTAINED) != code_de_mission(
        MissionStatus.DELIVERED_WITH_RESERVATION
    ), "c'est exactement la confusion corrigee : corriger ou fournir ne sont pas la meme action"


def test_CHAQUE_code_dit_l_action_qu_il_demande() -> None:
    for code in CODES:
        assert code in ACTION, f"le code {code} n'a pas d'action associee"
        assert ACTION[code].strip()


def test_un_etat_inconnu_LEVE_au_lieu_de_rendre_un_code_par_defaut() -> None:
    with pytest.raises(ValueError):
        code_de_mission("etat-inexistant")  # type: ignore[arg-type]


def test_aucune_commande_n_invente_un_code_hors_doctrine() -> None:
    """Garde-fou de derive : le fichier des commandes est LU, pas suppose.

    Un `return 4` ajoute un jour dans une fonction ferait un contrat invisible. Ce test
    l'attrape a la seconde ou il est ecrit, avec le numero fautif dans le message.
    """
    source = (Path(__file__).resolve().parent.parent / "jio" / "cli.py").read_text("utf-8")
    rendus = {int(n) for n in re.findall(r"^[ \t]*return (\d+)\s*$", source, flags=re.MULTILINE)}
    # Les codes rendus par une expression (`return 0 if ... else 1`) sont couverts par le
    # controle ci-dessous, qui lit TOUS les entiers apparaissant a droite d'un `return`.
    rendus |= {
        int(n) for n in re.findall(r"return[^\n]*?(?<!\d)(\d)(?!\d)", source)
    }
    inconnus = sorted(rendus - set(CODES))
    assert not inconnus, (
        f"codes de sortie hors doctrine dans jio/cli.py : {inconnus} — "
        f"declarez-les dans jio/core/codes.py (CODES/ACTION) ou utilisez un code existant"
    )


def test_les_codes_sont_ceux_que_les_scripts_connaissent() -> None:
    """Les valeurs elles-memes sont un contrat : 0 = succes, 2 = usage incorrect (argparse).
    Les changer casserait des scripts, y compris ceux de l'utilisateur."""
    assert (OK, PROBLEME, INDETERMINE, EN_ATTENTE) == (0, 1, 2, 3)


def test_la_sortie_de_run_EST_le_code_de_la_table(monkeypatch) -> None:
    """La table doit etre ce qui SORT, pas seulement ce qui est ecrit dans un module.

    On pilote le moteur pour lui faire rendre chacun des quatre etats et on lit le code de
    sortie du CLI — c'est le seul endroit ou le contrat devient reel.
    """
    from jio.cli import main
    from jio.core.types import MissionReport

    for statut, attendu in (
        (MissionStatus.DELIVERED, 0),
        (MissionStatus.DELIVERED_WITH_RESERVATION, 1),
        (MissionStatus.ABSTAINED, 2),
        (MissionStatus.FAILED, 1),
    ):
        rapports: list[MissionReport] = []

        def faux_run(self, mission, work):  # noqa: ANN001, ANN202 - substitut de test
            rapport = MissionReport(
                mission_id="test", objective="objectif", status=statut,
                abstention_reason="rien ne peut etre prouve",
            )
            rapports.append(rapport)
            return rapport

        from jio.loop import engine as module_moteur

        monkeypatch.setattr(module_moteur.Engine, "run", faux_run, raising=True)
        code = main([
            "run", "Sum even numbers below two hundred",
            "--simulate", "--task", "sum_even", "--sans-competences",
        ])
        assert code == attendu, f"{statut} devrait sortir en {attendu}, sorti en {code}"


def test_l_abstention_explique_QUOI_fournir(capsys, monkeypatch) -> None:
    """Un code 2 sans phrase ne dit pas quoi faire. Le rapport doit nommer l'action."""
    from jio.cli import main
    from jio.core.types import MissionReport

    def faux_run(self, mission, work):  # noqa: ANN001, ANN202
        return MissionReport(
            mission_id="test", objective="objectif", status=MissionStatus.ABSTAINED,
            abstention_reason="aucun temoin disponible",
        )

    from jio.loop import engine as module_moteur

    monkeypatch.setattr(module_moteur.Engine, "run", faux_run, raising=True)
    code = main([
        "run", "Sum even numbers below two hundred",
        "--simulate", "--task", "sum_even", "--sans-competences",
    ])
    sortie = capsys.readouterr().out
    assert code == 2
    assert "code 2" in sortie
    assert "fournir" in sortie, "l'appelant doit savoir quoi faire, pas seulement que ca a rate"
