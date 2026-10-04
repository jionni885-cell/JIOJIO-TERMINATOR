"""Tests de la matrice mutants x regles.

Ce que ces tests protegent
--------------------------
La matrice existe pour transformer un chiffre (« 1 mutant survivant ») en GESTE.
Elle serait nuisible si elle accusait la mauvaise partie : reprocher a une regle
qui n'a jamais execute la ligne de code de ne pas avoir vu le changement, c'est
envoyer le developpeur renforcer une regle qui n'y peut rien et laisser le trou de
specification ouvert. Les tests verrouillent donc trois choses :

  1. la LOCALISATION (le mutant sait quelle ligne a change, meme quand `ast.unparse`
     a reecrit la mise en forme) ;
  2. la JUSTESSE de l'accusation (aveugle = la regle a vu la ligne et l'a laissee
     passer ; hors-portee = la regle ne l'a jamais touchee, on ne l'accuse pas) ;
  3. le COUT (un mutant tue n'est jamais trace : seule une execution tracee par
     survivant, pas une par couple mutant-regle).

Mesures de reference relevees pendant le developpement, reutilisees ici :

  `median` (spec faible `is not None`) : 3/4 tues, R-002 « aveugle » avec le geste
  « rendre l'assertion falsifiable » ;
  `tariff` (une seule regle sur age=10) : le mutant `20 -> 21` de la ligne 4 est
  declare « hors-portee », et la reserve demande d'AJOUTER une regle.

Les tests de logique de decision utilisent un juge factice : ils sont deterministes
et ne lancent aucun sous-processus. Deux tests d'integration verifient que le vrai
`ExecutableProver` alimente correctement la matrice (traceur, lignes, verdicts).
"""

from __future__ import annotations

from jio.core.errors import FailClosed
from jio.core.types import Rule, RuleKind, Spec, Witness
from jio.verify.executable import (
    CouvertureRegle,
    ExecutableProver,
    ProverResult,
    Sandbox,
)
from jio.verify.matrice import (
    AVEUGLE,
    HORS_PORTEE,
    INCONCLUSIF,
    NON_MESURE,
    TUE,
    construire,
    controle_de_forme,
    formater,
)
from jio.verify.matrice import (
    assembler as _assembler,
)
from jio.verify.matrice import (
    regles_de_forme as _regles_de_forme,
)
from jio.verify.matrice import (
    resume as _resume,
)
from jio.verify.mutation import Mutation, mutate

MEDIAN = """def median(nums):
    s = sorted(nums)
    n = len(s)
    if n % 2 == 1:
        return s[n // 2]
    return (s[n // 2 - 1] + s[n // 2]) / 2
"""

#: Le mutant `20 -> 21` tombe sur la ligne 4, que la regle « age = 10 » n'atteint pas.
TARIFF = """def tariff(age):
    if age < 18:
        return 0
    return 20
"""

SPEC_FAIBLE = Spec(
    mission="test",
    rules=(
        Rule(id="R-001", statement="impair", kind=RuleKind.PROPERTY),
        Rule(id="R-002", statement="forme", kind=RuleKind.PROPERTY),
    ),
)
CHECKS_FAIBLES = {
    "R-001": "assert median([3, 1, 2]) == 2",
    "R-002": "assert median([1, 2, 3, 4]) is not None",
}


class _JugeFactice:
    """Un `ExecutableProver` scripte, sans sous-processus ni horloge."""

    def __init__(self, verdicts, couvertures=(), *, leve: Exception | None = None):
        self.verdicts = list(verdicts)
        self.couvertures = list(couvertures)
        self.leve = leve
        self.appels_preuve = 0
        self.appels_couverture = 0

    def prove(self, source, spec, **kwargs) -> ProverResult:
        self.appels_preuve += 1
        if self.leve is not None:
            raise self.leve
        ok = self.verdicts.pop(0) if self.verdicts else True
        temoins = tuple(
            Witness(rule_id=r.id, command="factice", exit_code=0 if ok else 1, ok=ok)
            for r in spec.rules
        )
        if ok:
            return ProverResult(witnesses=temoins)
        tueuse = spec.rules[0].id
        return ProverResult(
            witnesses=temoins,
            failures=(
                Witness(rule_id=tueuse, command="factice", exit_code=1, ok=False),
            ),
        )

    def couverture_regles(self, source, spec, **kwargs):
        self.appels_couverture += 1
        return self.couvertures.pop(0) if self.couvertures else {}


