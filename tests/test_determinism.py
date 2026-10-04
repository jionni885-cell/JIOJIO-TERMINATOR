"""Tests de reproductibilite — la promesse la plus facile a casser sans le voir.

Deux bugs reels ont rendu le systeme non reproductible. Tous deux etaient
invisibles : les resultats restaient plausibles, ils changeaient simplement d'une
execution a l'autre.

  1. `random.Random(hash((...)))` : `hash()` sur des chaines est randomise par
     processus (PYTHONHASHSEED). Le panel de critiques votait donc differemment
     pour le meme artefact et la meme graine.
  2. Le bac a sable ecrivait la source dans un dossier temporaire ALEATOIRE dont
     le chemin apparaissait dans les traces d'erreur. L'empreinte du temoin
     changeait a chaque execution, et toute decision qui en derivait aussi.

Une preuve qu'on ne peut pas rejouer n'est pas une preuve : c'est une anecdote.
Ces tests echouent si l'un des deux revient.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from jio.core.types import Witness
from jio.verify.executable import Sandbox

_PROBE = """
import sys
sys.path.insert(0, %r)
from jio.audit.panel import _stable_seed
from jio.cli import _simulated_engine
from jio.core.types import Mission
from jio.bench.tasks import TASKS_BY_ID
from jio.loop.engine import WorkItem
from jio.verify.executable import Sandbox
from jio.core.types import Witness

# 1. Le panel de critiques, a travers son RNG (pas seulement la fonction de graine).
task = TASKS_BY_ID["median"]
eng = _simulated_engine(task, skill=0.13, seed=0, max_rounds=4)
rep = eng.run(Mission(objective=task.objective, id="det", max_rounds=4),
              WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                       checks=dict(task.checks), spec=task.spec()))
print("statut", rep.status.value)
print("votes", "".join(v.decision.value[0] for v in rep.votes))
print("calls", rep.usage.get("calls"))
print("witness", ",".join(w.output_hash for w in rep.witnesses))
print("seed", _stable_seed("redteam", 0, "def f(): return 1"))

# 2. Le bac a sable : aucun chemin aleatoire dans les temoins.
res = Sandbox(timeout=20).run_python(
    "raise ValueError('echec volontaire ' + __file__)", tag="probe"
)
print("stderr", res.stderr.strip().splitlines()[-1])
print("hash", Witness(rule_id="R-1", command="x", exit_code=1, ok=False,
                     stdout=res.stdout, stderr=res.stderr).output_hash)
"""


def _run_probe(hash_seed: str) -> list[str]:
    env = dict(os.environ)
    env["PYTHONHASHSEED"] = hash_seed
    root = str(Path(__file__).resolve().parent.parent)
    out = subprocess.run(
        [sys.executable, "-c", _PROBE % root],
        capture_output=True, text=True, env=env, timeout=120,
    )
    assert out.returncode == 0, out.stderr
    wanted = ("statut", "votes", "calls", "witness", "seed", "stderr", "hash")
    return [line for line in out.stdout.splitlines() if line.startswith(wanted)]


# --------------------------------------------------------------------------- #
# 1. Graine stable entre processus
# --------------------------------------------------------------------------- #


def test_stable_seed_ne_depend_pas_du_hachage_aleatoire():
    """`hash()` est randomise par processus : l'utiliser comme graine casse tout."""
    from jio.audit.panel import _stable_seed

    assert _stable_seed("a", 1, "b") == _stable_seed("a", 1, "b")
    assert _stable_seed("a", 1, "b") != _stable_seed("a", 1, "c")


def test_mission_entiere_reproductible_entre_processus():
    """Deux processus avec des PYTHONHASHSEED differents doivent rendre le MEME verdict.

    Ce test est bout-en-bout a dessein : la version precedente verifiait seulement
    la fonction de graine, et restait donc verte alors que le site d'appel du
    panel utilisait toujours `hash()`. Un test qui ne peut pas echouer est une
    decoration — leçon apprise en le verifiant par mutation volontaire.
    """
    first = _run_probe("0")
    second = _run_probe("1")
    assert first == second, f"non reproductible entre processus :\n{first}\n{second}"
    assert any(line.startswith("statut") for line in first)


