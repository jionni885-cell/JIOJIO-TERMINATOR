"""Axe temoins : les regles de la mission deviennent des tests executables.

Ce que ces tests verrouillent, dans l'ordre d'importance :

  1. la PORTE DE SECURITE — un test ecrit par un modele est du contenu NON FIABLE :
     il entre avec les seules capacites dont un test a besoin, ou il est refuse avec
     son motif. La liste des refus est testee fragment par fragment ;
  2. l'HONNETETE — une regle que le modele ne sait pas traduire est DECLAREE, jamais
     devinee ; une regle inventee n'est pas un temoin ;
  3. la SUBSTITUTION INTERDITE — quand la mission fournit un oracle, le modele ne
     prend PAS sa place : la traduction n'est meme pas demandee ;
  4. le NON-DISCRIMINANT — un temoin que tous les candidats echouent ne peut pas
     faire rejeter un candidat, et son echec interdit une livraison SANS reserve ;
  5. le mode d'echec du traducteur lui-meme, mesure : la contrefacon d'une regle
     doit etre satisfaite par une implementation fausse et REFUSEE par la correcte.
"""

from __future__ import annotations

import json

import pytest

from jio.bench.tasks import TASKS
from jio.bench.temoins import TraducteurSimule, contrefacon
from jio.core.types import Mission, Rule, RuleKind, Spec
from jio.loop.engine import Engine, EngineConfig, WorkItem
from jio.providers.base import Completion, Message
from jio.spec.witness import Temoignage, traduire, valider_test

# --------------------------------------------------------------------------- #
# Faux fournisseurs : aucun reseau, aucun hasard
# --------------------------------------------------------------------------- #


class Fournisseur:
    """Rend un texte fixe, et compte les appels."""

    name = "faux"
    model = "faux-1"

    def __init__(self, texte: str = "", *, explose: bool = False) -> None:
        self.texte = texte
        self.explose = explose
        self.appels = 0

    def complete(self, messages, *, temperature=0.0, max_tokens=2048, seed=None):
        self.appels += 1
        if self.explose:
            raise RuntimeError("panne simulee")
        return Completion(text=self.texte, model=self.model, provider=self.name)


class Generateur:
    """Rend une implementation fixe — le candidat de la mission."""

    name = "gen"
    model = "gen-1"

    def __init__(self, code: str) -> None:
        self.code = code
        self.appels = 0

    def complete(self, messages, *, temperature=0.0, max_tokens=2048, seed=None):
        self.appels += 1
        return Completion(text=f"```python\n{self.code}\n```", model=self.model,
                          provider=self.name)


SPEC = Spec(
    mission="moyenne",
    rules=(
        Rule(id="R-001", statement="moyenne nominale"),
        Rule(id="R-002", statement="la moyenne de deux valeurs egales est cette valeur",
             kind=RuleKind.BOUNDARY),
    ),
)

JUSTE = "def mean(nums):\n    return round(sum(nums) / len(nums), 10)\n"


def _engine(gen: str, *, temoins: bool, traducteur: Fournisseur, checks=None,
            config: EngineConfig | None = None) -> Engine:
    from jio.spec.compiler import SpecCompiler

    base = {"max_rounds": 1, "candidates_per_round": 1, "self_check": False,
            "differential": True, "mutation_gate": False, "temoins": temoins}
    if config is not None:
        base = dict(base, **{k: v for k, v in vars(config).items()})
        base.pop("temoins", None)
    return Engine(
        generators=[Generateur(gen)],
        config=EngineConfig(**base),
        spec_compiler=SpecCompiler(provider=traducteur),
        panel=_panel_permissif(),
    )


def _panel_permissif():
    """Panel qui accepte : ici on teste la MECANIQUE de la preuve, pas le vote."""
    from jio.audit.panel import AuditPanel

    return AuditPanel.simulated(seed=0)


