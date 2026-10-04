"""La matrice mutants x regles — qui a vu le changement, et qui ne pouvait pas le voir.

Le probleme que ce module resout
--------------------------------
La porte de mutation dit « N mutants survivants ». C'est un chiffre, pas une action :
un developpeur ne sait pas QUOI corriger. Les deux causes possibles demandent des
gestes OPPOSES, et rien ne les distingue sans mesurer la couverture de chaque regle :

  * la regle a EXECUTE la ligne mutee et n'a rien vu. Sa verification ne distingue
    pas le correct du faux : c'est une decoration. Il faut la renforcer, et on sait
    laquelle.
  * la regle n'a JAMAIS touche cette ligne. Elle ne pouvait rien voir : lui
    reprocher la survie serait une accusation fausse. C'est la SPECIFICATION qui est
    incomplete, pas cette regle-la.

Usage
-----
On mute l'artefact, on prouve chaque mutant contre la specification COMPLETE, puis,
pour les seuls survivants, on mesure par UNE execution tracee les lignes que chaque
controle exerce. Aucun mutant tue n'est trace : il n'y a rien a localiser chez lui.

Assemblage : la decision est PURE, l'execution ne l'est pas
---------------------------------------------------------
`construire` fait le travail complet (muter, prouver, tracer) mais c'est `assembler`
qui DECIDE, a partir de mesures deja prises. Cette separation existe pour une raison
concrete : le moteur de mission a deja prouve chaque mutant quand il veut expliquer
un survivant. Refaire les preuves pour obtenir la matrice doublerait le cout de la
porte ; lui demander d'appeler `assembler` avec ce qu'il sait ne coute rien de plus.

Quatrieme etat, et il compte
----------------------------
`inconclusif` n'est pas un refus de repondre : c'est une reponse. Il apparait quand le
traceur n'a rien rapporte, quand la ligne du changement est inconnue, ou quand deux
executions de la meme regle donnent des verdicts opposes. Dans ces cas on ne sait pas,
et le dire vaut mieux que de ranger le mutant dans la case qui accuse quelqu'un.
"""

from __future__ import annotations

import ast
import textwrap
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from ..core.errors import FailClosed
from ..core.types import Spec
from .executable import CouvertureRegle, ExecutableProver, Sandbox
from .mutation import MUTATION_BUDGET, Mutation, mutate

#: Etats d'une case de la matrice.
TUE = "tue"
AVEUGLE = "aveugle"
HORS_PORTEE = "hors-portee"
INCONCLUSIF = "inconclusif"
NON_MESURE = "non-mesure"

__all__ = [
    "AVEUGLE",
    "HORS_PORTEE",
    "INCONCLUSIF",
    "NON_MESURE",
    "TUE",
    "CelluleMatrice",
    "MatriceMutants",
    "assembler",
    "construire",
    "formater",
    "regles_de_forme",
    "resume",
]


#: Motifs d'un controle qui, par construction, ne peut PAS distinguer deux valeurs.
_MOTIFS_DE_FORME = ("is not None", "is None", "isinstance(", "callable(", "bool(", "hasattr(")


def controle_de_forme(controle: str) -> bool:
    """Vrai quand le controle ne compare AUCUNE valeur attendue.

    Un `assert resultat is not None` passe pour toute fonction qui ne plante pas : il
    ne peut rater aucun mutant qui garde le bon type de retour. Le dire change le
    geste a faire (reecrire l'assertion) au lieu d'ajouter un exemple (ce qui ne
    servirait a rien : le controle ne regarde meme pas la valeur).

    Le classement est prudent : des qu'une comparaison porte sur une constante non
    nulle, ou qu'un appel a `approx`/`isclose` est present, le controle est tenu
    pour falsifiable. Seules les formes manifestement aveugles sont signalees.
    """
    texte = textwrap.dedent(controle or "").strip()
    if not texte:
        return False
    try:
        arbre = ast.parse(texte)
    except SyntaxError:
        arbre = None
    if arbre is None:
        return any(motif in texte for motif in _MOTIFS_DE_FORME)
    assertions = [n for n in ast.walk(arbre) if isinstance(n, ast.Assert)]
    if not assertions:
        return False  # pas d'assertion : on ne juge pas ce qu'on ne lit pas
    return all(not _comparaison_falsifiable(n.test) for n in assertions)