def _regle(*ids: str) -> Spec:
    return Spec(
        mission="test",
        rules=tuple(Rule(id=i, statement=i, kind=RuleKind.PROPERTY) for i in ids),
    )


# --------------------------------------------------------------------------- #
# Localisation du changement
# --------------------------------------------------------------------------- #


def test_mutants_de_median_sont_localises() -> None:
    """Sans la ligne, la matrice ne peut rien dire : elle doit etre renseignee."""
    mutants = mutate(MEDIAN, budget=4)
    assert mutants, "aucun mutant : le test ne prouverait rien"
    for mutant in mutants:
        assert 1 <= mutant.ligne <= len(mutant.source.splitlines()), (
            f"{mutant.label} : ligne {mutant.ligne} hors du texte mute"
        )


def test_la_ligne_designe_le_changement_dans_le_texte_mute() -> None:
    """`ast.unparse` reecrit la mise en forme : la ligne doit venir du texte MUTE.

    Ici le commentaire de la ligne 2 disparait a l'unparse : la ligne « 3 » de
    l'original est la ligne « 2 » du mutant. Mesurer la couverture avec la ligne
    d'origine reviendrait a regarder une ligne qui n'a pas bouge.
    """
    source = "def f(n):\n    # commentaire qui disparait a l'unparse\n    return n + 1\n"
    mutant = mutate(source, budget=1)[0]
    assert mutant.ligne == 2, "ligne 2 du texte MUTE"
    assert mutant.source.splitlines()[mutant.ligne - 1].strip() == "return n + 2"
    assert source.splitlines()[mutant.ligne - 1].strip() != "return n + 2", (
        "et c'est bien la ligne 3 de l'original qui a change"
    )
    assert source.splitlines()[2].strip() == "return n + 1"


def test_mutation_sans_effet_sur_le_texte_ne_localise_rien() -> None:
    """Cas limite : un texte inchange ne doit pas designer une ligne au hasard."""
    from jio.verify.mutation import _ligne_du_changement

    assert _ligne_du_changement("def f():\n    return 1\n", "def f():\n    return 1\n") == 0


# --------------------------------------------------------------------------- #
# Les cinq etats, un par un
# --------------------------------------------------------------------------- #


def test_mutant_tue_n_est_jamais_trace() -> None:
    """Le cout est la contrainte : on ne trace que ce qui reste a expliquer."""
    juge = _JugeFactice(verdicts=[False, True, False, False])
    matrice = construire(MEDIAN, SPEC_FAIBLE, checks=CHECKS_FAIBLES, budget=4, prover=juge)
    assert juge.appels_preuve == 4
    assert juge.appels_couverture == 1, "une seule execution tracee attendue (le survivant)"
    assert len(matrice.survivants) == 1
    assert matrice.tues == 3
    for index in range(len(matrice.mutants)):
        etats = {c.etat for c in matrice.cellules_de(index)}
        if index in matrice.survivants:
            assert NON_MESURE not in etats
        else:
            assert etats == {NON_MESURE, TUE}, (
                "un mutant tue ne doit produire aucun jugement de couverture"
            )