# --------------------------------------------------------------------------- #
# 1. La porte de securite
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "test,fragment",
    [
        ("import os\nassert mean([1, 2]) == 1.5", "import"),
        ("assert mean([1, 2]) == 1.5 and os.getcwd()", "os."),
        ("assert open('/etc/passwd')", "fichier"),
        ("assert mean.__globals__", "dunder"),
        ("exec('assert False')", "dynamique"),
        ("import subprocess\nassert mean([1,2])", "import"),
        ("assert mean([1, 2]) == 1.5", ""),  # celui-la doit PASSER
    ],
)
def test_la_porte_refuse_le_code_hostile(test: str, fragment: str) -> None:
    ok, motif = valider_test(test, entrypoint="mean")
    if fragment:
        assert not ok, f"test accepte alors qu'il doit etre refuse : {test!r}"
        assert fragment.lower() in motif.lower(), motif
    else:
        assert ok, f"test legitime refuse : {motif}"


@pytest.mark.parametrize(
    "test,motif_attendu",
    [
        ("", "vide"),
        ("mean([1, 2])", "aucune assertion"),
        ("assert mean([1, 2]", "syntaxe"),
        ("assert 1 + 1 == 2", "n'appelle jamais l'entree"),
        ("assert " + "mean([1, 2])" * 200, "trop long"),
    ],
)
def test_la_porte_dit_pourquoi_elle_refuse(test: str, motif_attendu: str) -> None:
    ok, motif = valider_test(test, entrypoint="mean")
    assert not ok
    assert motif_attendu.lower() in motif.lower(), motif


# --------------------------------------------------------------------------- #
# 2. L'honnetete : aveux, regles inventees, refus
# --------------------------------------------------------------------------- #


def test_traduction_complete_et_declaration_des_impossibles() -> None:
    reponse = json.dumps(
        {
            "R-001": "assert mean([1, 2]) == 1.5, 'nominal'",
            "R-002": {"impossible": "la liste vide n'est pas specifiee"},
            "R-003": "assert mean([1, 2]) == 1.5",  # regle INVENTEE
        }
    )
    temoignage = traduire(SPEC, Fournisseur(reponse), entrypoint="mean")
    assert list(temoignage.tests) == ["R-001"]
    assert "R-002" in temoignage.aveux and "pas specifiee" in temoignage.aveux["R-002"]
    assert "R-003" in temoignage.refuses
    assert "inconnue" in temoignage.refuses["R-003"]
    assert temoignage.couverture == pytest.approx(1 / 3)


@pytest.mark.parametrize(
    "reponse",
    [
        '{"R-001": "assert mean([1, 2]) == 1.5"}',
        '[{"id": "R-001", "test": "assert mean([1, 2]) == 1.5"}]',
        '[{"rule_id": "R-001", "check": "assert mean([1, 2]) == 1.5"}]',
        '{"rules": {"R-001": "assert mean([1, 2]) == 1.5"}}',
        'Voici la traduction :\n```json\n{"R-001": "assert mean([1, 2]) == 1.5"}\n```',
        'Bien sur !\n[{"rule": "R-001", "check": "assert mean([1, 2]) == 1.5"}]\nVoila.',
        '[{"regle": "R-001", "assertion": "assert mean([1, 2]) == 1.5"}]',
    ],
)
def test_toutes_les_formes_de_reponse_plausibles_sont_lues(reponse: str) -> None:
    """Un modele reel ne rend pas toujours la forme demandee.

    Le format le PLUS probable est le tableau ``[{"id": "R-001", ...}]``, parce que
    c'est celui que le compilateur de specification demande juste a cote. Refuser
    cette reponse ne protegerait rien — la porte de securite juge le TEST, pas
    l'emballage — cela ferait seulement perdre les temoins.

    Ce test a attrape un bug reel : chercher d'abord ``{...}`` dans un tableau
    trouve l'OBJET IMBRIQUE, donc les reponses en tableau etaient jetees en silence.
    """
    temoignage = traduire(SPEC, Fournisseur(reponse), entrypoint="mean")
    assert list(temoignage.tests) == ["R-001"], (temoignage.tests, temoignage.refuses,
                                                 temoignage.motif)
    assert temoignage.tests["R-001"] == "assert mean([1, 2]) == 1.5"


