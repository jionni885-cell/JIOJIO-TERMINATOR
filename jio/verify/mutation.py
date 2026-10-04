"""Porte de mutation — « vos tests passent » ne vaut que s'ils peuvent echouer.

Le probleme
-----------
Un artefact peut satisfaire toutes les regles pour la pire des raisons : les
regles ne testent rien. Un test qui ne peut pas echouer est une decoration, et
une decoration qui valide est plus dangereuse qu'une absence de test, parce
qu'elle produit de la confiance sans preuve.

La reponse (technique standard, appliquee ici a l'auto-verification)
--------------------------------------------------------------------
On MUTE l'artefact de facons qui DOIVENT le rendre incorrect, puis on relance la
verification. Si un mutant survit — c'est-a-dire si les regles passent encore —
alors les regles ne distinguent pas le bon artefact d'un artefact faux. Le score
de mutation est la proportion de mutants tues.

Pourquoi c'est une porte ADVISORY, jamais un rejet
--------------------------------------------------
Un mutant survivant ne prouve pas que l'artefact est faux : il prouve que la
*specification* est faible. Condamner l'artefact pour un defaut de specification
serait un faux positif — exactement le genre d'erreur qui detruit la confiance
dans un garde. On emet donc une RESERVE, avec la liste des mutants survivants,
et l'action concrete : ajouter une regle qui les tue.

Mutations choisies
------------------
Peu, mais semantiquement fortes : operateurs de comparaison, operateurs
arithmetiques, bornes de boucle, constantes booleennes, retours anticipes. Le
but n'est pas la couverture exhaustive (cout exponentiel) mais de detecter la
classe de faiblesse la plus courante : des tests qui verifient la forme du
resultat sans verifier sa valeur.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass

__all__ = ["Mutation", "MutationReport", "mutate", "MUTATION_BUDGET"]

#: Nombre maximum de mutants executes. Chaque mutant coute une passe complete de
#: verification : on borne le cout, on ne cherche pas l'exhaustivite.
MUTATION_BUDGET = 4

_SWAP_CMP = {
    ast.Eq: ast.NotEq,
    ast.NotEq: ast.Eq,
    ast.Lt: ast.GtE,
    ast.LtE: ast.Gt,
    ast.Gt: ast.LtE,
    ast.GtE: ast.Lt,
}

_SWAP_BIN = {
    ast.Add: ast.Sub,
    ast.Sub: ast.Add,
    ast.Mult: ast.FloorDiv,
    ast.FloorDiv: ast.Mult,
    ast.Mod: ast.FloorDiv,
}


@dataclass(frozen=True)
class Mutation:
    """Une mutation appliquee : description lisible + source mutee.

    ``ligne`` est la ligne DU TEXTE MUTE ou le changement se voit. Elle n'est pas
    copiee de l'arbre d'origine : `ast.unparse` reecrit la mise en forme (les
    commentaires et les lignes vides disparaissent), donc la ligne d'origine ne
    designe plus rien dans le mutant. Elle est retrouvee en comparant les deux
    arbres, et elle sert a repondre a la seule question qui compte pour une
    specification : CE CODE A-T-IL ETE EXECUTE par la regle ?
    """

    label: str
    source: str
    ligne: int = 0


@dataclass
class MutationReport:
    """Resultat : combien de mutants tues, et lesquels ont survecu."""

    total: int = 0
    killed: int = 0
    survived: tuple[Mutation, ...] = ()
    unusable: tuple[str, ...] = ()
    #: Mutants que la preuve n'a PAS pu juger (controles absents, panne de preuve).
    #: Ils ne sont ni tues ni survivants : les compter tues gonflait le score d'une
    #: preuve qui n'a pas eu lieu, et la porte annoncait alors une specification
    #: solide sur la foi d'un silence. Mesure faite sur `median` : quatre mutants,
    #: un seul juge, score annonce 75 % — la vraie part jugee etait 100 % d'un seul
    #: mutant, et personne ne pouvait le voir dans le chiffre.
    non_juges: tuple[Mutation, ...] = ()
    #: La matrice mutants x regles (`jio.verify.matrice`) quand elle a pu etre
    #: construite : elle nomme les regles aveugles et les lignes sans aucune regle.
    #: Typage volontairement large : `matrice` importe ce module, l'inverse serait
    #: un cycle d'import pour un seul attribut.
    matrice: object | None = None

    @property
    def juges(self) -> int:
        """Mutants sur lesquels une preuve a effectivement porte."""
        return self.total - len(self.non_juges)

    @property
    def score(self) -> float:
        """Part des mutants tues, dans [0, 1]. 0 mutant executable -> 0."""
        return self.killed / self.total if self.total else 0.0

    @property
    def weak(self) -> bool:
        """Vrai si la specification n'a pas su tuer un mutant executable.

        Un mutant non juge compte comme une faiblesse : « on n'a pas pu prouver »
        n'est pas « on a prouve ». L'inverse — compter tue ce qu'on n'a pas juge —
        est precisement la confiance sans preuve que ce module existe pour empecher.
        """
        return self.total > 0 and self.killed < self.total

    def summary(self) -> str:
        if not self.total:
            return "aucun mutant executable : la porte de mutation n'a rien pu tester"
        texte = (
            f"{self.killed}/{self.total} mutant(s) tue(s) — "
            f"score de mutation {self.score:.0%}"
        )
        if self.non_juges:
            texte += f" · {len(self.non_juges)} NON JUGE(S) (preuve impossible)"
        return texte


class _Mutator(ast.NodeTransformer):
    """Applique UNE mutation au premier site eligible rencontre."""

    def __init__(self, index: int) -> None:
        self.index = index
        self.seen = 0
        self.label = ""

    def _hit(self, label: str) -> bool:
        """Vrai si c'est ce site qui doit etre mute (et non un precedent)."""
        current = self.seen
        self.seen += 1
        if current == self.index:
            self.label = label
            return True
        return False

    # -- sites de mutation -------------------------------------------------- #

    def visit_Compare(self, node: ast.Compare) -> ast.AST:
        self.generic_visit(node)
        if len(node.ops) != 1:
            return node
        op = type(node.ops[0])
        if op not in _SWAP_CMP:
            return node
        if self._hit(f"comparaison {op.__name__} -> {_SWAP_CMP[op].__name__}"):
            node.ops = [_SWAP_CMP[op]()]
        return node

    def visit_BinOp(self, node: ast.BinOp) -> ast.AST:
        self.generic_visit(node)
        op = type(node.op)
        if op not in _SWAP_BIN:
            return node
        if self._hit(f"operateur {op.__name__} -> {_SWAP_BIN[op].__name__}"):
            node.op = _SWAP_BIN[op]()
        return node

    def visit_Constant(self, node: ast.Constant) -> ast.AST:
        if isinstance(node.value, bool):
            if self._hit(f"booleen {node.value} -> {not node.value}"):
                return ast.copy_location(ast.Constant(value=not node.value), node)
            return node
        if isinstance(node.value, int) and not isinstance(node.value, bool):
            if self._hit(f"constante {node.value} -> {node.value + 1}"):
                return ast.copy_location(ast.Constant(value=node.value + 1), node)
        return node

    def visit_If(self, node: ast.If) -> ast.AST:
        """Vide un bloc conditionnel : traque les branches jamais exercees."""
        self.generic_visit(node)
        if node.body and self._hit("bloc conditionnel vide"):
            node.body = [ast.copy_location(ast.Pass(), node.body[0])]
        return node