def test_regle_qui_a_execute_la_ligne_et_laisse_passer_est_aveugle() -> None:
    juge = _JugeFactice(
        verdicts=[True],
        couvertures=[{
            "R-001": CouvertureRegle("R-001", True, frozenset({4})),
            "R-002": CouvertureRegle("R-002", True, frozenset({4})),
        }],
    )
    matrice = construire(MEDIAN, SPEC_FAIBLE, checks=CHECKS_FAIBLES, budget=1, prover=juge)
    assert juge.appels_couverture == 1
    assert {c.etat for c in matrice.cellules_de(0)} == {AVEUGLE}
    assert matrice.regles_aveugles == {"R-001": 1, "R-002": 1}
    assert matrice.a_des_reserves
    assert not matrice.survivants_sans_couverture


def test_regle_qui_n_a_jamais_vu_la_ligne_est_hors_portee() -> None:
    """Accuser une regle qui n'a pas atteint la ligne serait une accusation fausse."""
    juge = _JugeFactice(
        verdicts=[True],
        couvertures=[{"R-001": CouvertureRegle("R-001", True, frozenset({3}))}],
    )
    matrice = construire(MEDIAN, _regle("R-001"), checks=CHECKS_FAIBLES, budget=1, prover=juge)
    assert {c.etat for c in matrice.cellules_de(0)} == {HORS_PORTEE}
    assert matrice.regles_aveugles == {}, "une regle hors de portee ne doit pas etre accuse"
    assert matrice.survivants_sans_couverture == (0,)
    reserve = " ".join(matrice.reserves)
    assert "ajouter une regle" in reserve
    assert "pas durcir" in reserve


def test_ligne_inconnue_rend_la_cellule_inconclusive(monkeypatch) -> None:
    """Sans localisation, on ne peut pas trancher : le dire vaut mieux qu'accuser.

    `mutate` ne produit pas de mutant non localise (il ne rend que des textes qui
    diffèrent). Le cas est donc force ici : c'est un etat que la matrice doit savoir
    traverser sans accuser personne, parce qu'un mutant sans ligne peut arriver d'une
    autre source de mutants (un format d'entree, un futur budget different).
    """
    from jio.verify.mutation import Mutation

    monkeypatch.setattr(
        "jio.verify.matrice.mutate",
        lambda source, budget=0: [Mutation("booleen True -> False", "def f():\n    return 0\n", 0)],
    )
    juge = _JugeFactice(
        verdicts=[True],
        couvertures=[{"R-001": CouvertureRegle("R-001", True, frozenset({4}))}],
    )
    matrice = construire(MEDIAN, _regle("R-001"), checks=CHECKS_FAIBLES, prover=juge)
    cellule = matrice.cellules_de(0)[0]
    assert cellule.etat == INCONCLUSIF
    assert "ligne du changement inconnue" in cellule.detail
    assert not matrice.a_des_reserves


def test_regle_sans_mesure_est_inconclusive() -> None:
    """Une regle qui n'a pas de controle executable n'est pas pour autant aveugle."""
    juge = _JugeFactice(
        verdicts=[True],
        couvertures=[{"R-001": CouvertureRegle("R-001", True, frozenset({4}))}],
    )
    matrice = construire(MEDIAN, SPEC_FAIBLE, checks=CHECKS_FAIBLES, budget=1, prover=juge)
    etats = {c.regle: c.etat for c in matrice.cellules_de(0)}
    assert etats == {"R-001": AVEUGLE, "R-002": INCONCLUSIF}
    assert matrice.regles_aveugles == {"R-001": 1}, "R-002 ne doit pas etre accusee"


def test_mesures_qui_ne_concordent_pas_n_accusent_personne() -> None:
    """Verdict different entre l'execution normale et l'execution tracee : incoherent."""
    juge = _JugeFactice(
        verdicts=[True],
        couvertures=[{"R-001": CouvertureRegle("R-001", False, frozenset({4}))}],
    )
    matrice = construire(MEDIAN, _regle("R-001"), checks=CHECKS_FAIBLES, budget=1, prover=juge)
    cellule = matrice.cellules_de(0)[0]
    assert cellule.etat == INCONCLUSIF
    assert "ne concordent pas" in cellule.detail
    assert not matrice.a_des_reserves


