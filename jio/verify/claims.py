"""Temoins pour la PROSE : une affirmation verifiable doit etre verifiee.

LE MANQUE. Tout le harness prouve du CODE : des regles, des exemples executables,
des mutants. Sur une mission generaliste — une analyse, un rapport, une note de
recherche — il n'y a rien a executer, donc JIO s'abstient. Or un texte contient des
affirmations VERIFIABLES, et c'est precisement la que se logent les hallucinations :
un calcul annonce faux, un chemin de fichier qui n'existe pas, un bloc de code
presente comme valide et qui ne compile pas.

CE QUE CE MODULE VERIFIE, et rien de plus — la retenue est le sujet :

  1. **arithme­tique** : « 12 + 30 = 42 ». Un calcul est vrai ou faux, sans
     interpretation. C'est le seul temoin de prose qui ne soit jamais discutable ;
  2. **bloc de code annonce comme Python** : il doit au moins COMPILER. Une erreur de
     syntaxe dans un bloc ```python est un fait, pas une opinion. Un bloc non marque
     reste une illustration et n'est juge que s'il ne compile pas — signale, jamais
     accuse ;
  3. **chemin cite** : un token qui ressemble a un fichier (`jio/cli.py`) et qui
     n'existe pas sous la racine visee est SIGNALE. Jamais accuse : un document a le
     droit de decrire un fichier a creer, ou de citer un chemin d'une autre machine.

CE QUE CE MODULE NE VERIFIE PAS : le style, la pertinence, la veracite d'une opinion,
une citation attribuee a une source absente. Un outil qui pretend juger cela produit
des faux positifs, et un outil qui accuse a tort est desactive au bout de deux jours.

Toute verification rend une PREUVE : la commande, l'extrait exact du texte, et le
resultat. Rien n'est conclu sur du vide.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

__all__ = [
    "Affirmation",
    "Genre",
    "RapportProse",
    "est_un_document",
    "extraction",
    "verifier",
]


class Genre(str, Enum):
    ARITHMETIQUE = "arithmetique"
    BLOC_CODE = "bloc-code"
    CHEMIN = "chemin"


#: Severite : ce qui est CERTAIN est bloquant, ce qui est probable est signale.
SEVERITE = {
    Genre.ARITHMETIQUE: "VIOLATION",
    Genre.BLOC_CODE: "VIOLATION",     # le bloc est ANNONCE comme python
    Genre.CHEMIN: "SIGNAL",
}


@dataclass(frozen=True)
class Affirmation:
    """Une affirmation verifiable, avec son extrait EXACT : c'est la preuve.

    `cite` distingue une AFFIRMATION d'une CITATION. Un document qui parle
    d'arithmetique cite forcement des calculs faux — c'est le sujet. Les confondre
    condamnait tout texte expliquant une erreur, c'est-a-dire precisement les
    documents les plus utiles. Une citation se verifie quand meme : elle est
    SIGNALEE, jamais bloquante.
    """

    genre: Genre
    extrait: str
    position: int
    #: Ce qu'il faut verifier, selon le genre.
    detail: str = ""
    #: Vrai si le fragment est presente comme une CITATION (entre backticks).
    cite: bool = False

    def resume(self) -> str:
        return f"[{self.genre.value}] {self.extrait[:80]}"


# --------------------------------------------------------------------------- #
# Extraction — aucune heuristique floue : des motifs precis
# --------------------------------------------------------------------------- #

#: Un calcul ecrit en toutes lettres : « 12 + 30 = 42 », « 7 × 6 = 42 », « 100/4 = 25 ».
#: Les symboles de multiplication s'ecrivent differemment selon la source : `*`,
#: `x` et le vrai signe `×`. Les ecrire a la main dans une classe de caracteres a
#: produit un motif qui ne matchait PAS le signe `×` d'un document reel — un calcul
#: faux passait donc sans etre vu. La classe est construite ICI, a partir de la table.
OPERATEURS = {
    "+": "add", "-": "sub", "*": "mul", "×": "mul", "x": "mul", "/": "truediv",
}
_CLASSE_OPERATEURS = "".join(re.escape(symbole) for symbole in OPERATEURS)
_CALCUL = re.compile(
    r"(?<![\w.])"
    r"(?P<gauche>\d+(?:[.,]\d+)?"
    r"(?:\s*[" + _CLASSE_OPERATEURS + r"]\s*\d+(?:[.,]\d+)?)+)"
    # Le regard arriere-final doit refuser un CHIFFRE qui suivrait, pas un point :
    # « le total de 7 x 6 = 43. » est une phrase, et exiger « pas de point apres »
    # faisait manquer tous les calculs en fin de phrase — donc precisement ceux qu'un
    # rapport ecrit. Mesure : un calcul FAUX passait a cause de sa ponctuation.
    r"\s*(?:=|vaut|donne|fait)\s*(?P<droite>-?\d+(?:[.,]\d+)?)(?![\w])(?!\.\d)"
)
_BLOC = re.compile(r"```(?P<langue>[A-Za-z0-9_+-]*)\n(?P<code>.*?)```", re.DOTALL)
#: Un chemin cite : au moins un dossier, une extension connue, entre backticks.
_CHEMIN = re.compile(r"`(?P<chemin>[A-Za-z0-9_.-]+/[A-Za-z0-9_./-]+\.[A-Za-z0-9]{1,6})`")
#: Langues dont on sait prouver la validite syntaxique. Un bloc `bash` n'est PAS du
#: Python : le compiler comme tel produisait une accusation FAUSSE sur tout document
#: contenant un exemple en ligne de commande — c'est-a-dire presque tous. On ne juge
#: que ce que le document ANNONCE comme Python, et rien d'autre.
LANGUES_JUGEES = frozenset({"python", "py", "python3"})

#: Motifs qui ne laissent aucun doute : la ligne est du Python. Sert aux blocs NON
#: MARQUES, qu'on ne juge que s'ils sont manifestement du code. Sans ce filtre, un
#: diagramme ASCII ou une sortie de terminal etait signale comme « ne compile pas » :
#: du bruit, et 18 occurrences sur le seul README de ce depot.
_CODE_EVIDENT = re.compile(
    r"^\s*(?:def |class |async def |import |from \S+ import |@\w+|return |"
    r"if __name__ == )",
    re.MULTILINE,
)

_EXTENSIONS = {
    ".py", ".md", ".json", ".jsonl", ".toml", ".yaml", ".yml", ".txt", ".sh",
    ".mdc", ".cfg", ".ini", ".js", ".ts", ".html", ".css", ".sql", ".csv",
}


def _nombre(texte: str) -> float:
    return float(texte.replace(",", "."))


def _calcule(noeud: ast.AST) -> float | None:
    """Valeur du noeud, ou `None` des qu'il sort du domaine autorise.

    Un seul passage fait a la fois le CONTROLE et le CALCUL : ecrire la verification a
    part invitait a la desynchroniser du calcul (et `ast.walk` la rendait fausse, en
    visitant les noeuds d'operateur comme `ast.Add`).

    Aucun `eval` : le calcul est fait ICI, sur les seuls noeuds admis. Un document est
    du contenu NON FIABLE ; l'evaluation doit etre incapable d'atteindre autre chose
    que des nombres. `ast.Expression` -> `Constant` -> `UnaryOp` -> `BinOp`, rien
    d'autre n'a de sens.
    """
    if isinstance(noeud, ast.Expression):
        return _calcule(noeud.body)
    if isinstance(noeud, ast.Constant):
        if isinstance(noeud.value, bool) or not isinstance(noeud.value, (int, float)):
            return None
        return float(noeud.value)
    if isinstance(noeud, ast.UnaryOp):
        valeur = _calcule(noeud.operand)
        if valeur is None:
            return None
        if isinstance(noeud.op, ast.USub):
            return -valeur
        if isinstance(noeud.op, ast.UAdd):
            return valeur
        return None
    if isinstance(noeud, ast.BinOp):
        gauche, droite = _calcule(noeud.left), _calcule(noeud.right)
        if gauche is None or droite is None:
            return None
        if isinstance(noeud.op, ast.Add):
            return gauche + droite
        if isinstance(noeud.op, ast.Sub):
            return gauche - droite
        if isinstance(noeud.op, ast.Mult):
            return gauche * droite
        if isinstance(noeud.op, ast.Div):
            return None if droite == 0 else gauche / droite
        return None
    return None


def _evalue_calcul(expression: str) -> float | None:
    """Evalue une expression arithmetique, ou `None` si elle sort du domaine.

    Le texte vient d'un document non fiable : il est PARSÉ, puis interprete noeud par
    noeud par `_calcule`. Une expression qui tente quoi que ce soit d'autre — un nom,
    un appel, une comparaison — ne rencontre aucune branche et vaut `None`.
    """
    propre = expression
    for symbole, nature in OPERATEURS.items():
        if nature == "mul" and symbole != "*":
            propre = propre.replace(symbole, "*")
    propre = propre.replace(",", ".")
    try:
        arbre = ast.parse(propre, mode="eval")
    except SyntaxError:
        return None
    return _calcule(arbre)


def _plages_citees(texte: str, debut: int, fin: int) -> bool:
    """Vrai si [debut, fin) tombe dans un fragment entre backticks, sur la meme ligne.

    Un backtick isole un fragment LITTERAL en Markdown : ce qui est dedans est cite,
    pas affirme. On apparie les backticks de la ligne (les paires sont consecutives)
    plutot que de chercher la paire la plus proche, ce qui se trompe des qu'une ligne
    en contient plusieurs.
    """
    ligne_debut = texte.rfind("\n", 0, debut) + 1
    ligne_fin = texte.find("\n", fin)
    ligne = texte[ligne_debut:ligne_fin if ligne_fin != -1 else len(texte)]
    marques = [i for i, c in enumerate(ligne) if c == "`"]
    for a, b in zip(marques[0::2], marques[1::2]):
        if a <= debut - ligne_debut and fin - ligne_debut <= b + 1:
            return True
    return False


def extraction(texte: str) -> tuple[Affirmation, ...]:
    """Toutes les affirmations verifiables d'un document, dans l'ordre du texte."""
    trouvailles: list[Affirmation] = []
    for bloc in _BLOC.finditer(texte):
        langue = (bloc.group("langue") or "").lower()
        trouvailles.append(
            Affirmation(
                genre=Genre.BLOC_CODE,
                extrait=bloc.group("code").strip()[:400],
                position=bloc.start("code"),
                detail=langue or "sans-langue",
            )
        )
    for calcul in _CALCUL.finditer(texte):
        trouvailles.append(
            Affirmation(
                genre=Genre.ARITHMETIQUE,
                extrait=calcul.group(0).strip(),
                position=calcul.start(),
                detail=f"{calcul.group('gauche')}|{calcul.group('droite')}",
                cite=_plages_citees(texte, calcul.start(), calcul.end()),
            )
        )
    for chemin in _CHEMIN.finditer(texte):
        brut = chemin.group("chemin")
        if Path(brut).suffix.lower() not in _EXTENSIONS:
            continue
        trouvailles.append(
            Affirmation(
                genre=Genre.CHEMIN, extrait=brut, position=chemin.start(), detail=brut
            )
        )
    return tuple(sorted(trouvailles, key=lambda a: a.position))


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Verification:
    """Le sort d'une affirmation, avec la preuve qui le justifie."""

    affirmation: Affirmation
    ok: bool
    bloquant: bool
    message: str


@dataclass
class RapportProse:
    """Ce qui a ete PROUVE, ce qui a ete REFUTE, et ce qui reste non conclu."""

    verifications: tuple[Verification, ...] = ()
    #: Affirmations qu'on a su verifier (le reste est declare, jamais suppose).
    verifiees: int = 0
    refutees: int = 0
    signalees: int = 0

    @property
    def bloquantes(self) -> tuple[Verification, ...]:
        return tuple(v for v in self.verifications if not v.ok and v.bloquant)

    @property
    def conforme(self) -> bool:
        return not self.bloquantes

    def resume(self) -> str:
        return (
            f"{self.verifiees} affirmation(s) verifiee(s) · "
            f"{self.refutees} refutee(s) dont {len(self.bloquantes)} bloquante(s) · "
            f"{self.signalees} signalee(s) non concluante(s)"
        )


def _verifier_une(affirmation: Affirmation, racine: Path) -> Verification | None:
    """Verifie une affirmation. Rend None quand elle n'est PAS verifiable."""
    if affirmation.genre is Genre.ARITHMETIQUE:
        gauche, droite = affirmation.detail.split("|")
        try:
            attendu = _nombre(droite)
            obtenu = _evalue_calcul(gauche)
        except (ValueError, OverflowError):
            # Une expression non evaluable n'est pas une affirmation. On nomme les
            # deux seules exceptions possibles ici (`_calcule` ne peut pas en lever
            # d'autre) plutot que d'attraper tout : un `except Exception` masquerait
            # aussi un vrai bug dans ce module.
            return None
        if obtenu is None:
            return None
        ok = abs(obtenu - attendu) < 1e-9
        if affirmation.cite:
            # Une CITATION : le document parle d'un calcul, il ne l'affirme pas. Un
            # texte qui explique les erreurs d'arithmetique en cite forcement.
            return Verification(
                affirmation=affirmation, ok=ok, bloquant=False,
                message=(
                    f"calcul CITE (entre backticks) : « {affirmation.extrait} » — "
                    f"{gauche.strip()} vaut {obtenu:g}, le texte cite {attendu:g}. "
                    "Une citation se signale, elle ne condamne pas le document."
                ),
            )
        return Verification(
            affirmation=affirmation,
            ok=ok,
            bloquant=True,
            message=(
                f"calcul EXACT : « {affirmation.extrait} » — {gauche.strip()} vaut "
                f"{obtenu:g}, le texte annonce {attendu:g}"
            ),
        )

    if affirmation.genre is Genre.BLOC_CODE:
        if affirmation.detail not in LANGUES_JUGEES:
            # Deux cas, et un seul est juge :
            #   * langue ANNONCEE (bash, json, console...) : elle n'est pas du Python,
            #     donc il n'y a rien a en dire. La compiler comme Python accusait a
            #     tort tout document contenant un exemple de terminal ;
            #   * bloc NON MARQUE : il ne fait aucune affirmation de langage. On ne le
            #     juge que s'il est manifestement du code — un diagramme ou une sortie
            #     de programme n'est pas une specification.
            if affirmation.detail != "sans-langue":
                return None
            if not _CODE_EVIDENT.search(affirmation.extrait or ""):
                return None
            try:
                ast.parse(affirmation.extrait or "pass")
            except SyntaxError as exc:
                return Verification(
                    affirmation=affirmation, ok=False, bloquant=False,
                    message=(
                        f"bloc NON MARQUE qui est manifestement du code et qui ne "
                        f"compile pas ({exc.msg}) : illustration ou erreur, on signale "
                        "sans trancher"
                    ),
                )
            return None
        try:
            ast.parse(affirmation.extrait or "pass")
        except SyntaxError as exc:
            return Verification(
                affirmation=affirmation, ok=False, bloquant=True,
                message=(
                    f"bloc presente comme `{affirmation.detail}` et qui NE COMPILE PAS : "
                    f"{exc.msg} (ligne {exc.lineno}). Un fait, pas une opinion."
                ),
            )
        return Verification(
            affirmation=affirmation, ok=True, bloquant=True,
            message=f"bloc `{affirmation.detail}` compile",
        )

    # CHEMIN : signale, jamais accuse.
    cible = (racine / affirmation.detail) if racine else Path(affirmation.detail)
    if cible.exists():
        return Verification(affirmation=affirmation, ok=True, bloquant=False,
                            message=f"chemin cite present : {affirmation.detail}")
    return Verification(
        affirmation=affirmation, ok=False, bloquant=False,
        message=(
            f"chemin cite INTROUVABLE sous {racine} : `{affirmation.detail}`. Un document "
            "peut decrire un fichier a creer ou citer une autre machine — on le signale, "
            "on n'accuse pas."
        ),
    )


def verifier(texte: str, *, racine: Path | None = None) -> RapportProse:
    """Verifie tout ce qui est verifiable dans un document, et declare le reste.

    `racine` est la racine a partir de laquelle un chemin cite est cherche. Sans
    elle, les chemins ne sont ni confirmes ni accuses : ils sont ignores — faute de
    reference, il n'y a rien a dire.
    """
    rapport = RapportProse()
    sorties: list[Verification] = []
    for affirmation in extraction(texte):
        if affirmation.genre is Genre.CHEMIN and racine is None:
            continue
        verification = _verifier_une(affirmation, racine or Path("."))
        if verification is None:
            continue
        sorties.append(verification)
    rapport.verifications = tuple(sorties)
    rapport.verifiees = sum(1 for v in sorties if v.ok)
    rapport.refutees = sum(1 for v in sorties if not v.ok and v.bloquant)
    rapport.signalees = sum(1 for v in sorties if not v.ok and not v.bloquant)
    return rapport


#: Suffixes de documents ecrits. Un `.py` n'en fait jamais partie, meme s'il ne
#: compile pas : un source casse doit rester du CODE, et etre juge comme tel.
SUFFIXES_DOCUMENT = frozenset({".md", ".markdown", ".rst", ".txt", ".org", ".adoc"})


def est_un_document(chemin: Path, texte: str) -> bool:
    """Vrai si la cible est un DOCUMENT (a juger comme prose) et non du code.

    Pourquoi cette fonction existe : `jio audit` sur un rapport rendait « la source
    ne compile pas » — vrai, et inutile. Un utilisateur qui demande l'audit d'un
    document doit obtenir les temoins du document, sans avoir a savoir laquelle des
    deux familles s'applique. Une seule porte, deux familles de temoins.

    Regle de decision, volontairement mecanique : le suffixe tranche d'abord (un `.py`
    reste du code, meme casse), puis la capacite a etre parse comme du Python.
    """
    if chemin.suffix.lower() in SUFFIXES_DOCUMENT:
        return True
    if chemin.suffix.lower() in {".py", ".pyi"}:
        return False
    try:
        ast.parse(texte)
    except SyntaxError:
        return True
    return False
