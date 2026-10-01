"""Un temoin doit PROUVER QU'IL PEUT ECHOUER — et le harness doit pouvoir le redemander.

Defaut trouve par la mesure, pas par la lecture : avec des temoins imparfaits — le regime REEL
d'une mission sans oracle, ou les tests sont ecrits par le modele — un instrument faux fait
echouer TOUS les candidats, y compris les bons, et le harness n'a plus rien a livrer. Mesure a
60 % de fidelite de traduction : **15 missions sur 15 en abstention**. Le moteur re-demandait des
CANDIDATS quand la preuve echouait ; il ne re-demandait jamais l'INSTRUMENT.

La correction ne demande aucune confiance supplementaire, et c'est ce qui la rend utilisable :
chaque temoin doit venir avec une implementation de reference et une contrefacon, et le harness
les EXECUTE avant que le temoin serve a quoi que ce soit.

    le test PASSE sur la reference fournie avec lui   -> sinon il se contredit ;
    le test ECHOUE sur la contrefacon fournie avec lui -> sinon il ne prouve rien.

Un instrument refuse est redemande UNE fois, avec son motif de refus — et le fait est journalise,
parce qu'un instrument repare n'est pas l'instrument du premier essai.
"""

from __future__ import annotations

import json

import pytest

from jio.core.types import Rule, RuleKind, Spec
from jio.providers.base import Completion
from jio.spec.witness import traduire
from jio.verify.executable import Sandbox

SPEC = Spec(
    mission="ecrire sum_even(nums)",
    rules=(
        Rule(id="R-001", statement="la somme des pairs est correcte", kind=RuleKind.PROPERTY),
    ),
)

REFERENCE = "def sum_even(nums):\n    return sum(n for n in nums if n % 2 == 0)\n"
CONTREFACON = "def sum_even(nums):\n    return sum(n for n in nums if n % 2 == 1)\n"
BON_TEST = "assert sum_even([1, 2, 3, 4]) == 6, f'{sum_even([1,2,3,4])} != 6'"
#: Le meme test lu a l'envers : il ECHOUE sur la reference et PASSE sur la contrefacon.
TEST_INVERSE = "assert sum_even([1, 2, 3, 4]) == 4, f'{sum_even([1,2,3,4])} != 4'"
#: Un test qui passe sur les DEUX implementations : il ne distingue rien.
TEST_AVEUGLE = "assert isinstance(sum_even([2]), int), 'pas un entier'"


def _reponse(test: str, reference: str = REFERENCE, contrefacon: str = CONTREFACON) -> str:
    return json.dumps({"R-001": {"test": test, "reference": reference, "contrefacon": contrefacon}})


class FauxTraducteur:
    """Un modele qui rend les reponses preparees, dans l'ordre, et compte ses appels."""

    name = "faux"
    model = "faux-1"

    def __init__(self, reponses: list[str]) -> None:
        self.reponses = reponses
        self.appels = 0

    def complete(self, messages, *, temperature=0.0, max_tokens=2048, seed=None):
        index = min(self.appels, len(self.reponses) - 1)
        self.appels += 1
        return Completion(text=self.reponses[index], model=self.model, provider=self.name)


@pytest.fixture()
def bac() -> Sandbox:
    return Sandbox(timeout=20)


def test_un_triplet_coherent_est_accepte_et_marque_valide(bac: Sandbox) -> None:
    """Le cas nominal : le temoin passe sur sa reference, echoue sur sa contrefacon."""
    traducteur = FauxTraducteur([_reponse(BON_TEST)])
    resultat = traduire(SPEC, traducteur, entrypoint="sum_even", controle=True, sandbox=bac)
    assert set(resultat.tests) == {"R-001"}
    assert resultat.valides == frozenset({"R-001"})
    assert not resultat.incoherents


def test_un_test_qui_se_contredit_est_refuse_avant_de_juger(bac: Sandbox) -> None:
    """Le coeur du mecanisme : un temoin faux ne doit juger AUCUN candidat.

    `TEST_INVERSE` echoue sur la reference fournie avec lui. Avant cette porte, il entrait tel
    quel : il faisait echouer tous les candidats, et le harness s'abstenait — en accusant le
    porteur d'un defaut qui etait celui de l'instrument.
    """
    traducteur = FauxTraducteur([_reponse(TEST_INVERSE)])
    resultat = traduire(SPEC, traducteur, entrypoint="sum_even", controle=True, sandbox=bac)
    assert "R-001" not in resultat.tests, "un temoin qui se contredit ne doit pas etre utilise"
    assert "R-001" in resultat.incoherents
    assert "ECHOUE sur l'implementation de reference" in resultat.incoherents["R-001"]


