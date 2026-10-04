"""Tests de la comparaison differentielle des candidats.

Le trou comble, mesure : quand plusieurs candidats satisfont la specification, le
moteur choisissait entre eux par l'ORDRE DE GENERATION (`_better` prend le dernier
dont le ratio est au moins egal). Avec une specification qui ne couvre que le cas
nominal, le livrable changeait donc selon l'ordre d'arrivee des reponses — et rien ne
le signalait. Deux candidats payes, un desaccord visible, et un silence.

Trois comportements sont verrouilles ici :

1. **detection** : les candidats sont executes sur les memes entrees derivees et leurs
   resultats sont compares ;
2. **aveu** : tout desaccord devient un constat nomme, avec l'entree exacte et les
   valeurs obtenues — jamais bloquant, parce qu'un desaccord peut porter sur un
   comportement non specifie ;
3. **choix informe** : quand une majorite stricte de candidats s'accorde, c'est elle
   qui est livree, au lieu du dernier arrive.

Le corpus `evidence/divergence/` est versionne : la mesure est rejouable.
"""

from __future__ import annotations

import pathlib

import pytest

from jio.core.types import Mission, Rule, RuleKind, Spec
from jio.loop.engine import Engine, EngineConfig, WorkItem
from jio.providers.base import Completion
from jio.verify.divergence import comparer

REPO = pathlib.Path(__file__).resolve().parents[1]
CORPUS = REPO / "evidence" / "divergence"
JUSTE = (CORPUS / "candidat_juste.py").read_text(encoding="utf-8")
FAUX = (CORPUS / "candidat_faux.py").read_text(encoding="utf-8")


def test_le_corpus_de_divergence_est_present():
    assert CORPUS.is_dir(), "corpus manquant : la mesure ne serait plus rejouable"
    assert "sum(nums) / len(nums)" in JUSTE
    assert "sum(nums) // len(nums)" in FAUX


def _juste(source: str) -> bool:
    """Oracle de mesure : `mean([1, 2])` vaut 1.5 (vraie moyenne) ou 1.0 (entiere).

    Un premier oracle ecrit trop vite comparait `mean([2, 4])` : les deux
    implementations y rendent 3, et la mesure ne mesurait donc RIEN. C'est le genre
    d'erreur que ce projet existe pour attraper.
    """
    espace: dict = {}
    try:
        exec(source, espace)  # noqa: S102 - corpus de test, source de confiance
    except Exception:
        return False
    try:
        return abs(espace["mean"]([1, 2]) - 1.5) < 1e-9
    except Exception:
        return False


# --------------------------------------------------------------------------- #
# Le module
# --------------------------------------------------------------------------- #

def test_deux_candidats_qui_divergent_sont_detectes():
    divergences, majoritaire = comparer([("a", JUSTE), ("b", FAUX)], "mean")
    assert divergences, "le desaccord n'a pas ete vu"
    assert majoritaire == "", "deux candidats ne peuvent pas former de majorite stricte"
    # Le constat doit etre exploitable : l'entree ET les deux valeurs.
    rendu = divergences[0].render()
    assert "->" in rendu and "a:" in rendu and "b:" in rendu


def test_trois_candidats_dont_deux_identiques_donnent_une_majorite():
    divergences, majoritaire = comparer(
        [("a", JUSTE), ("b", JUSTE), ("c", FAUX)], "mean")
    assert divergences
    assert majoritaire in {"a", "b"}, majoritaire


def test_tous_differents_donne_le_desaccord_sans_majorite_forcée():
    """Trois comportements distincts : aucun n'est prefere, faute de majorite stricte.

    Trois implementations reellement differentes (division entiere, arrondi, division
    exacte) : chacune rend une valeur differente sur `[1, 2]`, donc il n'existe pas de
    majorite — et le module doit le dire au lieu de fabriquer un gagnant.
    """
    division_entiere = FAUX
    arrondi = JUSTE.replace("sum(nums) / len(nums)", "round(sum(nums) / len(nums))")
    exacte = JUSTE

    divergences, majoritaire = comparer(
        [("a", division_entiere), ("b", arrondi), ("c", exacte)], "mean")
    assert divergences, "trois comportements differents doivent produire un desaccord"
    assert majoritaire == "", (
        f"aucune majorite stricte n'existe ici, mais « {majoritaire} » a ete designe"
    )

def test_des_candidats_identiques_ne_produisent_aucun_desaccord():
    divergences, majoritaire = comparer([("a", JUSTE), ("b", JUSTE)], "mean")
    assert divergences == ()
    assert majoritaire == ""


def test_sans_domaine_derive_aucune_comparaison():
    """Deux fonctions non annotees et sans exemple : rien a explorer, et on le dit."""
    divergences, majoritaire = comparer(
        [("a", "def f(x):\n    return x\n"), ("b", "def f(x):\n    return x + 1\n")], "f")
    assert divergences == ()
    assert majoritaire == ""