def _comparaison_falsifiable(test: ast.AST) -> bool:
    for noeud in ast.walk(test):
        if isinstance(noeud, ast.Call) and _nom_appele(noeud) in {"approx", "isclose"}:
            return True
        if isinstance(noeud, ast.Compare):
            for operateur, comparateur in zip(noeud.ops, noeud.comparators):
                if not isinstance(operateur, (ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE)):
                    continue
                if isinstance(comparateur, ast.Constant) and comparateur.value is None:
                    continue  # `== None` / `!= None` : pas une valeur attendue
                return True
    return False


def _nom_appele(appel: ast.Call) -> str:
    fonction = appel.func
    if isinstance(fonction, ast.Name):
        return fonction.id
    if isinstance(fonction, ast.Attribute):
        return fonction.attr
    return ""


@dataclass(frozen=True)
class CelluleMatrice:
    """Un couple (mutant, regle) et ce qu'on peut en dire."""

    mutant: int
    regle: str
    etat: str
    detail: str = ""

    @property
    def accuse_la_regle(self) -> bool:
        """Vrai quand la regle a VU le code mute et l'a laisse passer."""
        return self.etat == AVEUGLE


@dataclass
class MatriceMutants:
    """Le tableau complet, avec de quoi decider sans relire le journal."""

    mutants: tuple[Mutation, ...] = ()
    cellules: tuple[CelluleMatrice, ...] = ()
    regles: tuple[str, ...] = ()
    #: Raison ECRITE quand la matrice n'a pas pu etre construite entierement.
    note: str = ""
    #: Mutants que la specification n'a pas tues, indices dans `mutants`.
    survivants: tuple[int, ...] = ()
    #: Mutants que l'on n'a meme pas pu juger (preuve impossible).
    non_juges: tuple[int, ...] = ()
    #: Regles dont tous les controles ne comparent AUCUNE valeur attendue : elles ne
    #: peuvent, par construction, distinguer un resultat correct d'un resultat faux.
    regles_de_forme: tuple[str, ...] = ()

    # -- lectures ---------------------------------------------------------- #

    @property
    def tues(self) -> int:
        return len(self.mutants) - len(self.survivants) - len(self.non_juges)

    @property
    def score(self) -> float:
        """Part des mutants tues, parmi ceux qui ont pu etre juges."""
        juges = len(self.mutants) - len(self.non_juges)
        return self.tues / juges if juges else 0.0

    def cellules_de(self, mutant: int) -> tuple[CelluleMatrice, ...]:
        return tuple(c for c in self.cellules if c.mutant == mutant)

    @property
    def regles_aveugles(self) -> dict[str, int]:
        """Regles qui ont EXECUTE des lignes mutees sans rien y voir, par regle."""
        comptes: dict[str, int] = {}
        for cellule in self.cellules:
            if cellule.etat == AVEUGLE:
                comptes[cellule.regle] = comptes.get(cellule.regle, 0) + 1
        return dict(sorted(comptes.items(), key=lambda item: (-item[1], item[0])))

    @property
    def survivants_sans_couverture(self) -> tuple[int, ...]:
        """Survivants dont AUCUNE regle n'a execute la ligne mutee.

        Ce n'est pas la faute des regles existantes : c'est un trou de la
        specification, et le geste a faire est d'ajouter une regle, pas d'en durcir
        une qui n'a jamais vu ce code.
        """
        resultat = []
        for index in self.survivants:
            etats = {c.etat for c in self.cellules_de(index)}
            if etats == {HORS_PORTEE}:
                resultat.append(index)
        return tuple(resultat)

    @property
    def reserves(self) -> tuple[str, ...]:
        """Ce qu'il faut corriger, en clair, avec le geste associe.

        Une reserve vide n'est pas un silence : `a_des_reserves` le dit, et les
        appelants s'en servent pour refuser un quitus.
        """
        phrases: list[str] = []
        for regle, nombre in self.regles_aveugles.items():
            if regle in self.regles_de_forme:
                geste = (
                    "son controle ne compare AUCUNE valeur attendue (forme seulement) : "
                    "il faut le rendre falsifiable, c'est-a-dire y ecrire ce que le "
                    "resultat DOIT valoir"
                )
            else:
                geste = (
                    "son assertion compare une valeur, mais ses exemples ne passent pas "
                    "par le chemin que ce changement modifie : il faut un cas ou ce "
                    "chemin change le resultat"
                )
            phrases.append(
                f"{regle} : {nombre} mutant(s) survivant(s) sur des lignes qu'elle a "
                f"EXECUTEES — sa verification ne distingue pas le correct du faux : {geste}."
            )
        if self.survivants_sans_couverture:
            indices = ", ".join(str(i) for i in self.survivants_sans_couverture)
            phrases.append(
                f"aucune regle n'execute les lignes des mutants {indices} : ce chemin "
                "de code n'est couvert par RIEN — ajouter une regle, pas durcir une "
                "regle existante (aucune ne pouvait le voir)."
            )
        if self.non_juges:
            phrases.append(
                f"{len(self.non_juges)} mutant(s) non juge(s) : la preuve n'a pas pu "
                "etre executee, donc rien n'est affirme sur eux — ni tue, ni survivant."
            )
        if self.note:
            phrases.append(self.note)
        return tuple(phrases)

    @property
    def a_des_reserves(self) -> bool:
        return bool(self.regles_aveugles or self.survivants_sans_couverture or self.non_juges)