def test_un_test_qui_passe_sur_la_contrefacon_est_refuse(bac: Sandbox) -> None:
    """Un temoin que rien ne fait echouer ne prouve rien : il est refuse pour cette raison."""
    traducteur = FauxTraducteur([_reponse(TEST_AVEUGLE)])
    resultat = traduire(SPEC, traducteur, entrypoint="sum_even", controle=True, sandbox=bac)
    assert "R-001" not in resultat.tests
    assert "PASSE sur la contrefacon" in resultat.incoherents["R-001"]


def test_la_reparation_redemande_l_instrument_et_le_declare(bac: Sandbox) -> None:
    """Un instrument refuse est redemande UNE fois, et le fait est dit.

    Deux appels ne sont pas un appel : `relance` et `appels` le portent, sinon la comparaison a
    budget egal — la seule qui compte — deviendrait ininterpretable.
    """
    traducteur = FauxTraducteur([_reponse(TEST_INVERSE), _reponse(BON_TEST)])
    resultat = traduire(SPEC, traducteur, entrypoint="sum_even", controle=True, sandbox=bac)
    assert set(resultat.tests) == {"R-001"}
    assert resultat.reparations == frozenset({"R-001"})
    assert resultat.relance is True
    assert resultat.appels == 2, "la reparation doit etre comptee, pas offerte"


def test_la_reparation_ne_sert_pas_a_choisir_un_temoin_complaisant(bac: Sandbox) -> None:
    """Le garde-fou : reparer ne doit JAMAIS accepter un instrument que rien ne met en echec.

    Sans cette garantie, « reparer l'instrument » deviendrait « redemander jusqu'a ce qu'un
    temoin laisse passer » — exactement l'exploit que ce depot existe pour empecher. Ici le
    modele repond DEUX fois avec un test aveugle : rien n'est accepte, et la regle reste non
    prouvee plutot que faussement prouvee.
    """
    traducteur = FauxTraducteur([_reponse(TEST_AVEUGLE), _reponse(TEST_AVEUGLE)])
    resultat = traduire(SPEC, traducteur, entrypoint="sum_even", controle=True, sandbox=bac)
    assert resultat.tests == {}
    assert resultat.reparations == frozenset()
    assert "R-001" in resultat.incoherents


def test_une_reference_illisible_est_refusee_avec_sa_raison(bac: Sandbox) -> None:
    """Une reference qui ne definit pas l'entree, ou qui sort du bac a sable, est refusee."""
    traducteur = FauxTraducteur([_reponse(BON_TEST, reference="x = 1\n")])
    resultat = traduire(SPEC, traducteur, entrypoint="sum_even", controle=True, sandbox=bac)
    assert "R-001" not in resultat.tests
    assert "ne definit pas" in resultat.incoherents["R-001"]

    traducteur = FauxTraducteur([_reponse(BON_TEST, contrefacon="def sum_even(n):\n    import socket\n")])
    resultat = traduire(SPEC, traducteur, entrypoint="sum_even", controle=True, sandbox=bac)
    assert "R-001" not in resultat.tests
    assert "fragment interdit" in resultat.incoherents["R-001"]


def test_sans_bac_a_sable_rien_n_est_declare_valide() -> None:
    """Sans moyen d'executer, on refuse plutot que de faire semblant.

    Un instrument non mis a l'epreuve n'est pas un instrument valide : le declarer tel serait
    exactement le raccourci que ce module existe pour interdire.
    """
    traducteur = FauxTraducteur([_reponse(BON_TEST)])
    resultat = traduire(SPEC, traducteur, entrypoint="sum_even", controle=True, sandbox=None)
    assert resultat.tests == {}, "un temoin non mis a l'epreuve ne doit pas servir a juger"
    raison = resultat.refuses.get("R-001", "") + resultat.incoherents.get("R-001", "")
    assert "bac a sable" in raison, f"le refus doit dire pourquoi : {raison!r}"