def test_un_refus_motive_est_lu_dans_toutes_les_formes() -> None:
    for reponse in ('[{"id": "R-001", "impossible": "pas specifie"}]',
                    '{"rules": [{"rule": "R-001", "reason": "pas specifie"}]}'):
        temoignage = traduire(SPEC, Fournisseur(reponse), entrypoint="mean")
        assert temoignage.aveux.get("R-001") == "pas specifie", temoignage


def test_une_reponse_qui_nest_pas_du_json_est_un_aveu_motive() -> None:
    temoignage = traduire(SPEC, Fournisseur("```python\ndef mean(x): return 1\n```"),
                          entrypoint="mean")
    assert not temoignage.utilisable
    assert "JSON" in temoignage.motif


def test_une_regle_sans_reponse_est_un_aveu_jamais_un_silence() -> None:
    temoignage = traduire(SPEC, Fournisseur('{"R-001": "assert mean([1, 2]) == 1.5"}'),
                          entrypoint="mean")
    assert "R-002" in temoignage.aveux, "une regle oubliee doit etre declaree non traduite"


def test_reponse_illisible_et_panne_sont_des_aveux_pas_des_plantages() -> None:
    for fournisseur in (Fournisseur("je ne sais pas ecrire de test"),
                        Fournisseur(explose=True)):
        temoignage = traduire(SPEC, fournisseur, entrypoint="mean")
        assert not temoignage.utilisable
        assert temoignage.motif, "l'echec de traduction doit etre nomme"


def test_les_regles_advisory_ne_deviennent_jamais_des_verrous() -> None:
    spec = Spec(mission="m", rules=(
        Rule(id="R-001", statement="suspicion", kind=RuleKind.ADVISORY),))
    temoignage = traduire(spec, Fournisseur('{"R-001": "assert mean([]) == 0"}'),
                          entrypoint="mean")
    assert not temoignage.tests, "une regle de suspicion ne doit pas produire de temoin"


# --------------------------------------------------------------------------- #
# 3. Le moteur : substitution interdite, preuve possible, reserve obligatoire
# --------------------------------------------------------------------------- #


def test_sans_oracle_le_moteur_traduit_les_regles_et_prouve() -> None:
    traducteur = Fournisseur(json.dumps({
        "R-001": "assert mean([1, 2]) == 1.5",
        "R-002": "assert mean([2, 2]) == 2",
    }))
    moteur = _engine(JUSTE, temoins=True, traducteur=traducteur)
    rapport = moteur.run(
        Mission(objective="moyenne", id="t1", max_rounds=1),
        WorkItem(objective="moyenne", entrypoint="mean", spec=SPEC),
    )
    assert traducteur.appels == 1, "une seule traduction par mission"
    assert rapport.status.value.startswith("delivered"), rapport.abstention_reason
    assert "def mean" in rapport.subject
    evenements = {e.kind for e in moteur.journal.events()}
    assert "temoins" in evenements
    # Le texte exact du temoin est tracable : on doit pouvoir AUDITER ce que le
    # modele a eu le droit d'affirmer.
    detail = next(e.payload for e in moteur.journal.events() if e.kind == "temoins")
    assert "assert mean([1, 2]) == 1.5" in detail["tests"]["R-001"]


def test_sans_oracle_et_sans_temoins_le_moteur_sabstient() -> None:
    moteur = _engine(JUSTE, temoins=False, traducteur=Fournisseur("{}"))
    rapport = moteur.run(
        Mission(objective="moyenne", id="t2", max_rounds=1),
        WorkItem(objective="moyenne", entrypoint="mean", spec=SPEC),
    )
    assert rapport.status.value == "abstained"
    assert "preuve" in rapport.abstention_reason.lower()


