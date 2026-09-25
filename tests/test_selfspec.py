"""Tests de l'axe auto-coherence : un artefact ne doit pas mentir sur lui-meme.

Regime teste, celui de la vraie vie : la specification de la mission est
**incomplete**. Le harness ne peut donc pas tout prouver — mais il reste une source
de verite qu'on n'exploitait pas : ce que l'artefact AFFIRME de lui-meme. Ses exemples
`>>>` et ses annotations sont des affirmations executables, ecrites par son auteur.

Mesure (corpus `evidence/selfspec/`, specification faible) : 2 defauts sur 4 rattrapes,
0 faux rejet. Les deux defauts non rattrapes sont ceux dont la documentation decrit
FIDELEMENT le mauvais comportement : aucune methode locale ne peut les voir, et le
dire fait partie de la preuve.

Deuxieme moitie du chantier, trouvee en verifiant le premier : le rejet etait bien
prononce, mais le modele recevait « aucun echec » — il devait deviner quoi corriger.
Le motif est desormais transmis tel quel comme retour d'echec structuré.
"""

from __future__ import annotations

import pathlib

import pytest

from jio.core.types import Mission, Rule, RuleKind, Spec
from jio.loop.engine import Engine, EngineConfig, WorkItem
from jio.providers.base import Completion

REPO = pathlib.Path(__file__).resolve().parents[1]
CORPUS = REPO / "evidence" / "selfspec"

#: Le contrat REEL, garde cote oracle : c'est lui qui dit qui a raison, jamais la
#: documentation (sinon on se contenterait de croire l'artefact sur parole).
def _contrat_est_tenu(source: str) -> list[str]:
    espace: dict = {}
    try:
        exec(source, espace)  # noqa: S102 - corpus de test, source de confiance
    except Exception as exc:  # pragma: no cover - les corpus compilent
        return [f"ne s'execute pas : {exc}"]
    mean = espace.get("mean")
    if not callable(mean):
        return ["mean absent"]
    manques: list[str] = []
    if mean([1, 2, 3]) != 2.0:
        manques.append("cas nominal")
    if mean([2, 4]) != 3.0:
        manques.append("deux elements")
    if mean([1.5, 2.5]) != 2.0:
        manques.append("valeurs decimales")
    try:
        mean([])
    except ValueError:
        pass
    except Exception as exc:
        manques.append(f"mauvais type d'erreur ({type(exc).__name__})")
    else:
        manques.append("liste vide acceptee sans erreur")
    return manques


def _spec_faible() -> tuple[Spec, dict[str, str]]:
    """Une specification qui ne couvre QUE le cas nominal — le regime incomplet."""
    spec = Spec(
        mission="moyenne",
        rules=(Rule(id="R-001", statement="Moyenne correcte au nominal", kind=RuleKind.PROPERTY),),
    )
    return spec, {"R-001": "assert mean([1, 2, 3]) == 2.0, f'nominal: {mean([1,2,3])}'"}


def _fichiers() -> list[pathlib.Path]:
    return sorted(CORPUS.glob("*.py"))


def test_le_corpus_est_present():
    assert len(_fichiers()) == 5, [p.name for p in _fichiers()]


@pytest.mark.parametrize("fichier", _fichiers(), ids=lambda p: p.name)
def test_le_verdict_de_l_oracle_est_coherent_avec_le_nom_du_fichier(fichier):
    """Le corpus doit rester honnete : `correct.py` est conforme, les autres non.

    Sans ce test, un corpus pourrait « passer » parce que ses fichiers ont ete
    modifies par erreur, et la mesure ne prouverait plus rien.
    """
    manques = _contrat_est_tenu(fichier.read_text(encoding="utf-8"))
    if fichier.name == "correct.py":
        assert not manques, f"correct.py devrait tenir le contrat : {manques}"
    else:
        assert manques, f"{fichier.name} devrait echouer au contrat, mais il le tient"


def test_l_auto_controle_rattrape_les_artefacts_qui_mentent():
    """Les deux menteurs (division entiere, arrondi silencieux) sont rejetes.

    Leur docstring annonce `2.0`, leur code rend `2` : les deux ne peuvent pas etre
    vrais, et cette contradiction est detectable sans connaitre le contrat.
    """
    attendus = {"ment_sur_la_division.py", "arrondit_en_douce.py"}
    rattrapes = set()

    for fichier in _fichiers():
        source = fichier.read_text(encoding="utf-8")
        engine = Engine(generators=[], config=EngineConfig(self_check=True))
        conforme, motif = engine._contredit_sa_documentation(source, WorkItem(
            objective="moyenne", entrypoint="mean"))
        if not conforme:
            rattrapes.add(fichier.name)
            assert "docstring" in motif, motif

    assert attendus <= rattrapes, f"non rattrapes : {sorted(attendus - rattrapes)}"