def test_le_controle_est_desactivable_et_retrouve_l_ancien_comportement(bac: Sandbox) -> None:
    """`controle=False` : le temoin est utilise tel quel, et declare NON valide.

    Le drapeau existe pour que la comparaison soit possible : « avec » et « sans » controle,
    memes missions — sinon on ne saurait pas ce que le controle apporte.
    """
    traducteur = FauxTraducteur([_reponse(BON_TEST)])
    resultat = traduire(SPEC, traducteur, entrypoint="sum_even", controle=False)
    assert set(resultat.tests) == {"R-001"}
    assert resultat.valides == frozenset(), "sans mise a l'epreuve, rien n'est valide"


def test_le_journal_du_moteur_porte_les_instruments(bac: Sandbox) -> None:
    """Le moteur doit DIRE quels temoins ont ete mis a l'epreuve, refuses, ou repares.

    Un rapport qui annonce « 3/3 regles satisfaites » sans dire avec quels instruments demande
    qu'on le croie. On interroge donc l'etape de traduction elle-meme, sur un moteur reel, et
    on lit l'evenement ecrit au journal : les trois listes y sont.
    """
    import tempfile
    from pathlib import Path

    from jio.bench.tasks import TASKS_BY_ID
    from jio.bench.temoins import TraducteurSimule
    from jio.core.journal import Journal
    from jio.loop.engine import Engine, EngineConfig, WorkItem

    with tempfile.TemporaryDirectory() as dossier:
        tache = TASKS_BY_ID["sum_even"]
        journal = Journal(Path(dossier) / "j.jsonl")
        moteur = Engine(
            config=EngineConfig(temoins=True, witness_control=True),
            journal=journal,
            generators=[TraducteurSimule(taches=[tache], fidelite=0.5)],
        )
        moteur._temoins_de_la_spec(  # noqa: SLF001 — on interroge l'etape, pas tout le run
            tache.spec(),
            WorkItem(objective=tache.objective, entrypoint=tache.entrypoint, checks={}),
            {"calls": 0},
        )
        evenements = [
            json.loads(l) for l in Path(journal.path).read_text().splitlines() if l.strip()
        ]
    temoins = [e for e in evenements if e.get("kind") == "temoins"]
    assert temoins, "le journal doit porter la traduction des regles"
    charge = temoins[-1]["payload"]
    for cle in ("valides", "incoherents", "reparations"):
        assert cle in charge, f"le journal doit porter `{cle}` : {sorted(charge)}"


def test_un_aveu_se_memorise_ne_PROUVE_rien_et_ne_se_repaie_pas(tmp_path) -> None:
    """Le savoir NEGATIF est un savoir : il se garde, et il ne se confond jamais avec une preuve.

    Sans cette memoire, une regle que le modele declare non testable etait redemandee a CHAQUE
    mission identique pour recevoir la meme reponse — un cout qui ne s'arrete jamais. Le
    garde-fou est dans l'autre sens : un aveu memorise ne doit pas devenir une regle « prouvee »,
    sinon la memoire fabriquerait exactement ce que le projet refuse.
    """
    from jio.spec.library import BibliothequeTemoins, empreinte_regle

    journal = tmp_path / "temoins.jsonl"
    biblio = BibliothequeTemoins(path=journal)
    spec = SPEC
    empreintes = {r.id: empreinte_regle(r.id, r.statement) for r in spec.rules}

    assert biblio.retenir_aveux(
        objectif="moyenne", empreintes=empreintes,
        aveux={"R-001": "aucun oracle de reference"}, modele="modele-A",
    ) == 1

    # Meme modele : l'aveu revient, et la mission ne repose pas la question.
    repris = BibliothequeTemoins(path=journal).rappeler_aveux("moyenne", empreintes, "modele-A")
    assert repris == {"R-001": "aucun oracle de reference"}

    # Autre modele : il n'herite PAS de l'aveu d'un autre. On ne fait pas dire a un nouveau
    # venu ce qu'un ancien a avoue.
    assert BibliothequeTemoins(path=journal).rappeler_aveux(
        "moyenne", empreintes, "modele-B",
    ) == {}

    # Un enonce qui change ne retrouve rien : la memoire ne s'applique pas a une autre regle.
    autres = {"R-001": empreinte_regle("R-001", "enonce different")}
    assert BibliothequeTemoins(path=journal).rappeler_aveux("moyenne", autres, "modele-A") == {}

    # Et l'aveu reste ce qu'il est : une entree de memoire, jamais un temoin.
    biblio_rechargee = BibliothequeTemoins(path=journal)
    assert biblio_rechargee.rappeler("moyenne", empreintes) == {}
    assert "1 aveu(s) memorise(s)" in biblio_rechargee.resume()