def test_un_oracle_fourni_ne_se_laisse_pas_remplacer_par_le_modele() -> None:
    traducteur = Fournisseur(json.dumps({"R-001": "assert mean([1, 2]) == 99"}))
    moteur = _engine(JUSTE, temoins=True, traducteur=traducteur)
    rapport = moteur.run(
        Mission(objective="moyenne", id="t3", max_rounds=1),
        WorkItem(objective="moyenne", entrypoint="mean", spec=SPEC,
                 checks={"R-001": "assert mean([1, 2]) == 1.5"}),
    )
    assert traducteur.appels == 0, "l'oracle de la mission prime : aucune traduction"
    assert rapport.status.value.startswith("delivered")


def test_un_temoin_que_tous_echouent_nest_pas_cru_et_conduit_a_labstention() -> None:
    """Le garde-fou central, et sa limite, mesures tous les deux.

    Deux causes possibles quand AUCUN candidat ne passe un temoin : le temoin est
    faux, ou tous les candidats sont faux. Rien ne permet de trancher. La sortie
    juste n'est donc ni « on ignore le temoin et on livre » (un brouillon de cette
    brique faisait exactement cela, et livrait un artefact FAUX avec une simple
    reserve), ni « on rejette tout le monde » (un temoin faux accuserait alors une
    implementation correcte) : c'est l'ABSTENTION, avec l'ambiguite nommee.
    """
    traducteur = Fournisseur(json.dumps({
        "R-001": "assert mean([1, 2]) == 1.5",
        "R-002": "assert mean([]) == 42",  # faux : personne ne le satisfait
    }))
    moteur = _engine(JUSTE, temoins=True, traducteur=traducteur)
    rapport = moteur.run(
        Mission(objective="moyenne", id="t4", max_rounds=1),
        WorkItem(objective="moyenne", entrypoint="mean", spec=SPEC),
    )
    evenements = {e.kind: e.payload for e in moteur.journal.events()}
    assert "temoins-non-discriminants" in evenements
    assert evenements["temoins-non-discriminants"]["regles"] == ["R-002"]
    # Un temoin que personne ne passe ne departage personne : le classement est
    # inchange. On le VERIFIE au lieu de l'affirmer.
    assert evenements["temoins-non-discriminants"]["classement_identique"] is True
    assert rapport.status.value == "abstained", rapport.status.value
    aveux = [f for f in rapport.findings if f.agent == "temoins"
             and "NON PROUVEE" in f.message]
    assert aveux and "R-002" in aveux[0].message
    assert "deux causes" in aveux[0].message.lower()


def test_des_aveux_sont_visibles_dans_le_rapport() -> None:
    traducteur = Fournisseur(json.dumps({
        "R-001": "assert mean([1, 2]) == 1.5",
        "R-002": {"impossible": "la liste vide n'est pas specifiee"},
    }))
    moteur = _engine(JUSTE, temoins=True, traducteur=traducteur)
    rapport = moteur.run(
        Mission(objective="moyenne", id="t5", max_rounds=1),
        WorkItem(objective="moyenne", entrypoint="mean", spec=SPEC),
    )
    aveux = [f for f in rapport.findings if f.agent == "temoins"]
    assert aveux, "une regle non traduite doit apparaitre dans le rapport"
    assert any("R-002" in f.message for f in aveux)


# --------------------------------------------------------------------------- #
# 4. Le mode d'echec du traducteur, mesure sur le banc
# --------------------------------------------------------------------------- #


def _echoue(code: str, test: str, tache) -> bool:
    """L'implementation ``code`` echoue-t-elle au test ?"""
    espace: dict[str, object] = {}
    exec(code, espace)  # noqa: S102 — code du banc
    try:
        exec(test, dict(espace))  # noqa: S102
    except Exception:  # noqa: BLE001 — toute exception est un echec de test
        return True
    return False


