"""Les valeurs figees : ce qui sert de CLE ne doit pas pouvoir changer en place.

Mesure a l'origine — `jio mutants` : quatre `@dataclass(frozen=True)` du depot pouvaient
passer a `frozen=False` **sans qu'aucun test ne bouge** (`Risque`, `Calibration`, `Decision`,
`AgentSpec`). Ces objets servent de VALEURS : un constat d'audit, un point de calibrage, une
decision de garde-ecriture, la definition d'un artefact. Les rendre mutables ne casse rien
tout de suite — cela casse le jour ou deux couches partagent l'objet et ou l'une le modifie
sous l'autre. C'est le genre de defaut qu'on ne voit qu'apres coup, donc on le ferme ici.

La table ci-dessous est EXPLICITE, et c'est le point : une liste derivee automatiquement
(« toutes les classes figees ») ne detecterait pas le retrait de `frozen=True`, puisqu'une
classe devenue libre sortirait simplement de la liste. Chaque entree dit POURQUOI cette
valeur doit etre figee ; un test le verifie sur l'objet, pas sur le fichier source.
"""

from __future__ import annotations

import dataclasses
import importlib

import pytest

#: module:Classe -> la raison, en clair, d'exiger l'immutabilite.
VALEURS_FIGEES: dict[str, str] = {
    "jio.audit.oscillation:ProgressPoint": (
        "un point de trace sert de CLE de comparaison ; deux couches qui partagent l'objet "
        "rendraient l'oscillation invisible"
    ),
    "jio.verify.imports:ImportProblem": (
        "un probleme d'import est compare et dedoublonne : mute en place, il fausserait le "
        "comptage"
    ),
    "jio.artifacts.audit_skills:Risque": (
        "un constat d'audit de competence est une VALEUR, pas un etat qu'on revise"
    ),
    "jio.gate.conformal:Calibration": (
        "un point de calibrage alimente le seuil de la porte ; le modifier en place "
        "changerait le seuil d'une decision deja prise"
    ),
    "jio.artifacts.write_guard:Decision": (
        "une decision d'ecriture est lue par plusieurs couches avant d'agir"
    ),
    "jio.artifacts.definitions:AgentSpec": (
        "la definition d'un artefact natif est une donnee de reference partagee"
    ),
    "jio.artifacts.definitions:SkillSpec": (
        "une competence est ecrite telle quelle dans le fichier de l'outil : la modifier en "
        "place ferait diverger le fichier ecrit de la definition"
    ),
    "jio.core.types:Witness": (
        "un temoin porte le hash de sa sortie : le modifier en place casserait la chaine "
        "de preuve"
    ),
    "jio.core.types:MissionReport": (
        "le rapport d'une mission est archive tel quel et ne doit pas bouger apres coup"
    ),
    "jio.core.journal:Event": (
        "un evenement de journal est la matiere du rejeu deterministe"
    ),
    # --- les onze ajoutees apres la deuxieme passe de mutation (budget 2, tout jio/) ---
    "jio.verify.mutation:Mutation": (
        "une mutation est un COUPLE (etiquette, source mutee) : la modifier en place ferait "
        "mesurer autre chose que ce qu'on a applique"
    ),
    "jio.trust.router:Arm": (
        "un bras du bandit est une configuration de reference : le modifier en place "
        "changerait le budget d'une decision deja prise"
    ),
    "jio.verify.commands:CommandeCitee": (
        "une invocation citee est comparee au parseur reel ; mutee en place, elle "
        "designerait une autre commande"
    ),
    "jio.verify.entropy:EntropyResult": (
        "un resultat d'entropie est une mesure : elle ne doit pas se reviser sous les "
        "yeux de celui qui la lit"
    ),
    "jio.verify.dependances:Manque": (
        "un manque de dependance est une VALEUR mise dans un rapport"
    ),
    "jio.verify.metamorphic:Mutation": (
        "une transformation metamorphique est une fonction nommee, pas un etat"
    ),
    "jio.verify.metamorphic:MetamorphicFinding": (
        "un constat de metamorphose est une valeur, comme tout constat"
    ),
    "jio.spec.library:TemoinValide": (
        "un temoin valide par une livraison prouvee est une CAPACITE rejouable : sa "
        "signature doit etre figeable"
    ),
    "jio.bench.prose:ProseTache": (
        "une tache de prose est une donnee de reference du banc"
    ),
    "jio.bench.tasks:Task": (
        "une tache du banc de code est une donnee de reference : la meme pour tous les bras"
    ),
    "jio.bench.provider_spec:Fournisseur": (
        "la description d'un fournisseur est lue par plusieurs couches avant un appel"
    ),
}


def _classe(cle: str) -> type:
    module_nom, _, classe_nom = cle.partition(":")
    module = importlib.import_module(module_nom)
    return getattr(module, classe_nom)


@pytest.mark.parametrize("cle", sorted(VALEURS_FIGEES))
def test_la_valeur_est_figee_et_refuse_toute_modification(cle: str) -> None:
    """Deux verifications, parce qu'elles echouent separement.

    `frozen` peut etre retire de l'annotation SANS que l'objet cesse d'etre fige sur un
    chemin donne ; et une classe peut se declarer figee tout en laissant un `__setattr__`
    passer. On exige donc les deux : le drapeau ET le refus reel (test sur l'objet, pas sur
    la source).
    """
    classe = _classe(cle)
    assert dataclasses.is_dataclass(classe), f"{cle} n'est plus une dataclass"
    motif = VALEURS_FIGEES[cle]
    assert getattr(classe.__dataclass_params__, "frozen", False), (
        f"{cle} doit etre declaree `frozen=True` : {motif}"
    )
    champs = dataclasses.fields(classe)
    assert champs, f"{cle} n'a aucun champ : le test ne prouverait rien"
    # Instance sans arguments : on ne suppose pas la signature du constructeur.
    objet = object.__new__(classe)
    with pytest.raises(dataclasses.FrozenInstanceError):
        setattr(objet, champs[0].name, "valeur-de-test")
    with pytest.raises(dataclasses.FrozenInstanceError):
        delattr(objet, champs[0].name)


def test_la_table_couvre_les_quatre_valeurs_mesurees_par_la_mutation() -> None:
    """Le lien avec la mesure est explicite : ces quatre-la ont SURVECU a un mutant.

    Sans cette assertion, quelqu'un pourrait vider la table (ou retirer une ligne) et le
    test parametre deviendrait plus silencieux en restant vert — le defaut exact que
    `jio mutants` a servi a rendre visible.
    """
    mesurees = {
        "jio.artifacts.audit_skills:Risque",
        "jio.gate.conformal:Calibration",
        "jio.artifacts.write_guard:Decision",
        "jio.artifacts.definitions:AgentSpec",
        "jio.artifacts.definitions:SkillSpec",
    }
    manquantes = sorted(mesurees - set(VALEURS_FIGEES))
    assert not manquantes, (
        f"valeur(s) figee(s) mesuree(s) par mutation et absente(s) de la table : {manquantes}"
    )


def test_aucune_entree_de_la_table_n_est_un_doublon_ou_un_fantome() -> None:
    """Un nom qui ne se resout plus doit echouer ICI, pas passer pour un test en moins."""
    for cle in VALEURS_FIGEES:
        classe = _classe(cle)
        assert classe.__name__ == cle.partition(":")[2]
    assert len(VALEURS_FIGEES) == len(set(VALEURS_FIGEES))