def test_preuve_impossible_donne_des_non_juges_explicites() -> None:
    """FailClosed ne doit jamais etre traduit en « tue » ni en « survivant »."""
    juge = _JugeFactice(verdicts=[], leve=FailClosed("aucun temoin disponible"))
    matrice = construire(MEDIAN, SPEC_FAIBLE, checks=CHECKS_FAIBLES, budget=4, prover=juge)
    assert matrice.non_juges == (0, 1, 2, 3)
    assert matrice.survivants == ()
    assert matrice.tues == 0
    assert matrice.score == 0.0, "aucun mutant juge => aucun score, pas un score de 100%"
    assert juge.appels_couverture == 0
    assert "non juge" in " ".join(matrice.reserves)


def test_source_non_mutable_donne_une_matrice_vide_qui_le_dit() -> None:
    matrice = construire("def f(:\n", SPEC_FAIBLE, checks=CHECKS_FAIBLES, prover=_JugeFactice([]))
    assert not matrice.mutants
    assert "aucun mutant" in formater(matrice)
    assert not matrice.a_des_reserves


def test_invariante_comptable() -> None:
    """tues + survivants + non juges = mutants, toujours."""
    juge = _JugeFactice(verdicts=[False, True, False, False])
    matrice = construire(MEDIAN, SPEC_FAIBLE, checks=CHECKS_FAIBLES, budget=4, prover=juge)
    assert matrice.tues + len(matrice.survivants) + len(matrice.non_juges) == len(matrice.mutants)
    assert 0.0 <= matrice.score <= 1.0


# --------------------------------------------------------------------------- #
# Le geste, pas seulement le verdict
# --------------------------------------------------------------------------- #


def test_controle_de_forme_est_reconnu() -> None:
    for controle in (
        "assert median([1, 2]) is not None",
        "assert isinstance(f(1), float)",
        "assert resultat",
        "assert f(1) == None",
    ):
        assert controle_de_forme(controle), controle
    for controle in (
        "assert median([3, 1, 2]) == 2",
        "assert f(1) > 0",
        "assert len(f(1)) == 3",
        "assert approx(f(1), 0.5)",
        "x = 1",  # pas d'assertion : on ne juge pas ce qu'on ne lit pas
    ):
        assert not controle_de_forme(controle), controle


def test_le_geste_distingue_assertion_de_forme_et_exemple_trop_faible() -> None:
    """Deux causes differentes, deux corrections differentes."""
    juge = _JugeFactice(
        verdicts=[True],
        couvertures=[{
            "R-001": CouvertureRegle("R-001", True, frozenset({4})),
            "R-002": CouvertureRegle("R-002", True, frozenset({4})),
        }],
    )
    matrice = construire(MEDIAN, SPEC_FAIBLE, checks=CHECKS_FAIBLES, budget=1, prover=juge)
    reserve = " ".join(matrice.reserves)
    assert matrice.regles_de_forme == ("R-002",)
    assert "y ecrire ce que le resultat DOIT valoir" in reserve  # R-002 : forme
    assert "ses exemples ne passent pas par le chemin" in reserve  # R-001 : exemple


def test_le_controle_de_la_spec_est_lu_quand_aucun_controle_cache_n_est_fourni() -> None:
    """Les regles portent leur controle dans `Rule.check` : la classification le lit."""
    spec = Spec(
        mission="test",
        rules=(
            Rule(id="R-001", statement="valeur", kind=RuleKind.PROPERTY, check="assert f(2) == 4"),
            Rule(id="R-002", statement="forme", kind=RuleKind.PROPERTY, check="assert f(2) is not None"),
        ),
    )
    juge = _JugeFactice(
        verdicts=[True],
        couvertures=[{
            "R-001": CouvertureRegle("R-001", True, frozenset({4})),
            "R-002": CouvertureRegle("R-002", True, frozenset({4})),
        }],
    )
    matrice = construire(MEDIAN, spec, prover=juge, budget=1)
    assert matrice.regles_de_forme == ("R-002",)
    assert juge.appels_preuve == 1, "sans controle cache, la preuve reste possible par commande"