def test_un_candidat_qui_plante_est_observe_sans_tout_casser():
    """Un candidat qui leve une exception reste comparable : c'est une observation."""
    fragile = '''def moitie(valeurs: list[int]) -> int:
    """Moitie.

    >>> moitie([2, 4])
    3
    """
    return valeurs[0]
'''
    solide = '''def moitie(valeurs: list[int]) -> int:
    """Moitie.

    >>> moitie([2, 4])
    3
    """
    return sum(valeurs) // 2
'''
    divergences, _ = comparer([("a", fragile), ("b", solide)], "moitie")
    assert divergences, "les deux comportements different enormement"


def test_la_comparaison_est_deterministe():
    """Meme entree, meme resultat : une comparaison non rejouable ne prouve rien."""
    premier = comparer([("a", JUSTE), ("b", FAUX)], "mean")
    second = comparer([("a", JUSTE), ("b", FAUX)], "mean")
    assert premier == second


# --------------------------------------------------------------------------- #
# Le moteur
# --------------------------------------------------------------------------- #

class _Candidats:
    """Rend les sources fournies, dans l'ordre, a chaque appel."""

    name = "sim"
    model = "sim-1"

    def __init__(self, sources: list[str]) -> None:
        self.sources = list(sources)
        self.index = 0

    def complete(self, messages, *, temperature=0.0, max_tokens=2048, seed=None):
        source = self.sources[self.index % len(self.sources)]
        self.index += 1
        return Completion(
            text="```python\n" + source + "```\n", prompt_tokens=10,
            completion_tokens=20, model=self.model,
        )


SPEC = Spec(
    mission="moyenne",
    rules=(Rule(id="R-001", statement="moyenne nominale", kind=RuleKind.PROPERTY),),
)
CHECKS = {"R-001": "assert mean([1, 2, 3]) == 2.0, f'nominal: {mean([1,2,3])}'"}


def _mission(sources: list[str], *, differential: bool):
    modele = _Candidats(sources)
    engine = Engine(generators=[modele], config=EngineConfig(
        max_rounds=1, candidates_per_round=len(sources), self_check=True,
        differential=differential, mutation_gate=False,
    ))
    rapport = engine.run(
        Mission(objective="moyenne", id="divergence"),
        WorkItem(objective="moyenne", entrypoint="mean", checks=CHECKS, spec=SPEC),
    )
    return rapport, engine


@pytest.mark.parametrize("sources", [
    [FAUX, JUSTE, JUSTE],
    [JUSTE, FAUX, JUSTE],
    [JUSTE, JUSTE, FAUX],
], ids=["faux en premier", "faux au milieu", "faux en dernier"])
def test_le_choix_ne_depend_plus_de_l_ordre_d_arrivee(sources):
    """Le livrable doit etre JUSTE quel que soit l'ordre de generation.

    Avant : `_better` prenait le dernier candidat de ratio maximal, donc le livrable
    changeait avec l'ordre (mesure : « faux en premier » livrait le faux).
    """
    rapport, _ = _mission(sources, differential=True)
    assert _juste(rapport.subject or ""), (
        "un candidat faux a ete livre : "
        f"{[l for l in (rapport.subject or '').splitlines() if 'return' in l]}"
    )


def test_le_desaccord_est_avoue_avec_l_entree_exacte():
    """Ce qui levait le silence : le constat nomme l'entree et les valeurs."""
    rapport, _ = _mission([FAUX, JUSTE, JUSTE], differential=True)
    constats = [f for f in rapport.findings if f.agent == "divergence"]
    assert constats, "aucun constat : le desaccord serait reste silencieux"
    constat = constats[0]
    assert constat.evidence, "un desaccord sans entree citee n'est pas exploitable"
    assert constat.counterexample, "l'entree divergente doit etre nommee"
    assert not constat.blocking, (
        "un desaccord ne doit JAMAIS bloquer : il peut porter sur un comportement "
        "non specifie, ou deux implementations correctes peuvent differer"
    )


def test_sans_comparaison_le_comportement_reste_inchange():
    """Le reglage a un effet observable, et le desaccord redevient silencieux."""
    rapport, _ = _mission([FAUX, JUSTE, JUSTE], differential=False)
    assert not [f for f in rapport.findings if f.agent == "divergence"]


def test_le_desaccord_est_journalise():
    """Une preuve non tracee n'existe pas : l'evenement est au journal."""
    _, engine = _mission([FAUX, JUSTE, JUSTE], differential=True)
    evenements = [e for e in engine.journal.events() if e.kind == "divergence"]
    assert evenements, "aucun evenement `divergence` au journal"
    charge = evenements[0].payload
    assert charge.get("cas", 0) >= 1
    assert charge.get("detail"), charge