# --------------------------------------------------------------------------- #
# 2. Aucun chemin aleatoire dans les temoins
# --------------------------------------------------------------------------- #


def test_le_chemin_du_bac_a_sable_est_normalise():
    res = Sandbox(timeout=20).run_python(
        "raise ValueError('trace ' + __file__)", tag="norm"
    )
    assert "<sandbox>" in res.stderr, "le chemin temporaire n'a pas ete normalise"
    assert "/tmp/jio-" not in res.stderr


def test_empreinte_de_temoin_stable_dans_le_meme_processus():
    sandbox = Sandbox(timeout=20)

    def once() -> str:
        res = sandbox.run_python("raise ValueError(__file__)", tag="h")
        return Witness(
            rule_id="R-1", command="x", exit_code=res.exit_code, ok=False,
            stdout=res.stdout, stderr=res.stderr,
        ).output_hash

    assert once() == once(), "deux executions identiques doivent donner la meme empreinte"


def test_le_bac_a_sable_reste_fonctionnel_apres_normalisation():
    """La normalisation ne doit pas masquer les vraies erreurs."""
    res = Sandbox(timeout=20).run_python("assert 1 == 2, 'vraie assertion'")
    assert res.exit_code != 0
    assert "vraie assertion" in res.stderr


# --------------------------------------------------------------------------- #
# 3. Invariant central : un harness amplifie, il ne cree pas de connaissance
# --------------------------------------------------------------------------- #


def test_le_gain_est_multiplicatif_et_non_additif():
    """Un bonus ADDITIF ferait reussir un modele de competence nulle des qu'on lui
    donne un retour d'erreur — c'est-a-dire un harness capable d'inventer du savoir
    absent. C'est l'inverse de la these du projet, et un modele de simulation qui
    viole cette these fausse toutes les mesures qui en decoulent."""
    from jio.providers.simulated import Persona, SimulatedProvider

    p = SimulatedProvider(persona=Persona("test"))
    assert p._amplify(0.0, 0.15) == 0.0, "a competence nulle, un avertissement ne peut rien"
    assert p._amplify(0.0, 1.0) == 0.0
    assert p._amplify(0.4, 0.15) > 0.4, "a competence non nulle, l'effet doit exister"
    assert p._amplify(0.4, 0.15) <= 1.0
    assert p._amplify(1.0, 0.15) == 1.0


def test_un_modele_qui_se_trompe_toujours_abstient_toujours():
    """Bout-en-bout : competence 0.0 + memoire remplie + avertissement actif
    -> le systeme doit ABSTENIR, jamais livrer."""
    from jio.bench.tasks import TASKS_BY_ID
    from jio.cli import _simulated_engine
    from jio.core.types import Mission, MissionStatus
    from jio.learn import FailureMemory
    from jio.loop.engine import WorkItem

    task = TASKS_BY_ID["parse_duration"]
    memory = FailureMemory()
    memory.record(
        objective=task.objective, symptom="regle R-002 non satisfaite",
        root_cause="exemple de test", correct_fix="n/a", guard="regle R-002",
    )
    engine = _simulated_engine(task, skill=0.0, seed=0, max_rounds=3)
    engine.memory = memory
    for provider in engine.generators:
        if hasattr(provider, "warning_gain"):
            provider.warning_gain = 0.99  # meme un avertissement enorme
    report = engine.run(
        Mission(objective=task.objective, max_rounds=3),
        WorkItem(objective=task.objective, entrypoint=task.entrypoint,
                 checks=dict(task.checks), spec=task.spec()),
    )
    assert report.status is MissionStatus.ABSTAINED
    assert report.passed < report.total_checks