def construire(
    source: str,
    spec: Spec,
    *,
    checks: Mapping[str, str] | None = None,
    prover: ExecutableProver | None = None,
    budget: int = MUTATION_BUDGET,
    entrypoint: str = "",
    preamble: str = "",
    chemin: Path | None = None,
) -> MatriceMutants:
    """Mute `source`, la prouve contre `spec`, et explique chaque survivant.

    Le cout est borne : une passe de preuve par mutant, puis UNE execution tracee
    par survivant (pas une par couple mutant-regle). Sur une specification a trois
    regles et un survivant, cela fait deux executions en tout.
    """
    juges = prover or ExecutableProver(sandbox=Sandbox(timeout=20))
    mutants = tuple(mutate(source, budget=budget))
    if not mutants:
        return MatriceMutants(
            note="aucun mutant executable : il n'y a rien a localiser sur cette source"
        )

    regles = tuple(r.id for r in spec.rules)
    verdicts: dict[int, frozenset[str] | None] = {}
    raisons: dict[int, str] = {}
    couvertures: dict[int, Mapping[str, CouvertureRegle]] = {}

    for index, mutant in enumerate(mutants):
        try:
            resultat = juges.prove(
                mutant.source,
                spec,
                hidden_checks=checks,
                entrypoint=entrypoint,
                preamble=preamble,
                chemin=chemin,
            )
        except FailClosed as exc:
            verdicts[index] = None
            raisons[index] = f"preuve impossible : {exc}"
            continue
        if not resultat.passed:
            verdicts[index] = frozenset(w.rule_id for w in resultat.failures)
            continue
        verdicts[index] = frozenset()
        # Uniquement pour un survivant : mesurer la couverture d'un mutant deja tue
        # couterait une execution pour ne rien apprendre.
        couvertures[index] = juges.couverture_regles(
            mutant.source,
            spec,
            hidden_checks=checks,
            entrypoint=entrypoint,
            preamble=preamble,
            chemin=chemin,
        )

    return assembler(
        mutants,
        regles=regles,
        verdicts=verdicts,
        raisons=raisons,
        couvertures=couvertures,
        regles_de_forme=regles_de_forme(spec, checks),
    )


