"""Le chemin REEL est prouve, pas seulement decrit.

Il n'y a pas de cle API dans un environnement de test, donc on ne peut pas mesurer
un vrai modele. Mais on peut prouver tout ce qui est verifiable : que JIO detecte une
CLI externe, lui parle, recupere sa reponse, la verifie, la soumet au consensus puis a
la porte de conformite, et livre. Un fournisseur qui n'a jamais tourne n'est pas un
fournisseur, c'est une intention.

Ces tests verrouillent trois comportements distincts, tous constates en usage reel :

1. **trois agents distincts** -> `DELIVERED`. La chaine complete fonctionne ;
2. **un seul agent** -> reserve « ce n'est pas un consensus, c'est un echo » ;
3. **deux agents** -> plafond arithmetiquement inatteignable, et le motif doit le
   DIRE avec la solution, sinon l'utilisateur cherche pendant des heures pourquoi
   une mission parfaite n'est jamais acceptee.
"""

from __future__ import annotations

import os
import stat
import sys
from pathlib import Path

import pytest

from jio.core.types import MissionStatus

#: Faux agent : repond en JSON quand on lui demande une critique, et rend un code
#: correct quand on lui demande un artefact. Mimique `opencode run --format json`
#: (une ligne JSON par evenement), que le fournisseur CLI sait lire.
STUB = '''#!{python}
import json
import sys

prompt = " ".join(sys.argv[2:]) if len(sys.argv) > 2 else ""

if "You are a strict" in prompt:
    print(json.dumps({{"type": "text", "text": json.dumps({{
        "verdict": "pass", "confidence": 0.9,
        "reason": "la specification est satisfaite", "counterexample": None,
    }})}}))
    sys.exit(0)

CODE = """def median(nums):
    if not nums:
        raise ValueError("liste vide")
    valeurs = sorted(nums)
    milieu = len(valeurs) // 2
    if len(valeurs) % 2:
        return valeurs[milieu]
    return (valeurs[milieu - 1] + valeurs[milieu]) / 2
"""

print(json.dumps({{"type": "text", "text": "```python\\n" + CODE + "```\\n"}}))
'''


def _installer_agents(tmp_path: Path, noms: tuple[str, ...]) -> dict[str, str]:
    """Cree un faux binaire par agent et retourne les variables JIO_BIN_* associees."""
    env: dict[str, str] = {}
    for nom in noms:
        binaire = tmp_path / nom
        binaire.write_text(STUB.format(python=sys.executable), encoding="utf-8")
        binaire.chmod(binaire.stat().st_mode | stat.S_IEXEC)
        env[f"JIO_BIN_{nom.upper()}"] = str(binaire)
    return env


def _mission(tmp_path: Path, monkeypatch, agents: tuple[str, ...]) -> object:
    for key in list(os.environ):
        if key.startswith("JIO_BIN_"):
            monkeypatch.delenv(key, raising=False)
    for key, value in _installer_agents(tmp_path, agents).items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("JIO_LINTERS", "off")

    from jio.bench.tasks import TASKS_BY_ID
    from jio.cli import _real_engine
    from jio.core.types import Mission
    from jio.loop.engine import WorkItem

    task = TASKS_BY_ID["median"]
    engine = _real_engine(journal_path=tmp_path / "journal.jsonl", max_rounds=3)
    return engine.run(
        Mission(objective=task.objective, max_rounds=3),
        WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                 checks=task.checks, spec=task.spec()),
    )


def test_trois_agents_distincts_livrent(tmp_path: Path, monkeypatch) -> None:
    """La chaine complete : detecter la CLI, lui parler, verifier, livrer."""
    report = _mission(tmp_path, monkeypatch, ("opencode", "hermes", "claude"))

    assert report.status is MissionStatus.DELIVERED, report.abstention_reason
    assert report.passed == report.total_checks


def test_un_seul_agent_est_denonce_comme_un_echo(tmp_path: Path, monkeypatch) -> None:
    """Cinq agents sur un seul modele ne valent pas cinq agents.

    C'est la lecon de « Conformity Breaks Conformal Prediction » : l'accord entre
    copies d'un meme modele ne prouve rien. Le systeme doit refuser de l'appeler
    un consensus — et le dire dans ces termes.
    """
    report = _mission(tmp_path, monkeypatch, ("opencode",))

    assert report.status is MissionStatus.DELIVERED_WITH_RESERVATION
    assert "echo" in report.abstention_reason
    assert report.passed == report.total_checks, "le travail est bon : c'est le consensus qui manque"


def test_deux_agents_expliquent_le_plafond_et_la_solution(tmp_path: Path, monkeypatch) -> None:
    """Un refus doit etre calculable et actionnable, pas seulement honnete.

    Avec deux couples (modele, verdict) distincts, la decorrelation vaut
    0.55 + 0.15*2 = 0.85 : une mission PARFAITE plafonne a 0.85, sous le seuil non
    calibre de 0.90. Aucune amelioration du travail ne peut livrer. Sans cette
    explication, l'utilisateur conclut que l'outil est casse.
    """
    report = _mission(tmp_path, monkeypatch, ("opencode", "hermes"))

    assert report.status is MissionStatus.DELIVERED_WITH_RESERVATION
    motif = report.abstention_reason
    assert "PLAFOND INATTEIGNABLE" in motif
    assert "3e modele" in motif, "la solution doit etre donnee, pas seulement le constat"
    assert "decompte" in motif, "le calcul doit etre verifiable"


@pytest.mark.parametrize("agents", [("opencode",), ("opencode", "hermes"), ("opencode", "hermes", "claude")])
def test_la_cli_est_detectee_via_la_variable_documentee(
    tmp_path: Path, monkeypatch, agents: tuple[str, ...]
) -> None:
    """`JIO_BIN_<NOM>` doit reellement choisir le binaire — la variable etait ignoree."""
    for key, value in _installer_agents(tmp_path, agents).items():
        monkeypatch.setenv(key, value)

    from jio.providers.registry import detect_clis

    binaires = {p.binary for p in detect_clis()}

    for value in _installer_agents(tmp_path, agents).values():
        assert value in binaires