@pytest.mark.parametrize("tache", TASKS, ids=lambda t: t.id)
def test_chaque_regle_du_banc_a_une_contrefacon_qui_condmane_le_faux(tache) -> None:
    """Verifie le MODE D'ECHEC mesure : la contrefacon doit discriminer.

    Sans ce test, l'echelle de fidelite du banc mesurerait une contrefacon qui ne
    contredit rien — c'est-a-dire, encore une fois, une mesure qui ne mesure rien.
    """
    for rid, test in tache.checks.items():
        faux = contrefacon(test, tache.distractors)
        assert faux, f"{tache.id}/{rid} : aucune contrefacon constructible"
        assert _echoue(tache.correct, faux, tache), (
            f"{tache.id}/{rid} : l'implementation CORRECTE satisfait la contrefacon — "
            "elle ne mesure donc pas la faute"
        )
        assert not _echoue(tache.correct, test, tache), (
            f"{tache.id}/{rid} : l'implementation correcte echoue a l'oracle"
        )


def test_le_traducteur_simule_est_deterministe_et_varie_avec_la_fidelite() -> None:
    for fidelite in (0.0, 0.5, 1.0):
        premier = TraducteurSimule(taches=TASKS, fidelite=fidelite)
        second = TraducteurSimule(taches=TASKS, fidelite=fidelite)
        tache = TASKS[0]
        prompt = [
            Message("user", f"TASK:\n{tache.objective}\nRULES:\n"
                            + "\n".join(f"- [{r.id}] ({r.kind.value}) {r.statement}"
                                        for r in tache.rules)),
        ]
        a = premier.complete(prompt, seed=0).text
        b = second.complete(prompt, seed=0).text
        assert a == b, "la simulation doit etre reproductible"
        assert not TraducteurSimule(taches=TASKS, fidelite=1.0).contrefaites
    faux = TraducteurSimule(taches=TASKS, fidelite=0.0)
    tache = TASKS[0]
    faux.complete([Message("user", f"TASK:\n{tache.objective}\nRULES:\n" + "\n".join(
        f"- [{r.id}] ({r.kind.value}) {r.statement}" for r in tache.rules))], seed=0)
    assert faux.contrefaites, "a fidelite nulle, le traducteur doit contrefaire"


def test_temoignage_resume_est_lisible() -> None:
    temoignage = Temoignage(tests={"R-001": "assert 1"}, aveux={"R-002": "raison"})
    resume = temoignage.resume()
    assert "1 regle(s) traduite(s)" in resume and "1 declaree(s)" in resume


def test_un_test_plus_long_que_la_limite_est_refuse_avec_sa_raison() -> None:
    """`MAX_LONGUEUR = 600` : au-dela, ce n'est plus un test, c'est un programme.

    Mesure a l'origine : `jio mutants` a montre que ce 600 pouvait passer a 601 sans qu'aucun
    test ne bouge. La limite n'est pas cosmetique : un temoin long a plus de chances de
    contenir autre chose qu'une assertion — et il est ecrit par un modele, donc non fiable.
    """
    from jio.spec.witness import MAX_LONGUEUR, valider_test

    assert MAX_LONGUEUR == 600
    court = "def test_r():\n    assert f(1) == 2"
    assert valider_test(court, entrypoint="f")[0] is True
    trop_long = "def test_r():\n    assert f(1) == 2\n" + "# bruit\n" * 200
    assert len(trop_long) > MAX_LONGUEUR
    ok, motif = valider_test(trop_long, entrypoint="f")
    assert ok is False and str(MAX_LONGUEUR) in motif


def test_le_nombre_de_temoins_traduits_est_borne_et_declare() -> None:
    """`MAX_TESTS = 8` : au-dela, la traduction coute plus qu'elle ne rapporte.

    On verifie la borne sur le comportement ET la valeur : une borne qui glisse en silence
    ferait payer huit appels de plus sans que rien ne le dise.
    """
    import inspect

    from jio.spec.witness import MAX_TESTS, traduire

    assert MAX_TESTS == 8
    signature = inspect.signature(traduire)
    assert signature.parameters["max_tests"].default == MAX_TESTS