def test_formater_montre_les_reserves_et_les_lignes() -> None:
    juge = _JugeFactice(
        verdicts=[True],
        couvertures=[{"R-001": CouvertureRegle("R-001", True, frozenset({4}))}],
    )
    texte = formater(construire(MEDIAN, _regle("R-001"), checks=CHECKS_FAIBLES, budget=1, prover=juge))
    assert "SURVIT" in texte
    assert "ligne 4" in texte
    assert "RESERVES" in texte


# --------------------------------------------------------------------------- #
# Integration : le vrai prouveur alimente la matrice
# --------------------------------------------------------------------------- #


def test_matrice_reelle_designe_la_regle_aveugle() -> None:
    """Sur `median`, le controle `is not None` est aveugle : la matrice le NOMME."""
    prover = ExecutableProver(sandbox=Sandbox(timeout=20))
    matrice = construire(MEDIAN, SPEC_FAIBLE, checks=CHECKS_FAIBLES, budget=4, prover=prover)
    assert matrice.regles_aveugles, "la faiblesse de R-002 doit etre detectee"
    assert "R-002" in matrice.regles_aveugles
    assert matrice.a_des_reserves, "une faiblesse detectee doit produire une reserve"
    reserve = " ".join(matrice.reserves)
    assert "R-002" in reserve and "falsifiable" in reserve


def test_matrice_reelle_ne_reproche_pas_a_une_regle_d_avoir_ignore_une_ligne() -> None:
    """`tariff(10) == 0` n'atteint jamais la ligne 4 : la survie de `20 -> 21` vient
    d'un TROU DE SPECIFICATION, et la reserve doit demander une regle de plus."""
    prover = ExecutableProver(sandbox=Sandbox(timeout=20))
    spec = _regle("R-001")
    matrice = construire(
        TARIFF, spec, checks={"R-001": "assert tariff(10) == 0"}, budget=5, prover=prover
    )
    assert matrice.survivants, "au moins un mutant survit sur cette specification pauvre"
    hors_portee = [
        index
        for index in matrice.survivants
        for cellule in matrice.cellules_de(index)
        if cellule.etat == HORS_PORTEE
    ]
    assert hors_portee, "le mutant de la ligne 4 doit etre declare hors de portee"
    reserve = " ".join(matrice.reserves)
    assert "ajouter une regle" in reserve
    assert matrice.regles_aveugles, "le mutant de borne (18 -> 19) est bien, lui, aveugle"


# --------------------------------------------------------------------------- #
# `assembler` : la decision, sans aucune execution
# --------------------------------------------------------------------------- #


def test_assembler_distingue_tue_survivant_et_non_juge() -> None:
    """Trois faits differents qu'un simple `killed < total` confond."""
    mutants = (
        Mutation("constante 0 -> 1", "def f():\n    return 1\n", 2),
        Mutation("operateur Add -> Sub", "def f():\n    return 1 - 1\n", 2),
        Mutation("comparaison Lt -> GtE", "def f():\n    return 1 >= 1\n", 2),
    )
    matrice = _assembler(
        mutants,
        regles=("R-001",),
        verdicts={0: frozenset({"R-001"}), 1: frozenset(), 2: None},
        raisons={2: "preuve impossible : delai depasse"},
    )
    etats = [matrice.cellules_de(i)[0] for i in range(3)]
    assert [c.etat for c in etats] == [TUE, INCONCLUSIF, INCONCLUSIF]
    assert etats[1].detail.startswith("aucune mesure de couverture")
    assert etats[2].detail == "preuve impossible : delai depasse"
    assert matrice.survivants == (1,)
    assert matrice.non_juges == (2,)
    assert matrice.tues == 1
    # Le score porte sur les mutants JUGES (1 tue sur 2 juges). Si le mutant non juge
    # etait compte tue — l'ancien comportement du moteur — on lirait 2/3 = 67 % : la
    # specification paraitrait plus solide a mesure qu'on la prouve moins.
    assert matrice.score == 0.5