def test_une_regle_dont_l_instrument_est_REFUSE_ne_part_pas_SANS_RESERVE() -> None:
    """Le cas qui a fait echouer le banc d'ablation, verrouille ici en plus petit.

    Mesure a l'origine : sur `safe_divide` sans oracle, le controle a refuse les temoins de
    deux regles sur quatre. L'ancien regime les ACCEPTAIT, l'artefact les ratait, et le
    mecanisme « temoin que personne ne passe » declenchait la reserve. En refusant l'instrument
    plus tot, on a supprime ce signal : la meme mission est passee « livree SANS reserve » avec
    un artefact FAUX — l'invariant du depot casse par une amelioration.

    Ce test construit le meme cas, plus petit : deux regles, l'instrument de la seconde est
    refuse par execution. La livraison doit porter une reserve nommant la regle.
    """
    from jio.bench.tasks import TASKS_BY_ID
    from jio.core.types import Mission, MissionStatus
    from jio.loop.engine import Engine, EngineConfig, WorkItem

    tache = TASKS_BY_ID["sum_even"]
    bac = Sandbox(timeout=20)
    # Un traducteur qui rend un temoin VALIDE pour R-001 et un instrument CONTREDIT pour R-003 :
    # le test echoue sur la reference fournie avec lui, donc il est refuse a l'execution.
    class TraducteurRefusant:
        name = "refusant"
        model = "refusant-1"

        def complete(self, messages, *, temperature=0.0, max_tokens=2048, seed=None):
            return Completion(text=json.dumps({
                "R-001": {
                    "test": "assert sum_even([1, 2, 3, 4]) == 6",
                    "reference": "def sum_even(nums):\n    return sum(n for n in nums if n % 2 == 0)",
                    "contrefacon": "def sum_even(nums):\n    return 0",
                },
                "R-003": {
                    "test": "assert sum_even([-4, -3, 2]) == 42",
                    "reference": "def sum_even(nums):\n    return sum(n for n in nums if n % 2 == 0)",
                    "contrefacon": "def sum_even(nums):\n    return 1",
                },
            }), model=self.model, provider=self.name)

    moteur = Engine(
        config=EngineConfig(temoins=True, witness_control=True, max_rounds=2),
        generators=[TraducteurRefusant()],
    )
    rapport = moteur.run(
        Mission(objective=tache.objective, id="refus-1", max_rounds=2),
        WorkItem(objective=tache.objective, entrypoint=tache.entrypoint, checks={},
                 spec=tache.spec()),
    )
    # Le montage doit etre celui qu'on croit : un temoin MIS A L'EPREUVE, un instrument REFUSE.
    te = moteur._temoignage
    assert te is not None
    assert set(te.valides) == {"R-001"}, f"R-001 doit etre eprouve : {sorted(te.valides)}"
    assert "R-003" in te.incoherents, f"R-003 doit etre refuse : {dict(te.incoherents)}"
    assert "R-003" not in te.tests

    # Quoi qu'il arrive, la regle non couverte doit etre NOMMEE dans le rapport.
    textes = " ".join(f.message for f in rapport.findings)
    assert "R-003" in textes, f"la regle sans temoin doit etre declaree : {textes[:300]}"
    assert rapport.status is not MissionStatus.DELIVERED, (
        "livrer SANS reserve une mission dont une regle n'a aucun temoin reviendrait a dire "
        "que la specification est couverte alors qu'elle ne l'est pas"
    )