def test_la_couverture_additionne_les_trois_categories_au_lieu_de_les_soustraire() -> None:
    """`couverture = tests / (tests + aveux + refuses)` : une SOMME au denominateur.

    Mesure a l'origine : `jio mutants` a montre que ce `+` pouvait devenir un `-` sans
    qu'aucun test ne bouge. Avec quatre regles separees en deux tests et deux aveux, la
    couverture aurait ete divisee par un denominateur NUL — donc annoncee a 0 % au lieu de
    50 %, et le rapport aurait blame un modele qui avait fait la moitie du travail.
    """
    from jio.spec.witness import Temoignage

    temoignage = Temoignage(
        tests={"R-1": "assert f(1) == 1", "R-2": "assert f(2) == 2"},
        aveux={"R-3": "pas traduisible"},
        refuses={"R-4": "test vide"},
    )
    assert temoignage.couverture == 0.5
    assert Temoignage().couverture == 0.0
    assert Temoignage(tests={"R-1": "x"}).couverture == 1.0


# --------------------------------------------------------------------------- #
# 3 bis. La relance : utile une fois, interdite sur un aveu
# --------------------------------------------------------------------------- #


class FournisseurEnDeuxTemps:
    """Rend la PREMIERE reponse, puis la seconde — et compte les appels.

    C'est le mode d'echec le plus courant d'un modele reel devant ce prompt : il repond
    de la prose, puis se reprend quand on lui dit ce qui a ete refuse.
    """

    name = "faux-deux-temps"
    model = "faux-2"

    def __init__(self, premier: str, second: str) -> None:
        self.premier = premier
        self.second = second
        self.appels = 0
        self.rappels: list[str] = []

    def complete(self, messages, *, temperature=0.0, max_tokens=2048, seed=None):
        self.appels += 1
        if self.appels == 1:
            return Completion(text=self.premier, model=self.model, provider=self.name)
        self.rappels.append("\n".join(m.content for m in messages))
        return Completion(text=self.second, model=self.model, provider=self.name)


def test_une_reponse_inexploitable_est_RELANCEE_avec_le_motif_du_rejet() -> None:
    """Sans oracle, une prose au prompt de traduction faisait tomber le harness a ZERO.

    Mesure a l'origine, sur le chemin reel : un modele qui ecrit du code correct mais rend
    de la prose au prompt de traduction faisait livrer 0 % la ou un tirage aveugle du meme
    budget reussissait 100 % — le harness etait PIRE que le modele seul, sur le seul cas
    qui existe en vrai. Une seconde tentative, qui DIT ce qui a ete refuse, corrige cela
    pour un appel de plus.
    """
    traducteur = FournisseurEnDeuxTemps(
        premier="Sure! Here is a summary of the rules in prose instead of JSON.",
        second=json.dumps({
            "R-001": "assert mean([1, 2]) == 1.5",
            "R-002": "assert mean([2, 2]) == 2",
        }),
    )
    temoignage = traduire(SPEC, traducteur, entrypoint="mean", objectif="moyenne")

    assert traducteur.appels == 2, "la relance doit avoir lieu"
    assert temoignage.tests, "la seconde reponse est exploitable : elle doit etre retenue"
    assert temoignage.appels == 2, "deux appels doivent etre COMPTES comme deux"
    assert temoignage.relance is True
    # Le motif du rejet part avec la relance : une relance muette n'apprend rien.
    assert "SYSTEM NOTE" in traducteur.rappels[0]
    assert "Return ONLY a JSON object" in traducteur.rappels[0]


def test_une_reponse_PARTIELLEMENT_utilisable_n_est_PAS_relancee() -> None:
    """La borne de la relance, et pourquoi elle est la.

    Relancer quand UNE regle sur deux a ete traduite parait tentant : on gagnerait la
    couverture manquante. C'est refuse, pour une raison de fond et non de cout. La seconde
    reponse donne un AUTRE temoin pour la meme regle, et rien ne permet de choisir entre
    les deux : garder le nouveau peut effacer un temoin qui marchait, garder les deux
    revient a faire voter deux assertions pour une seule regle. Ce qui manque est deja
    DIT — la livraison porte la reserve « regle NON PROUVEE » — et une reserve nommee vaut
    mieux qu'un temoin choisi au hasard. La relance reste donc ce qu'elle doit etre : le
    rattrapage du cas ou RIEN n'etait utilisable.
    """
    traducteur = FournisseurEnDeuxTemps(
        premier=json.dumps({"R-001": "import os\nos.system('false')",
                            "R-002": "assert mean([2, 2]) == 2"}),
        second=json.dumps({"R-001": "assert mean([1, 2]) == 1.5",
                           "R-002": "assert mean([2, 2]) == 2"}),
    )
    temoignage = traduire(SPEC, traducteur, entrypoint="mean", objectif="moyenne")

    assert traducteur.appels == 1, "une reponse partiellement utilisable n'est pas relancee"
    assert set(temoignage.tests) == {"R-002"}
    assert "R-001" in temoignage.refuses, "le refus est conserve, avec son motif"
    assert temoignage.relance is False