def test_assembler_sans_mesure_de_couverture_est_inconclusif() -> None:
    """Le moteur peut fournir des verdicts sans avoir trace : on ne devine pas."""
    mutants = (Mutation("constante 0 -> 1", "def f():\n    return 1\n", 2),)
    matrice = _assembler(mutants, regles=("R-001",), verdicts={0: frozenset()})
    cellule = matrice.cellules_de(0)[0]
    assert cellule.etat == INCONCLUSIF
    assert "regle a commande" in cellule.detail or "sans traceur" in cellule.detail


def test_regles_de_forme_est_exporte_pour_le_moteur() -> None:
    assert _regles_de_forme(SPEC_FAIBLE, CHECKS_FAIBLES) == ("R-002",)
    assert _regles_de_forme(SPEC_FAIBLE) == ()


# --------------------------------------------------------------------------- #
# Cablage dans le moteur de mission
# --------------------------------------------------------------------------- #


def test_le_moteur_nomme_la_regle_aveugle_et_la_ligne_sans_regle() -> None:
    """La reserve du moteur ne doit plus etre un chiffre : elle doit nommer."""
    from jio.core.journal import Journal
    from jio.core.types import Artifact
    from jio.loop.engine import Engine, EngineConfig, WorkItem

    moteur = Engine(
        generators=[],
        journal=Journal(),
        prover=ExecutableProver(sandbox=Sandbox(timeout=20)),
        config=EngineConfig(mutation_budget=5),
    )
    work = WorkItem(
        objective="tarif enfant",
        entrypoint="tariff",
        checks={"R-001": "assert tariff(10) == 0"},
        spec=_regle("R-001"),
    )
    rapport = moteur._mutation_gate(Artifact(id="a", content=TARIFF, kind="code"), work.spec, work)
    assert rapport is not None and rapport.matrice is not None, (
        "la matrice doit etre construite : un `None` silencieux priverait la reserve "
        "de son seul contenu actionnable"
    )
    texte = _resume(rapport.matrice)
    assert "aveugle" in texte
    assert "ajouter une regle" in texte
    assert rapport.non_juges == ()


def test_le_moteur_dit_pourquoi_il_n_a_pas_de_localisation() -> None:
    """« Pas de mesure » et « rien a signaler » ne sont pas la meme phrase."""
    from jio.loop.engine import _resume_matrice

    assert "localisation impossible" in _resume_matrice(None)
    matrice = _assembler(
        (Mutation("constante 0 -> 1", "def f():\n    return 1\n", 2),),
        regles=("R-001",),
        verdicts={0: frozenset({"R-001"})},
    )
    assert "localisation impossible" not in _resume_matrice(matrice)


def test_un_mutant_non_juge_n_est_pas_compte_tue() -> None:
    """La porte de mutation ne doit pas crediter une preuve qui n'a pas eu lieu."""
    from jio.core.journal import Journal
    from jio.core.types import Artifact
    from jio.loop.engine import Engine, EngineConfig, WorkItem

    class _ProuveurSansTemoin:
        def prove(self, source, spec, **kwargs):
            raise FailClosed("aucun temoin disponible")

        def couverture_regles(self, source, spec, **kwargs):
            raise AssertionError("sans verdict, il n'y a rien a expliquer")

    moteur = Engine(
        generators=[],
        journal=Journal(),
        prover=_ProuveurSansTemoin(),  # type: ignore[arg-type]
        config=EngineConfig(mutation_budget=4),
    )
    work = WorkItem(objective="aucun temoin", checks={"R-001": "assert True"})
    rapport = moteur._mutation_gate(Artifact(id="a", content=MEDIAN, kind="code"), _regle("R-001"), work)
    assert rapport is not None
    assert rapport.killed == 0
    assert len(rapport.non_juges) == rapport.total > 0
    assert rapport.matrice is None, "aucun survivant : il n'y a rien a localiser"
    assert "NON JUGE" in rapport.summary()