def assembler(
    mutants: Sequence[Mutation],
    *,
    regles: Sequence[str],
    verdicts: Mapping[int, frozenset[str] | None],
    raisons: Mapping[int, str] | None = None,
    couvertures: Mapping[int, Mapping[str, CouvertureRegle]] | None = None,
    regles_de_forme: Sequence[str] = (),
) -> MatriceMutants:
    """Decide, a partir de mesures DEJA prises : aucune execution ici.

    `verdicts[i]` est l'ensemble des regles qui ont tue le mutant `i` ;
    l'ensemble VIDE veut dire « il a survecu » ; `None` veut dire « il n'a pas pu
    etre juge » — trois choses differentes que `killed < total` confond.
    """
    raisons = dict(raisons or {})
    couvertures = dict(couvertures or {})
    mutants = tuple(mutants)
    regles = tuple(regles)
    cellules: list[CelluleMatrice] = []
    survivants: list[int] = []
    non_juges: list[int] = []

    for index, mutant in enumerate(mutants):
        tueuses = verdicts.get(index)
        if tueuses is None:
            non_juges.append(index)
            motif = raisons.get(index) or "la preuve n'a pas pu etre executee"
            cellules.extend(
                CelluleMatrice(index, regle, INCONCLUSIF, motif) for regle in regles
            )
            continue
        if tueuses:
            for regle in regles:
                if regle in tueuses:
                    cellules.append(
                        CelluleMatrice(index, regle, TUE, "la regle a echoue sur ce mutant")
                    )
                else:
                    cellules.append(
                        CelluleMatrice(
                            index, regle, NON_MESURE,
                            "mutant tue : la couverture n'est mesuree que pour les survivants",
                        )
                    )
            continue
        survivants.append(index)
        cellules.extend(
            _cellules_du_survivant(index, mutant, regles, couvertures.get(index) or {})
        )

    return MatriceMutants(
        mutants=mutants,
        cellules=tuple(cellules),
        regles=regles,
        survivants=tuple(survivants),
        non_juges=tuple(non_juges),
        regles_de_forme=tuple(regles_de_forme),
    )


def _controles_en_vigueur(spec: Spec, checks: Mapping[str, str] | None) -> dict[str, str]:
    """Les controles REELLEMENT utilises par la preuve, par regle.

    Un controle cache prime sur `rule.check`, exactement comme dans
    `ExecutableProver.prove` : classer les regles sur un controle que la preuve
    n'utilise pas serait une lecture fausse du geste a faire.
    """
    caches = {r.id: checks[r.id] for r in spec.rules if checks and r.id in checks}
    if caches:
        return caches
    return {r.id: r.check for r in spec.rules if r.check}


