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
    "MAX_AFFIRMATIONS",
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

#: Le cote DROIT d'un calcul : un resultat annonce. On cherche `= 42`, pas l'expression
#: entiere — l'expression est ensuite remontee a la main, bornee.
#:
#: Pourquoi ce renversement : la version precedente cherchait `gauche = droite` d'un
#: seul motif, avec un groupe repete. Sur une chaine longue SANS `=`, le moteur
#: d'expressions regulieres essayait toutes les decoupes possibles et ne rendait jamais
#: la main : mesure sur `"1 + " * 50000`, la verification ne terminait pas (plus de
#: 600 secondes, commande interrompue). Un contenu non fiable ne doit pas pouvoir
#: fixer le temps de travail de l'outil.
_CALCUL_DROITE = re.compile(
    # `=` d'affectation ou de comparaison (`==`, `>=`, `:=`) : pas un resultat annonce.
    r"(?:(?<![<>=!:+\-*/])=(?!=)|\b(?:vaut|donne|fait)\b)"
    # Le regard final refuse un CHIFFRE qui suivrait, pas un point : « le total de
    # 7 x 6 = 43. » est une phrase, et exiger « pas de point apres » faisait manquer
    # tous les calculs en fin de phrase — donc ceux qu'un rapport ecrit vraiment.
    r"\s*(?P<droite>-?\d+(?:[.,]\d+)?)(?![\w])(?!\.\d)"
    # Un RESULTAT n'est pas suivi d'une operation. Dans « le total vaut 7 x 6 = 43 »,
    # le mot « vaut » matchait « vaut 7 » : 7 est le premier TERME d'une expression,
    # pas un resultat. Aucune expression ne se remontait alors a sa gauche, et le
    # rapport annoncait « 1 calcul trop long pour etre evalue » — une LACUNE INVENTEE.
    # Une lacune fausse est pire qu'aucune : elle apprend a ignorer les vraies.
    r"(?!\s*[" + _CLASSE_OPERATEURS + r"]\s*-?\d)"
)

#: Une chaine d'operateurs : `1 + 2`, `3 x 4`, `100/4`. La repetition est BORNEE
#: (`{0,12}`) : une expression de prose n'a jamais quinze termes, et une borne rend le
#: temps de recherche lineaire au lieu d'exponentiel.
_CHAINE = re.compile(
    # AU MOINS un operateur : `12 + 30`, `7 x 6`, `100/4`. Sans cette exigence,
    # « 4 mises a jour sur 4 = 75 % » etait lu comme le calcul « 4 = 75 » — refuse,
    # donc une accusation fausse sur une phrase de prose parfaitement correcte.
    r"(?P<expr>\d+(?:[.,]\d+)?(?:\s*[_OPE_]\s*\d+(?:[.,]\d+)?){1,32})$".replace(
        "_OPE_", _CLASSE_OPERATEURS
    )
)

#: Longueur maximale remontee avant l'expression. Au-dela, on ne devine pas : le
#: calcul est declare NON VERIFIE plutot que verifie sur une partie de ses termes.
_FENETRE_EXPRESSION = 240


def _expression_avant_detail(ligne: str, fin: int) -> tuple[str | None, str]:
    """L'expression qui se termine juste avant `fin`, ET la cause de son absence.

    Rend `(expression, cause)` ou `cause` vaut `ok`, `coupee` ou `absente`. La cause
    n'est pas un ornement : « coupee » demande de raccourcir l'expression, « absente »
    demande de l'ecrire. Les confondre faisait afficher « calcul trop long » pour un
    chiffre qu'AUCUNE expression n'accompagnait — un message faux dans la seule partie
    du rapport consacree a l'honnetete.

    Remonte a partir du `=` : on borne la fenetre, on exige que la chaine colle
    exactement a la fin de cette fenetre, et on VERIFIE qu'elle ne continue pas
    a gauche. Ce dernier controle est celui qui empeche l'accusation fausse : evaluer
    la fin d'une longue somme et la comparer au total produirait un refus invente.
    """
    debut_fenetre = max(0, fin - _FENETRE_EXPRESSION)
    fenetre = ligne[debut_fenetre:fin].rstrip()
    correspondance = _CHAINE.search(fenetre)
    if correspondance is None:
        return None, "absente"
    depart = debut_fenetre + correspondance.start("expr")
    # La chaine continue-t-elle a gauche ? Si oui, elle a ete coupee (par la fenetre
    # ou par la borne de termes) : on s'abstient. Evaluer une PARTIE des termes et la
    # comparer au total produirait un refus invente — la pire des sorties possibles.
    #
    # Seul un OPERATEUR signale une continuation. Un chiffre juste avant ne le peut
    # pas : `\d+` est gourmand, donc l'expression commence toujours au debut de la
    # suite de chiffres. Exiger « pas de chiffre avant » refusait tout sur une ligne
    # repetant plusieurs calculs (« 1 + 2 = 3 1 + 2 = 3 »), mesure faite.
    if _continue_a_gauche(ligne[:depart]):
        return None, "coupee"
    # La fenetre a peut-etre coupe le DEBUT de l'expression (ligne de plus de
    # `_FENETRE_EXPRESSION` caracteres) : la chaine commence alors au premier caractere
    # de la fenetre, et le chiffre precedent serait ignore. S'abstenir est la seule
    # sortie sure — un refus invente coute plus cher qu'un fait non verifie.
    if debut_fenetre > 0 and correspondance.start("expr") == 0:
        return None, "coupee"
    return correspondance.group("expr").strip(), "ok"