def test_la_relance_dit_POURQUOI_la_premiere_reponse_a_ete_rejetee() -> None:
    """Une relance muette n'est qu'un deuxieme tirage aveugle.

    Toute la litterature du domaine dit la meme chose : ce qui fait gagner des dizaines de
    points a un modele IDENTIQUE, c'est le format et le retour d'information, pas le nombre
    d'essais. On verifie donc le contenu du rappel, pas seulement qu'il a eu lieu.
    """
    traducteur = FournisseurEnDeuxTemps(
        premier=json.dumps({"R-001": "import os\nos.system('false')"}),
        second=json.dumps({"R-001": "assert mean([1, 2]) == 1.5"}),
    )
    # Une SEULE regle, refusee par la porte : rien d'utilisable, donc relance.
    un = Spec(mission="moyenne", rules=(Rule(id="R-001", statement="moyenne nominale"),))
    traduire(un, traducteur, entrypoint="mean", objectif="moyenne")

    assert traducteur.appels == 2
    rappel = traducteur.rappels[0]
    assert "REJECTED by the security gate" in rappel
    assert "R-001" in rappel
    assert "import" in rappel, "le motif du refus doit accompagner la relance"


def test_un_AVEU_honnete_n_est_JAMAIS_relance() -> None:
    """Insister sur un aveu, c'est fabriquer un faux temoin — et rien d'autre.

    Un modele qui declare une regle non testable a RENDU une reponse. Le relancer pour
    obtenir une assertion revient a lui demander d'inventer une preuve : c'est ainsi qu'on
    transforme une abstention honnete en mensonge verifie. On verifie donc que l'appel est
    UNIQUE, meme quand aucune regle n'a ete traduite.
    """
    aveu = json.dumps({
        "R-001": {"impossible": "aucun oracle de reference dans l'enonce"},
        "R-002": {"impossible": "propriete statistique, non decidable ici"},
    })
    traducteur = FournisseurEnDeuxTemps(premier=aveu, second=aveu)
    temoignage = traduire(SPEC, traducteur, entrypoint="mean", objectif="moyenne")

    assert traducteur.appels == 1, "un aveu n'est pas une panne : il ne se relance pas"
    assert not temoignage.tests and temoignage.aveux
    assert temoignage.relance is False
    assert temoignage.appels == 1


def test_une_relance_qui_echoue_AUSSI_reste_honnete_et_compte_ses_appels() -> None:
    """Le pire cas : deux reponses inexploitables. Le compte doit dire DEUX."""
    traducteur = FournisseurEnDeuxTemps(premier="prose", second="encore de la prose")
    temoignage = traduire(SPEC, traducteur, entrypoint="mean", objectif="moyenne")

    assert traducteur.appels == 2
    assert temoignage.appels == 2
    assert not temoignage.tests
    assert temoignage.motif, "l'echec doit etre NOMME, pas silencieux"