def test_la_memoire_ne_blanchit_pas_un_temoin_non_eprouve(tmp_path) -> None:
    """Ce qui entre comme « accepte sans preuve » doit ressortir comme tel.

    La memoire servait du meme air un temoin qui avait prouve qu'il peut echouer et un temoin
    seulement accepte : elle AUGMENTAIT donc silencieusement la confiance de ce qu'elle servait.
    Une entree ecrite sans mention (version anterieure, ou ecriture directe) ressort NON
    EPROUVEE — jamais l'inverse.
    """
    from jio.spec.library import BibliothequeTemoins, empreinte_regle

    journal = tmp_path / "temoins.jsonl"
    biblio = BibliothequeTemoins(path=journal)
    deux = Spec(
        mission="moyenne",
        rules=(
            Rule(id="R-001", statement="moyenne nominale", kind=RuleKind.PROPERTY),
            Rule(id="R-002", statement="deux valeurs egales", kind=RuleKind.BOUNDARY),
        ),
    )
    empreintes = {r.id: empreinte_regle(r.id, r.statement) for r in deux.rules}

    biblio.retenir(
        objectif="moyenne",
        empreintes=empreintes,
        correspondance={"R-001": "assert mean([1, 2]) == 1.5"},
        mission_id="m1",
    )  # `eprouves` absent : rien n'a ete prouve
    biblio.retenir(
        objectif="moyenne",
        empreintes=empreintes,
        correspondance={"R-002": "assert mean([2, 2]) == 2"},
        eprouves={"R-002": True},
        mission_id="m2",
    )

    repris = BibliothequeTemoins(path=journal)
    assert repris.rappeler("moyenne", empreintes).keys() == {"R-001", "R-002"}
    etats = repris.rappeler_eprouves("moyenne", empreintes)
    assert etats["R-002"] is True, "un temoin mis a l'epreuve reste mis a l'epreuve"
    assert etats["R-001"] is False, (
        "une entree sans mention doit ressortir NON EPROUVEE : par defaut, rien n'est prouve"
    )


def test_la_memoire_n_accepte_QUE_des_temoins_mis_a_l_epreuve(tmp_path) -> None:
    """Le trajet COMPLET : traduction -> memoire -> mission suivante.

    Le test unitaire ci-dessus verifie le magasin ; celui-ci verifie le CABLAGE, parce que
    c'est le cablage qui decide de ce que le rapport raconte. Un traducteur qui ne fournit
    jamais de contrefacon (l'ancien format) produit des temoins ACCEPTES mais NON EPROUVES :
    ils jugent la mission en cours — ils ne valent rien pour les suivantes. La memoire les
    refuse donc, et la seconde mission identique REPAIE sa traduction : c'est le prix, assume,
    de ne pas laisser une memoire augmenter la confiance de ce qu'elle sert.
    """
    from jio.bench.tasks import TASKS_BY_ID
    from jio.cli import _simulated_engine
    from jio.core.types import Mission
    from jio.loop.engine import WorkItem
    from jio.spec.library import BibliothequeTemoins

    class TraducteurSansTriplet:
        """Repond a l'ANCIEN format : un test par regle, sans reference ni contrefacon."""

        name = "simple"
        model = "simple-1"

        def complete(self, messages, *, temperature=0.0, max_tokens=2048, seed=None):
            return Completion(
                text=json.dumps({rid: t for rid, t in tache.checks.items()}),
                model=self.model, provider=self.name,
            )

    tache = TASKS_BY_ID["sum_even"]
    chemin = tmp_path / "temoins.jsonl"
    moteur: object | None = None

    def une_mission(numero: int):
        nonlocal moteur
        moteur = _simulated_engine(
            tache, skill=0.85, seed=0, max_rounds=2, temoins=True,
            traducteur=TraducteurSansTriplet(),
        )
        moteur.bibliotheque = BibliothequeTemoins(path=chemin)
        return moteur.run(
            Mission(objective=tache.objective, id=f"m{numero}", max_rounds=2),
            WorkItem(objective=tache.objective, entrypoint=tache.entrypoint, checks={},
                     spec=tache.spec()),
        )

    premiere = une_mission(1)
    assert premiere.status.value.startswith("delivered"), premiere.abstention_reason
    assert moteur._temoignage.non_eprouves, (
        "un test sans contrefacon est accepte, mais il doit etre NOMME non eprouve"
    )
    assert BibliothequeTemoins(path=chemin).size == 0, (
        "un temoin NON EPROUVE ne doit pas entrer dans la memoire : rien n'a montre qu'il "
        "peut echouer, donc il ne peut pas prouver la mission suivante"
    )

    une_mission(2)
    evenements = [e for e in moteur.journal.events() if e.kind == "temoins"]
    dernier = evenements[-1].payload
    assert dernier.get("source") != "bibliotheque", (
        "la memoire doit avoir refuse ces temoins : la seconde mission les repaie"
    )
    assert moteur._temoignage.non_eprouves, "et elle les requalifie NON EPROUVES"