def regles_de_forme(spec: Spec, checks: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Regles dont TOUS les controles sont des controles de FORME.

    Utile a qui veut le geste sans construire toute la matrice : la porte de
    mutation du moteur, par exemple, n'a besoin que de cette liste.
    """
    controles = _controles_en_vigueur(spec, checks)
    return tuple(
        regle.id for regle in spec.rules if controle_de_forme(controles.get(regle.id, ""))
    )


def resume(matrice: MatriceMutants) -> str:
    """La matrice en UNE ligne : pour un finding, un journal ou un resume de CI.

    `formater` sert a lire, `resume` sert a citer. Une reserve longue finit par ne
    plus etre lue du tout ; celle-ci tient dans une ligne de journal.
    """
    if not matrice.mutants:
        return matrice.note or "aucun mutant executable"
    morceaux: list[str] = []
    if matrice.regles_aveugles:
        morceaux.append(
            "regle(s) aveugle(s) : "
            + ", ".join(f"{regle} x{nombre}" for regle, nombre in matrice.regles_aveugles.items())
        )
    if matrice.survivants_sans_couverture:
        indices = ", ".join(str(i) for i in matrice.survivants_sans_couverture)
        morceaux.append(
            f"aucune regle n'execute la ligne des mutants {indices} : ajouter une regle"
        )
    if matrice.non_juges:
        morceaux.append(f"{len(matrice.non_juges)} mutant(s) non juge(s) (preuve impossible)")
    return " ; ".join(morceaux) if morceaux else "aucun survivant attribuable a une regle"


def _cellules_du_survivant(
    index: int,
    mutant: Mutation,
    regles: Sequence[str],
    couverture: Mapping[str, CouvertureRegle],
) -> list[CelluleMatrice]:
    """L'etat de chaque regle devant CE survivant — le coeur de la matrice."""
    cellules: list[CelluleMatrice] = []
    for regle in regles:
        if mutant.ligne <= 0:
            cellules.append(
                CelluleMatrice(
                    index, regle, INCONCLUSIF,
                    "ligne du changement inconnue : on ne peut pas dire si la regle l'a vue",
                )
            )
            continue
        donnee = couverture.get(regle)
        if donnee is None:
            cellules.append(
                CelluleMatrice(
                    index, regle, INCONCLUSIF,
                    "aucune mesure de couverture rapportee pour cette regle "
                    "(regle a commande, ou execution sans traceur)",
                )
            )
            continue
        if not donnee.ok:
            cellules.append(
                CelluleMatrice(
                    index, regle, INCONCLUSIF,
                    "la regle echoue sur ce mutant dans l'execution tracee, alors "
                    "qu'elle passait dans l'execution normale : les deux mesures ne "
                    "concordent pas, on n'accuse personne",
                )
            )
            continue
        if mutant.ligne in donnee.lignes:
            cellules.append(
                CelluleMatrice(
                    index, regle, AVEUGLE,
                    f"la regle a EXECUTE la ligne {mutant.ligne} du mutant et l'a "
                    "laissee passer",
                )
            )
        else:
            cellules.append(
                CelluleMatrice(
                    index, regle, HORS_PORTEE,
                    f"la regle n'a jamais execute la ligne {mutant.ligne} du mutant",
                )
            )
    return cellules


def formater(matrice: MatriceMutants) -> str:
    """Rend la matrice lisible : un bloc par mutant, et l'etat de chaque regle."""
    lignes: list[str] = []
    if not matrice.mutants:
        return "    " + (matrice.note or "aucun mutant")

    juges = len(matrice.mutants) - len(matrice.non_juges)
    entete = (
        f"    {matrice.tues}/{juges} mutant(s) tue(s) parmi {juges} juge(s)"
        f"  ·  {len(matrice.survivants)} survivant(s)"
    )
    if matrice.non_juges:
        entete += f"  ·  {len(matrice.non_juges)} non juge(s)"
    if matrice.regles_de_forme:
        entete += (
            "  ·  controle(s) de forme (non falsifiable) : "
            + ", ".join(matrice.regles_de_forme)
        )
    lignes.append(entete)
    lignes.append("")

    for index, mutant in enumerate(matrice.mutants):
        tue = index not in matrice.survivants and index not in matrice.non_juges
        marque = "tue" if tue else ("non juge" if index in matrice.non_juges else "SURVIT")
        emplacement = f" ligne {mutant.ligne}" if mutant.ligne else " ligne inconnue"
        lignes.append(
            f"    [{marque}] mutant {index} : {mutant.label}{emplacement}"
        )
        for cellule in matrice.cellules_de(index):
            if cellule.etat == NON_MESURE:
                continue
            lignes.append(f"        {cellule.regle}  {cellule.etat} — {cellule.detail}")
        if tue:
            tueuses = sorted({c.regle for c in matrice.cellules_de(index) if c.etat == TUE})
            if tueuses:
                lignes.append(f"        tue par : {', '.join(tueuses)}")

    if matrice.reserves:
        lignes.append("")
        lignes.append("    RESERVES DE SPECIFICATION (elles ne condamnent pas l'artefact) :")
        for reserve in matrice.reserves:
            lignes.append(f"      - {reserve}")
    return "\n".join(lignes)