def _ligne_du_changement(avant: str, apres: str) -> int:
    """La ligne ou le texte mute DIFFERE du texte d'origine, dans le texte mute.

    `ast.unparse` reecrit la mise en forme : commentaires, lignes vides et
    parentheses disparaissent. La ligne du noeud d'origine ne designe donc plus
    rien dans le mutant — mesurer la couverture avec elle reviendrait a regarder
    une ligne qui n'a pas bouge, et a declarer « hors de portee » une regle qui a
    pourtant execute le code mute.

    On parcourt donc les DEUX arbres en parallele et on rend la ligne, DANS LE
    MUTANT, du premier noeud qui differe. C'est exactement le noeud mute (ou le
    `pass` qui le remplace), et rien d'autre : les arbres sont identiques avant.
    """
    try:
        gauche = ast.parse(avant)
        droite = ast.parse(apres)
    except SyntaxError:  # pragma: no cover - la source a deja ete validee en amont
        return 0
    for noeud_gauche, noeud_droite in zip(ast.walk(gauche), ast.walk(droite)):
        if _signature(noeud_gauche) != _signature(noeud_droite):
            return int(getattr(noeud_droite, "lineno", 0) or 0)
    return 0


def _signature(noeud: ast.AST) -> tuple[str, tuple[tuple[str, object], ...]]:
    """Signature SUPERFICIELLE d'un noeud : son type et ses champs directs.

    Les enfants sont remplaces par leur type. C'est ce qui fait la difference entre
    « le noeud a change » et « un de ses descendants a change » : sans cela, le
    premier noeud qui differe est toujours le MODULE (il contient tout), il n'a pas
    de numero de ligne, et la matrice ne sait plus rien localiser — defaut mesure a
    la premiere version : toutes les cellules rendaient « ligne du changement
    inconnue », donc « inconclusif », donc aucune action.
    """

    def simplifier(valeur: object) -> object:
        if isinstance(valeur, ast.AST):
            return f"<{type(valeur).__name__}>"
        if isinstance(valeur, list):
            return [simplifier(item) for item in valeur]
        return valeur

    return (
        type(noeud).__name__,
        tuple((champ, simplifier(valeur)) for champ, valeur in ast.iter_fields(noeud)),
    )


def mutate(source: str, *, budget: int = MUTATION_BUDGET) -> list[Mutation]:
    """Genere jusqu'a `budget` mutations semantiquement fortes.

    Renvoie une liste vide si la source ne compile pas : muter du code invalide
    ne teste rien.
    """
    try:
        ast.parse(source)
    except SyntaxError:
        return []

    out: list[Mutation] = []
    for index in range(budget * 4):  # on sonde plus de sites que de mutants gardes
        if len(out) >= budget:
            break
        mutator = _Mutator(index)
        try:
            mutated = mutator.visit(ast.parse(source))
            if not mutator.label:
                # Aucun site a cet index : tous les sites eligibles sont epuises.
                break
            ast.fix_missing_locations(mutated)
            text = ast.unparse(mutated)
        except Exception:
            continue
        if text != source and text not in {m.source for m in out}:
            out.append(
                Mutation(
                    label=mutator.label,
                    source=text,
                    ligne=_ligne_du_changement(source, text),
                )
            )
    return out
