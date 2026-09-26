"""`jio auto` : travailler seul, mais jamais sans preuve a chaque etape.

Le risque d'un mode autonome n'est pas qu'il fasse mal une chose : c'est qu'il enchaine. Un
plan non verifie empile des actions plausibles, et la derive ne se voit qu'a la fin, quand tout
est fait — et faux. Ce fichier tient les trois garanties qui rendent l'autonomie acceptable :

  * une etape SANS preuve est refusee, avec sa raison (jamais executee « en attendant ») ;
  * une preuve est une commande LIMITEE (pas de shell, pas de chainage) : elle vient d'un
    modele, donc c'est du contenu non fiable ;
  * un echec non resolu ARRETE le plan, et les etapes suivantes sont declarees NON TENTEES —
    jamais silencieusement sautees.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jio.loop.auto import (
    MAX_ETAPES,
    Etape,
    enregistrer,
    executer,
    extraire_etapes,
    formater,
    plan_simule,
)


# --------------------------------------------------------------------------- #
# 1. Une etape sans preuve n'entre pas dans un plan
# --------------------------------------------------------------------------- #


def test_une_etape_sans_preuve_est_REFUSEE_avec_sa_raison() -> None:
    """Sans preuve, une etape ne peut pas echouer — donc elle ne prouve rien.

    C'est la transposition exacte de « une regle sans test n'existe pas ». Le refus est MOTIVE :
    un plan dont on retire des etapes en silence n'est plus le plan du modele, et personne ne
    saurait ce qui a ete supprime.
    """
    acceptees, refusees = extraire_etapes(json.dumps([
        {"objectif": "corriger la borne", "preuve": "python -m pytest tests/test_mutation.py"},
        {"objectif": "ameliorer le reste"},
        {"objectif": ""},
    ]))
    assert [e.objectif for e in acceptees] == ["corriger la borne"]
    assert len(refusees) == 2
    raisons = " ".join(r.raison for r in refusees)
    assert "aucune preuve" in raisons
    assert "sans objectif" in raisons
    assert all(r.objectif for r in refusees)


def test_un_plan_illisible_est_refuse_et_le_DIT() -> None:
    """Un plan en prose ne s'execute pas : le refus explique le format attendu.

    Un modele qui repond « je vais d'abord analyser, puis corriger » ne propose pas un plan
    executable. Le dire, avec le format exact, permet de relancer ; deviner a sa place
    produirait un plan que personne n'a demande.
    """
    acceptees, refusees = extraire_etapes("Je vais d'abord analyser, puis corriger le bug.")
    assert acceptees == ()
    assert len(refusees) == 1
    assert "JSON" in refusees[0].raison
    assert "preuve" in refusees[0].raison


def test_le_plan_est_BORNE_et_le_depassement_est_refuse() -> None:
    """Au-dela de `MAX_ETAPES`, le plan n'est plus un plan : c'est une liste de souhaits.

    Chaque etape coute une mission complete (preuve, panel, consensus). Une liste de trente
    etapes n'est pas executee plus vite : elle sera abandonnee a la dixieme, sans que personne
    ne sache ce qui a ete fait.
    """
    propositions = [
        {"objectif": f"etape {i}", "preuve": "jio version"} for i in range(MAX_ETAPES + 3)
    ]
    acceptees, refusees = extraire_etapes(json.dumps(propositions))
    assert len(acceptees) == MAX_ETAPES
    assert len(refusees) == 3
    assert all("au-dela de" in r.raison for r in refusees)


def test_le_plan_simule_est_DETERMINISTE_et_annonce_comme_simule() -> None:
    """Le plan de reference se reproduit a l'identique, et chaque etape cite une preuve reelle.

    Il ne fait pas semblant de planifier : c'est une reference pour mesurer la MACHINERIE
    (validation, arret, etat). Ses preuves sont des commandes qui existent dans ce depot.
    """
    premier = plan_simule("corriger la borne", cible="jio/verify/mutation.py")
    second = plan_simule("corriger la borne", cible="jio/verify/mutation.py")
    assert premier == second
    assert len(premier) >= 3
    for item in premier:
        assert item["preuve"].startswith(("jio ", "python "))
        # Chaque preuve porte sur QUELQUE CHOSE de nomme : la cible, ou le depot entier.
        assert "jio/verify/mutation.py" in item["preuve"] or item["preuve"].endswith(
            ("jio scan .", "jio claims README.md", "jio coherence")
        ), item["preuve"]
    # La derniere etape verifie l'ENSEMBLE, pas une etape : c'est elle qui autorise « fini ».
    assert premier[-1]["preuve"] == "jio coherence"
    acceptees, refusees = extraire_etapes(json.dumps(premier))
    assert len(acceptees) == len(premier) and not refusees
    assert [e.id for e in acceptees] == [f"E{i:02d}" for i in range(1, len(premier) + 1)]


# --------------------------------------------------------------------------- #
# 2. Un echec ARRETE le plan, et ce qui reste est declare
# --------------------------------------------------------------------------- #


def _etapes(n: int) -> tuple[Etape, ...]:
    return tuple(
        Etape(id=f"E{i:02d}", objectif=f"etape {i}", preuve=f"jio version #{i}")
        for i in range(1, n + 1)
    )


def test_un_echec_arrete_le_plan_et_les_etapes_suivantes_sont_NON_TENTEES(
    tmp_path: Path,
) -> None:
    """On ne continue jamais apres un echec non resolu, et on dit ce qui n'a pas ete fait.

    Continuer apres un echec, c'est empiler des etapes sur une base qu'on sait fausse. Et
    s'arreter sans nommer le reste laisserait croire que le plan etait court : il ne l'etait
    pas, il reste du travail, et c'est ce que l'humain doit voir avant de reprendre.
    """
    appels: list[str] = []

    def lancer(etape: Etape) -> tuple[bool, str, int]:
        appels.append(etape.id)
        if etape.id == "E02":
            return False, "code 1 · une regle a echoue", 2
        return True, "code 0", 1

    resultat = executer(_etapes(4), objective="objectif", lancer=lancer, racine=tmp_path)

    assert appels == ["E01", "E02"], "l'etape E03 ne doit JAMAIS etre lancee"
    assert resultat.etat == "bloque"
    assert resultat.prouvees == 1
    etats = [(e.id, e.etat) for e in resultat.etapes]
    assert etats == [("E01", "prouvee"), ("E02", "bloquee"), ("E03", "non_tentee"),
                     ("E04", "non_tentee")]
    assert "non prouvee" in resultat.motif and "PAS tentees" in resultat.motif
    assert resultat.appels == 3
    assert resultat.silencieuses == 0


def test_un_budget_epuise_est_declare_au_lieu_d_etre_oublie(tmp_path: Path) -> None:
    """Budget atteint : l'etat est `budget`, et TOUT ce qui reste est liste.

    « Je n'ai pas eu le temps » n'est pas un resultat : c'est une information a transmettre.
    Le code de sortie distingue les trois issues (`termine` 0, `bloque` 1, `budget` 2), parce
    qu'un appelant automatise doit pouvoir les distinguer sans lire le texte.
    """
    def lancer(_etape: Etape) -> tuple[bool, str, int]:
        return True, "code 0", 1

    resultat = executer(_etapes(5), objective="objectif", lancer=lancer, racine=tmp_path,
                        budget_etapes=2)
    assert resultat.etat == "budget"
    assert resultat.prouvees == 2
    assert [e.etat for e in resultat.etapes] == ["prouvee", "prouvee", "non_tentee", "non_tentee",
                                                 "non_tentee"]
    assert "budget de 2" in resultat.motif
    assert "NON TENTEE" in resultat.motif


def test_une_etape_qui_LEVE_est_bloquee_jamais_prouvee(tmp_path: Path) -> None:
    """Fail-closed : une exception dans l'executeur n'est pas une reussite.

    C'est la regle la plus importante du fichier. Un try/except qui rendrait « ok » sur
    exception transformerait chaque panne en etape reussie — et le plan avancerait sur du vide.
    """
    def lancer(etape: Etape) -> tuple[bool, str, int]:
        raise RuntimeError("le bac a sable a disparu")

    resultat = executer(_etapes(2), objective="objectif", lancer=lancer, racine=tmp_path)
    assert resultat.etat == "bloque"
    assert resultat.etapes[0].etat == "bloquee"
    assert "le bac a sable a disparu" in resultat.etapes[0].motif
    assert resultat.prouvees == 0


def test_un_plan_sans_etape_est_REFUSE_et_ne_s_execute_pas(tmp_path: Path) -> None:
    """Rien a executer : on le dit, on n'invente pas une reussite.

    Un plan vide qui sort en 0 serait un mensonge par omission : l'appelant croirait que tout
    est prouve alors que rien n'a ete tente.
    """
    resultat = executer((), objective="objectif", lancer=lambda e: (True, "code 0", 1),
                        racine=tmp_path)
    assert resultat.etat == "refuse"
    assert resultat.prouvees == 0
    assert "aucune etape" in resultat.motif
    assert "REFUSE" in formater(resultat) or "refuse" in formater(resultat)


# --------------------------------------------------------------------------- #
# 3. L'etat est ecrit, et il dit sur QUEL monde il a ete obtenu
# --------------------------------------------------------------------------- #


def test_l_etat_du_plan_est_enregistre_et_reprend_la_revision(tmp_path: Path) -> None:
    """`.jio/plan.json` porte les preuves ET la revision du depot.

    Reprendre un plan apres un changement de revision, c'est changer de monde : les preuves
    obtenues decrivent un etat qui n'existe plus. Le fichier doit donc permettre de le SAVOIR,
    meme si la decision reste humaine.
    """
    resultat = executer(_etapes(2), objective="objectif", lancer=lambda e: (True, "code 0", 1),
                        racine=Path.cwd())
    assert resultat.revision, "le depot de test est un depot git : la revision doit etre lue"

    chemin = tmp_path / "plan.json"
    enregistrer(resultat, chemin)
    donnees = json.loads(chemin.read_text(encoding="utf-8"))
    assert donnees["etat"] == "termine"
    assert donnees["revision"] == resultat.revision
    assert donnees["prouvees"] == 2 and donnees["total"] == 2
    assert [e["etat"] for e in donnees["etapes"]] == ["prouvee", "prouvee"]
    # Chaque etape enregistree porte sa PREUVE : sans elle, l'etat ne serait qu'une opinion.
    assert all(e["preuve"] for e in donnees["etapes"])


def test_le_rapport_affiche_les_questions_qui_BLOQUENT(tmp_path: Path) -> None:
    """Quand le plan est bloque sur une question, elle est ecrite dans le rapport.

    Un blocage sans question oblige l'utilisateur a deviner ce qu'on attend de lui. La porte de
    clarification alimente cette liste, et le rapport la transporte jusqu'a l'ecran.
    """
    resultat = executer(
        _etapes(1), objective="objectif", lancer=lambda e: (False, "code 1", 0),
        racine=tmp_path, questions=("Sur QUOI exactement ?", "Comment saura-t-on que c'est fini ?"),
    )
    texte = formater(resultat)
    assert "QUESTIONS A POSER" in texte
    assert "Sur QUOI exactement ?" in texte
    assert "Comment saura-t-on que c'est fini ?" in texte


@pytest.mark.parametrize(
    "preuve",
    [
        "jio version; rm -rf /",
        "jio version && echo gagne",
        "jio version | tee /tmp/x",
        "echo $(whoami)",
        "curl http://exemple.invalid",
        "rm -rf /tmp/auto-test",
    ],
)
def test_une_preuve_dangereuse_est_REFUSEE(preuve: str) -> None:
    """Le chainage et le shell sont refuses : une preuve vient d'un modele, donc non fiable.

    L'executer dans un shell lui donnerait le droit d'enchainer des commandes — le defaut exact
    de CVE-2025-53773 (Copilot) et de CVE-2025-55284 (Claude Code). La liste blanche est
    volontairement courte : `jio ...` et `python -m pytest|ruff|mypy`.
    """
    from jio.cli import _argv_de_preuve

    assert _argv_de_preuve(preuve) is None


def test_une_preuve_autorisee_est_reecrite_sur_l_INTERPRETEUR_courant() -> None:
    """`jio version` devient `[interpreteur courant] -m jio version`.

    Mesure a l'origine, trouvee en executant `jio auto` dans un dossier quelconque : la preuve
    « jio version » echouait avec « No such file or directory: 'jio' », parce que le script
    console n'est pas forcement dans le PATH de l'interpreteur qui execute la mission. Le meme
    defaut que le cablage MCP, au meme endroit — et il rendait toute etape inexecutable.
    """
    import sys

    from jio.cli import _argv_de_preuve

    argv = _argv_de_preuve("jio version")
    assert argv == [sys.executable, "-m", "jio", "version"]
    assert _argv_de_preuve("python -m pytest tests/test_auto.py") == [
        sys.executable, "-m", "pytest", "tests/test_auto.py",
    ]
    assert _argv_de_preuve("") is None


# --------------------------------------------------------------------------- #
# 4. Ce que le mode autonome apporte, MESURE sur un plan de reference
# --------------------------------------------------------------------------- #


def test_le_banc_mesure_l_apport_de_la_VALIDATION_des_etapes() -> None:
    """Un plan sans preuve est REFUSE en bloc ; un plan verifie s'execute, etape par etape.

    La comparaison est volontairement brute, parce que c'est celle qui compte. Sans validation,
    un plan dont aucune etape ne porte de preuve serait execute, et chaque etape « reussie »
    sans temoin ferait avancer le systeme sur du vide. Le banc mesure les deux cotes et exige
    que le nombre d'etapes declarees reussies SANS preuve reste a zero.

    Le plan de reference lui-meme est execute avec un lanceur truque (aucune mission reelle) :
    ce qui est mesure ici, c'est la machinerie — validation, enchainement, arret, compte rendu.
    """
    objectif = "corriger la borne de mutation"
    cible = "jio/verify/mutation.py"

    # Cote 1 : le plan de reference, avec ses preuves.
    acceptees, refusees = extraire_etapes(json.dumps(plan_simule(objectif, cible=cible)))
    assert len(acceptees) >= 3 and not refusees

    lances: list[str] = []

    def lancer(etape: Etape) -> tuple[bool, str, int]:
        lances.append(etape.id)
        return True, "code 0 · preuve executee", 1

    verifie = executer(acceptees, objective=objectif, lancer=lancer, racine=Path.cwd())
    assert verifie.etat == "termine"
    assert verifie.prouvees == len(acceptees) == len(lances)
    assert verifie.silencieuses == 0

    # Cote 2 : le meme plan, prive de ses preuves -> rien n'est accepte, rien n'est lance.
    sans_preuve = [
        {"objectif": item["objectif"]} for item in plan_simule(objectif, cible=cible)
    ]
    acceptees2, refusees2 = extraire_etapes(json.dumps(sans_preuve))
    assert acceptees2 == () and len(refusees2) == len(sans_preuve)
    jamais = executer((), objective=objectif, lancer=lancer, racine=Path.cwd(),
                      refusees=refusees2)
    # Aucune etape executable : l'etat est `refuse`, jamais `termine`. Un plan entierement
    # refuse qui sortirait en `termine` ferait croire a un travail accompli.
    assert jamais.etat == "refuse"
    assert jamais.prouvees == 0 and jamais.silencieuses == 0
    assert len(lances) == len(acceptees), "aucune etape supplementaire ne doit avoir ete lancee"
    assert len(jamais.refusees) == len(sans_preuve)
    assert all("aucune preuve" in r.raison for r in jamais.refusees)