def test_aucun_faux_rejet_sur_le_corpus():
    """ZERO artefact accuse a tort — c'est la condition pour oser activer l'axe."""
    faux_rejets = []

    for fichier in _fichiers():
        source = fichier.read_text(encoding="utf-8")
        if fichier.name == "correct.py" or _contrat_est_tenu(source) == []:
            engine = Engine(generators=[], config=EngineConfig(self_check=True))
            conforme, motif = engine._contredit_sa_documentation(
                source, WorkItem(objective="moyenne", entrypoint="mean"))
            if not conforme:
                faux_rejets.append((fichier.name, motif))

    assert not faux_rejets, faux_rejets


def test_les_artefacts_honnetes_sur_leur_propre_defaut_ne_sont_pas_rattrapes():
    """Ce que l'axe ne peut PAS faire, dit explicitement.

    `honnete_sur_son_comportement.py` documente correctement un comportement faux, et
    `docstring_coherente_contrat_faux.py` aussi. Aucune verification locale ne les voit :
    c'est le role de la specification de mission, ou de l'abstention. Le revendiquer
    autrement serait une preuve fabriquee.
    """
    for nom in ("honnete_sur_son_comportement.py", "docstring_coherente_contrat_faux.py"):
        source = (CORPUS / nom).read_text(encoding="utf-8")
        engine = Engine(generators=[], config=EngineConfig(self_check=True))
        conforme, _ = engine._contredit_sa_documentation(
            source, WorkItem(objective="moyenne", entrypoint="mean"))
        assert conforme, (
            f"{nom} : l'auto-controle ne doit PAS le rattraper (sa documentation est "
            "coherente) ; s'il le fait, c'est que la mesure a change de nature"
        )


# --------------------------------------------------------------------------- #
# La boucle complete : rejet, retour precis, reparation
# --------------------------------------------------------------------------- #

MENTEUR = '''def mean(nums: list[float]) -> float:
    """Moyenne.

    >>> mean([1, 2, 3])
    2.0
    """
    return sum(nums) // len(nums)
'''


class _ModeleQuiSeCorrige:
    """Rend un artefact qui ment sur lui-meme, puis se corrige au tour suivant."""

    name = "sim"
    model = "sim-1"

    def __init__(self, menteurs: int = 2) -> None:
        self.appels = 0
        self.prompts: list[str] = []
        self._menteurs = menteurs

    def complete(self, messages, *, temperature=0.0, max_tokens=2048, seed=None):
        self.appels += 1
        self.prompts.append(messages[-1].content if messages else "")
        texte = MENTEUR if self.appels <= self._menteurs else MENTEUR.replace(
            "// len(nums)", "/ len(nums)")
        return Completion(
            text="```python\n" + texte + "```\n", prompt_tokens=10,
            completion_tokens=20, model=self.model,
        )


def test_le_rejet_revient_au_modele_avec_la_contradiction_exacte():
    """Le point qui a manque la premiere fois.

    Le rejet etait prononce, mais la boucle ne transmettait que les echecs de la
    specification de MISSION — vides ici. Le modele recevait « aucun echec » et
    devait deviner. Mesure faite : 4 appels, livraison correcte, mais aucune
    reparation guidee. Le motif est maintenant transmis tel quel.
    """
    spec, checks = _spec_faible()
    modele = _ModeleQuiSeCorrige()
    engine = Engine(generators=[modele], config=EngineConfig(
        max_rounds=3, candidates_per_round=2, self_check=True))

    rapport = engine.run(
        Mission(objective="moyenne", id="auto-coherence"),
        WorkItem(objective="moyenne", entrypoint="mean", checks=checks, spec=spec),
    )

    assert rapport.status.value in ("delivered", "delivered_with_reservation"), rapport.status
    assert "/ len(nums)" in (rapport.subject or ""), "l'artefact livre reste le menteur"
    retours = [p for p in modele.prompts if "CONTREDIT" in p]
    assert retours, "le modele n'a jamais recu la contradiction : reparation aveugle"
    assert "docstring" in retours[0]
    assert "2.0" in retours[0] and "Got" in retours[0], (
        "le retour doit citer la promesse ET la valeur reellement obtenue"
    )


def test_le_controle_est_desactivable_et_le_comportement_redevient_permissif():
    """Un reglage qui n'a pas d'effet observable n'est pas un reglage."""
    spec, checks = _spec_faible()
    modele = _ModeleQuiSeCorrige(menteurs=99)   # il ne se corrigera jamais
    engine = Engine(generators=[modele], config=EngineConfig(
        max_rounds=2, candidates_per_round=1, self_check=False))

    rapport = engine.run(
        Mission(objective="moyenne", id="sans-controle"),
        WorkItem(objective="moyenne", entrypoint="mean", checks=checks, spec=spec),
    )

    assert "// len(nums)" in (rapport.subject or ""), (
        "controle desactive : le harness doit accepter ce que la spec accepte"
    )
    assert not [p for p in modele.prompts if "CONTREDIT" in p]