def _continue_a_gauche(avant: str) -> bool:
    """Un OPERATEUR reste-t-il a gauche de l'expression ? (donc : est-elle coupee ?)

    Piege trouve en auditant le README de ce depot : « le calcul fAUX » se termine par
    un `x`, et `x` est le symbole de multiplication de la prose francaise. La garde le
    prenait pour un operateur, declarait la chaine coupee, et le rapport affichait
    « 1 calcul trop long » sur une phrase qui ne contient aucun calcul coupe.

    Un operateur alphabetique (`x`) doit donc etre DETACHE pour en etre un : precede
    d'un separateur ou du debut. `3 x 4` : oui. `faux` : non.
    """
    gauche = avant.rstrip()
    if not gauche or gauche[-1] not in OPERATEURS:
        return False
    if not gauche[-1].isalpha():
        return True
    return len(gauche) < 2 or not (gauche[-2].isalnum() or gauche[-2] == "_")


def _expression_avant(ligne: str, fin: int) -> str | None:
    """L'expression arithmetique qui se termine juste avant `fin`, ou `None`."""
    return _expression_avant_detail(ligne, fin)[0]

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


def _fragments_cites(ligne: str) -> tuple[tuple[int, int], ...]:
    """Les plages entre backticks d'une ligne, en offsets RELATIFS a cette ligne.

    Un backtick isole un fragment LITTERAL en Markdown : ce qui est dedans est cite,
    pas affirme. On apparie les backticks de la ligne (les paires sont consecutives)
    plutot que de chercher la paire la plus proche, ce qui se trompe des qu'une ligne
    en contient plusieurs.
    """
    marques = [i for i, c in enumerate(ligne) if c == "`"]
    return tuple(zip(marques[0::2], marques[1::2]))


def _est_cite(fragments: tuple[tuple[int, int], ...], debut: int, fin: int) -> bool:
    """Vrai si [debut, fin) (offsets sur la LIGNE) tombe dans un fragment cite."""
    return any(a <= debut and fin <= b + 1 for a, b in fragments)


def extraction(texte: str) -> tuple[Affirmation, ...]:
    """Toutes les affirmations verifiables d'un document, dans l'ordre du texte."""
    return _extraction_detail(texte)[0]