class GenerateurParTour:
    """Rend une implementation FAUSSE au premier tour, JUSTE ensuite.

    C'est le cas exact du defaut : le temoin traduit est le meme a tous les tours (il est
    memoise), mais les CANDIDATS changent. Une regle que tous les candidats du tour 1
    echouent entre dans `_regles_non_prouvees`, et rien ne l'en sortait — meme quand le
    candidat final, lui, la satisfaisait.
    """

    name = "gen-par-tour"
    model = "gen-tour-1"

    def __init__(self, faux: str, juste: str) -> None:
        self.faux = faux
        self.juste = juste
        self.appels = 0

    def complete(self, messages, *, temperature=0.0, max_tokens=2048, seed=None):
        self.appels += 1
        code = self.faux if self.appels == 1 else self.juste
        return Completion(text=f"```python\n{code}\n```", model=self.model, provider=self.name)


def test_une_regle_NON_PROUVEE_a_un_tour_et_PROUVEE_par_lartefact_LIVRE_nest_plus_annoncee() -> None:
    """Le rapport ne doit JAMAIS se contredire sur la meme page.

    `_regles_non_prouvees` s'accumulait d'un tour a l'autre sans jamais se reconcilier, alors
    que le rapport affiche a cote les preuves de l'artefact LIVRE. Mesure faite sur
    `jio run --simulate --task sum_even --no-oracle` : la MEME page annoncait

        preuves  3/3 regles satisfaites
        [ok] R-001
        ...
        MOTIF : regle(s) NON PROUVEE(s) : R-001, R-003

    Un rapport qui se contredit n'est pas « prudent » : il n'est plus verifiable — et un
    lecteur qui ne peut plus rien verifier ne peut plus rien croire, y compris les lignes
    justes. La reconciliation retire donc les regles que l'artefact LIVRE satisfait, et
    ELLE-MEME est journalisee : l'ecart entre les deux lectures reste auditable.
    """
    from jio.spec.compiler import SpecCompiler

    traduits = json.dumps({
        "R-001": "assert mean([1, 2]) == 1.5",
        "R-002": "assert mean([2, 2]) == 2",
    })
    faux = "def mean(nums):\n    return sum(nums) / max(len(nums), 1) + 1\n"
    generateur = GenerateurParTour(faux, JUSTE)
    moteur = Engine(
        generators=[generateur],
        config=EngineConfig(max_rounds=3, candidates_per_round=1, self_check=False,
                            differential=True, mutation_gate=False, temoins=True),
        spec_compiler=SpecCompiler(provider=Fournisseur(traduits)),
        panel=_panel_permissif(),
    )
    rapport = moteur.run(
        Mission(objective="moyenne", id="t-reconcile", max_rounds=3),
        WorkItem(objective="moyenne", entrypoint="mean", spec=SPEC),
    )

    kinds = {e.kind for e in moteur.journal.events()}
    assert generateur.appels >= 2, "le tour 2 doit avoir eu lieu (sinon le test ne mesure rien)"

    prouvees = {w.rule_id for w in rapport.witnesses if w.ok}
    assert "R-001" in prouvees, [w.rule_id for w in rapport.witnesses]
    assert "NON PROUVEE" not in rapport.abstention_reason, (
        "l'artefact livre satisfait R-001 et le motif le declare NON PROUVEE : le rapport "
        f"se contredit — {rapport.abstention_reason[:200]}"
    )
    assert not any(
        "R-001" in f.message and "NON PROUVEE" in f.message for f in rapport.findings
    ), [f.message for f in rapport.findings]
    # La reconciliation est ECRITE, pas silencieuse : on doit pouvoir retrouver au journal
    # qu'une regle a ete declaree non prouvee puis reconciliee.
    assert "temoins-reconcilies" in kinds, kinds
    evenement = next(e.payload for e in moteur.journal.events()
                     if e.kind == "temoins-reconcilies")
    # Les DEUX regles : le candidat faux du tour 1 (`... + 1`) echoue les deux temoins, donc
    # les deux etaient non prouvees — et l'artefact livre les satisfait toutes les deux. Ce qui
    # compte n'est pas le nombre, c'est que la liste reconciliee soit celle des regles que le
    # constat de tour 1 nommait ET que l'artefact livre satisfait : ni plus, ni moins.
    assert evenement["regles"] == ["R-001", "R-002"]
    assert set(evenement["regles"]) <= prouvees