def _extraction_detail(texte: str) -> tuple[tuple[Affirmation, ...], int, int]:
    """Rend `(affirmations, ignorees_par_volume, chaines_coupees)`.

    Les deux compteurs existent parce qu'une verification PARTIELLE doit se savoir
    partielle. Deux limites, toutes deux declarees dans le rapport :

      * `ignorees_par_volume` : au-dela de `MAX_AFFIRMATIONS` (contenu non fiable : il
        ne fixe pas le temps de travail de l'outil) ;
      * `chaines_non_evaluees` : un calcul dont la chaine depasse la borne de termes,
        ou que la fenetre a coupee. On ne l'evalue PAS sur une partie de ses termes :
        comparer la fin d'une longue somme a son total inventerait un refus ;
    Un resultat annonce dont AUCUNE expression n'est lisible a gauche n'est pas compte :
    « le total vaut 42 ms » est une phrase, `seq=0` est un extrait de code. Les compter
    produisait DOUZE lacunes inventees sur le seul README de ce depot (mesure) — et une
    lacune inventee apprend a ignorer les vraies. Seule une chaine COUPEE est declaree :
    la, un calcul existe et n'a pas pu etre juge.

    Les deux etaient d'abord silencieux. Un calcul faux de trente-trois termes passait
    alors sans etre ni verifie ni compte : exactement le silence que ce projet refuse.
    """
    trouvailles: list[Affirmation] = []
    non_evaluees = 0

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
        if len(trouvailles) >= MAX_AFFIRMATIONS:
            return _trier(trouvailles), _compter_reste(texte, len(trouvailles)), 0

    # Les fragments cites d'une ligne sont calcules UNE fois. La version precedente
    # rescannait la ligne entiere pour chaque calcul : un document d'une ligne
    # contenant 20 000 calculs demandait 114 secondes (mesure) — un contenu non
    # fiable ne doit pas pouvoir fixer le temps de travail de l'outil.
    fragments: dict[int, tuple[tuple[int, int], ...]] = {}
    for calcul in _CALCUL_DROITE.finditer(texte):
        debut_ligne = texte.rfind("\n", 0, calcul.start()) + 1
        fin_ligne = texte.find("\n", calcul.start())
        ligne_texte = texte[debut_ligne:fin_ligne if fin_ligne != -1 else len(texte)]
        if debut_ligne not in fragments:
            fragments[debut_ligne] = _fragments_cites(ligne_texte)
        gauche, cause = _expression_avant_detail(ligne_texte, calcul.start() - debut_ligne)
        if gauche is None:
            # Seule une chaine COUPEE est une lacune : un calcul existe et n'a pas pu
            # etre juge. Une annonce sans expression (« le total vaut 42 ms », `seq=0`)
            # n'est pas un calcul manque, c'est du texte ou du code : la compter
            # fabriquait des lacunes, et une lacune inventee apprend a ignorer les
            # vraies. La cause est calculee par `_expression_avant_detail`, donc il n'y
            # a qu'un seul endroit qui sait POURQUOI il a refuse.
            if cause == "coupee":
                non_evaluees += 1
            continue
        depart = debut_ligne + ligne_texte.rfind(gauche)
        trouvailles.append(
            Affirmation(
                genre=Genre.ARITHMETIQUE,
                extrait=f"{gauche} = {calcul.group('droite')}",
                position=depart,
                detail=f"{gauche}|{calcul.group('droite')}",
                # `_est_cite` compare des offsets SUR LA LIGNE : passer une position
                # absolue faisait perdre le marquage « cite », et le calcul faux cite
                # par un document qui en PARLE redevenait bloquant.
                cite=_est_cite(
                    fragments[debut_ligne], depart - debut_ligne, calcul.end() - debut_ligne
                ),
            )
        )
        if len(trouvailles) >= MAX_AFFIRMATIONS:
            return (
                _trier(trouvailles),
                _compter_reste(texte, len(trouvailles)),
                non_evaluees,
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
        if len(trouvailles) >= MAX_AFFIRMATIONS:
            break
    return _trier(trouvailles), 0, non_evaluees


def _compter_reste(texte: str, deja: int) -> int:
    """Combien d'affirmations existent au-dela de la limite de volume."""
    candidats = len(_BLOC.findall(texte)) + len(_CALCUL_DROITE.findall(texte))
    candidats += sum(
        1 for c in _CHEMIN.finditer(texte)
        if Path(c.group("chemin")).suffix.lower() in _EXTENSIONS
    )
    return max(0, candidats - max(deja, MAX_AFFIRMATIONS))


def _trier(trouvailles: list[Affirmation]) -> tuple[Affirmation, ...]:
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
    #: Affirmations AU-DELA de la limite de volume (document volumineux) : non
    #: verifiees. Ce chiffre doit voyager avec le rapport : sans lui, une verification
    #: partielle se lirait comme un quitus complet.
    ignorees: int = 0
    #: Calculs dont la chaine depasse la borne de termes : ni verifies, ni accuses.
    #: Evaluer une PARTIE des termes et la comparer au total inventerait un refus.
    non_evaluees: int = 0

    @property
    def bloquantes(self) -> tuple[Verification, ...]:
        return tuple(v for v in self.verifications if not v.ok and v.bloquant)

    @property
    def conforme(self) -> bool:
        return not self.bloquantes

    def resume(self) -> str:
        manques = ""
        if self.ignorees:
            manques += f" · {self.ignorees} NON verifiee(s) (limite de volume)"
        if self.non_evaluees:
            manques += f" · {self.non_evaluees} calcul(s) trop long(s) pour etre evalue(s)"
        return (
            f"{self.verifiees} affirmation(s) verifiee(s) · "
            f"{self.refutees} refutee(s) dont {len(self.bloquantes)} bloquante(s) · "
            f"{self.signalees} signalee(s) non concluante(s)"
        ) + manques


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
    affirmations, ignorees, non_evaluees = _extraction_detail(texte)
    for affirmation in affirmations:
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
    # Ce qui n'a PAS ete verifie voyage avec le rapport : un plafond silencieux
    # transformerait une verification partielle en quitus.
    rapport.ignorees = ignorees
    rapport.non_evaluees = non_evaluees
    return rapport


#: Nombre maximal d'affirmations verifiees dans UN document.
#:
#: Ce n'est pas une precaution theorique : un contenu est NON FIABLE par defaut, et
#: une ligne contenant 20 000 calculs faisait durer la verification 114 secondes
#: (mesure). Un document hostile — ou simplement une table de chiffres generee —
#: immobilisait donc l'outil. Au-dela de cette limite, le reste est declare NON
#: VERIFIE : tronquer en silence serait la faute que ce projet refuse.
MAX_AFFIRMATIONS = 200

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
