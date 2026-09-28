"""Les exemples de sortie des documents sont-ils encore la sortie REELLE des outils ?

LE DEFAUT, observe ici meme. Le README montrait `jio artifacts --budget` avec « 11 fichier(s),
~5715 jetons » et des fichiers de contexte a 136/133/134 lignes. L'outil en disait 12, 6424, et
150/145/148. Le depot avait **neuf controles verts**, un test qui compte ses propres chiffres, et
un autre qui verifie que les commandes citees existent : aucun de ces mecanismes ne regardait
cette page. Une sortie d'outil recopiee dans un document est une AFFIRMATION — et c'etait la
seule classe d'affirmation du depot que rien ne relisait.

Le fait qu'elle soit longue, datee et pleine de chiffres n'est pas une raison de l'exempter :
c'est la raison pour laquelle elle pourrit. Personne ne relit une capture d'ecran.

COMMENT ON LA RELIT, sans transformer chaque bloc en test fragile
---------------------------------------------------------------
L'auteur DECLARE ce qu'un bloc promet, en nommant la commande qui doit le produire :

    <!-- sortie: jio artifacts --budget -->
    ... quelques lignes de la sortie ...
    <!-- /sortie -->

Deux contrats, et un seul est repare automatiquement :

  * `sortie:` — les lignes montrees forment un EXTRAIT fidele de la sortie reelle, et les
    coupures sont DECLAREES par une ligne `...`. Un README montre ce qui compte, pas les 45
    lignes de l'outil, mais il doit dire ce qu'il saute : chaque morceau contigu est cherche
    dans la sortie, dans l'ordre, apres la fin du precedent. Un extrait saute en silence
    n'est pas un extrait, c'est une citation arrangee. Ce contrat ne se REPARE pas tout seul
    (choisir les lignes a montrer demanderait de deviner l'intention) — le controle signale,
    comme partout dans ce depot quand la reparation exigerait d'inventer ;
  * `sortie-exacte:` — le bloc est la sortie COMPLETE. Celui-la se repare : `--appliquer`
    reecrit le bloc avec la sortie du jour, apres sauvegarde `.avant-jio`. La reparation ne
    devine rien.

SECURITE : un document est un contenu HOSTILE par defaut
-------------------------------------------------------
Executer une commande lue dans un fichier est exactement le geste qu'un depot hostile attend.
Le garde-fou n'est donc pas un filtre de politesse, c'est une liste blanche, et chaque refus est
un motif ecrit :

  * seul le programme `jio` est execute, dans la forme `jio <sous-commande> ...` ;
  * aucun metacaractere de shell (`; | & < > $ ` \\`) : la commande est passee en LISTE
    d'arguments, sans shell, donc rien de ce qui suit ne peut etre interprete ;
  * aucune option qui ECRIT (`--write`, `--appliquer`, `--fix`, `--sortie`, `--update`) : un
    controle ne modifie jamais ce qu'il controle. Seul `--appliquer`, demande par l'utilisateur,
    ecrit — et il ecrit le document, jamais autre chose ;
  * un DELAI : une commande qui ne rend pas la main est un blocage, pas une mesure ;
  * une commande qui echoue (code != 0) est SIGNALEE, pas silencieusement ignoree : un exemple
    qui montre une sortie que la commande ne produit plus est faux, meme si elle sort en 0.

NORMALISATION : ce qui change sans rien dire
--------------------------------------------
Trois choses rendent une sortie non reproductible entre deux machines, et elles sont masquees
AVANT comparaison, jamais apres : les sequences ANSI (une couleur n'est pas une information quand
la sortie est redirigee), les chemins absolus (remplaces par `<racine>`), et les durees
(`en 1.7s` -> `en <duree>s`). Le reste est compare caractere a caractere : masquer plus serait
s'exempter soi-meme du controle.
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Bloc",
    "Divergence",
    "blocs",
    "commande_refusee",
    "executer",
    "liste",
    "normaliser",
    "reparer",
    "verifier",
]

#: Le balisage. Le nom de la commande tient sur une ligne, sans chevron ni retour a la ligne :
#: un marqueur sur deux lignes serait invisible a la relecture, et ce qui est invisible n'est
#: pas un contrat.
_MOTIF = re.compile(
    r"^(?P<indent>[ \t]*)<!--\s*(?P<type>sortie|sortie-exacte)\s*:\s*(?P<cmd>[^\n<>]+?)\s*-->\n"
    r"(?P<corps>.*?)"
    r"^[ \t]*<!--\s*/(?:sortie|sortie-exacte)\s*-->\s*$",
    re.DOTALL | re.MULTILINE,
)

_METACARACTERES = re.compile(r"[;&|<>$`\\!*?~]")

_ECRITURES = ("--write", "--appliquer", "--fix", "--sortie", "--update", "--propre")

ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
_DUREE = re.compile(r"\b\d+(?:[.,]\d+)?\s*(?:s|sec|ms)\b")


@dataclass(frozen=True)
class Bloc:
    """Un exemple de sortie declare dans un document, avec la commande qui doit le produire."""

    ligne: int
    commande: str
    corps: tuple[str, ...]
    exact: bool


@dataclass(frozen=True)
class Divergence:
    """Ce que le document promet, ce que l'outil rend, et OU cela diverge."""

    ligne: int
    commande: str
    motif: str
    attendu: str
    obtenu: str

    def __str__(self) -> str:
        return (f"ligne {self.ligne} · {self.commande} · {self.motif}\n"
                f"      le document montre : {self.attendu[:120] or '(rien)'}\n"
                f"      l'outil rend        : {self.obtenu[:120] or '(rien)'}")


def blocs(texte: str) -> list[Bloc]:
    """Les blocs declares d'un document, dans l'ordre, avec leur numero de ligne."""
    out: list[Bloc] = []
    for m in _MOTIF.finditer(texte):
        ligne = texte.count("\n", 0, m.start()) + 1
        corps = _corps(m.group("corps"), m.group("indent"))
        out.append(Bloc(ligne=ligne, commande=m.group("cmd").strip(), corps=corps,
                        exact=m.group("type") == "sortie-exacte"))
    return out


def _corps(brut: str, indent: str) -> tuple[str, ...]:
    """Les lignes du bloc, debarrassees de ce qui releve du RENDU et non du contenu.

    Un bloc peut etre ecrit entre accents graves (```` ``` ````) ou indente de quatre espaces :
    c'est de la mise en page Markdown. Ni l'un ni l'autre n'est une affirmation, donc les deux
    sont retires avant comparaison — sans quoi le controle accuserait une mise en forme.
    """
    lignes = brut.split("\n")
    while lignes and not lignes[0].strip():
        lignes.pop(0)
    while lignes and not lignes[-1].strip():
        lignes.pop()
    if lignes and lignes[0].strip().startswith("```") and lignes[-1].strip() == "```":
        lignes = lignes[1:-1]
    prefixe = indent if indent else "    "
    if lignes and all(not l.strip() or l.startswith(prefixe) for l in lignes):
        lignes = [l[len(prefixe):] if l.startswith(prefixe) else l for l in lignes]
    return tuple(l.rstrip() for l in lignes)


def normaliser(texte: str, racine: Path | str | None = None) -> tuple[str, ...]:
    """La sortie ramenee a ce qui doit etre IDENTIQUE partout : sans couleurs, sans chemins
    absolus, sans durees. Ce qui reste est compare caractere a caractere."""
    lignes = [ANSI.sub("", l).rstrip() for l in texte.splitlines()]
    if racine is not None:
        absolue = str(Path(racine).resolve())
        lignes = [l.replace(absolue, "<racine>") for l in lignes]
    lignes = [_DUREE.sub("<duree>", l) for l in lignes]
    while lignes and not lignes[0].strip():
        lignes.pop(0)
    while lignes and not lignes[-1].strip():
        lignes.pop()
    return tuple(lignes)


def commande_refusee(commande: str) -> str | None:
    """Pourquoi cette commande ne sera PAS executee — ou `None` si elle est acceptable.

    Une liste blanche, pas un filtre : on refuse tout ce qui n'est pas exactement une
    sous-commande de `jio`, sans exception et sans « sauf si ».
    """
    try:
        mots = shlex.split(commande)
    except ValueError as exc:                       # guillemet non ferme
        return f"commande illisible ({exc})"
    if not mots or mots[0] != "jio":
        return "seul le programme `jio` est execute depuis un document"
    if len(mots) < 2 or mots[1].startswith("-"):
        return "il faut nommer la sous-commande (`jio <sous-commande> ...`)"
    if _METACARACTERES.search(commande):
        return "metacaractere de shell refuse : la commande est passee en arguments, pas au shell"
    for option in mots:
        if option.split("=")[0] in _ECRITURES:
            return f"option qui ECRIT refusee dans un controle : {option}"
    return None


def executer(commande: str, racine: Path | str, delai: int = 120) -> tuple[int, tuple[str, ...]]:
    """Lance la commande depuis la racine du depot et rend `(code, sortie normalisee)`.

    `subprocess` recoit une LISTE d'arguments : le shell n'intervient jamais, donc rien de ce
    qui figure dans le document ne peut etre interprete. C'est le meme choix que partout dans
    ce depot, et il compte davantage ici : la source est un fichier, pas une decision.
    """
    refus = commande_refusee(commande)
    if refus:
        raise ValueError(refus)
    # `shlex` et non `str.split` : la commande d'un document s'ecrit comme dans un terminal, donc
    # les guillemets qui protegent un objectif (`jio skills "Ajouter un test ..."`) doivent etre
    # retires. Les metacaracteres ont deja ete refuses plus haut : rien de ce qui reste ici ne
    # peut etre interprete, puisqu'il n'y a pas de shell.
    resultat = subprocess.run(
        [sys.executable, "-m", *shlex.split(commande)],
        cwd=str(racine), capture_output=True, text=True, timeout=delai, check=False,
    )
    melange = resultat.stdout + ("\n" + resultat.stderr if resultat.stderr.strip() else "")
    return resultat.returncode, normaliser(melange, racine)


#: Une ligne de coupure DÉCLARÉE. Trois ecritures, parce que trois sont naturelles : `...`,
#: `[...]` et les points de suspension typographiques `[…]`.
_COUPURE = re.compile(r"^\s*(?:\.\.\.|\[\s*(?:\.\.\.|…)\s*\]|…)\s*$")


def _bords(lignes: list[str]) -> tuple[str, ...]:
    """Retire les lignes vides de tete et de queue : la mise en page d'un bloc n'est pas
    une affirmation, et la comparer produirait des divergences de forme."""
    out = list(lignes)
    while out and not out[0].strip():
        out.pop(0)
    while out and not out[-1].strip():
        out.pop()
    return tuple(out)


def _segments(corps: tuple[str, ...]) -> list[tuple[str, ...]]:
    """Decoupe le corps en morceaux contigus, sur les lignes de coupure declarees."""
    segments: list[tuple[str, ...]] = []
    courant: list[str] = []
    for ligne in corps:
        if _COUPURE.match(ligne):
            if courant:
                segments.append(_bords(courant))
            courant = []
            continue
        # Les lignes VIDES a l'interieur d'un morceau en font partie : la sortie reelle en
        # contient, et un extrait qui les supprimerait ne serait plus contigu — le controle
        # accuserait alors une mise en page, exactement ce qu'il ne doit pas faire.
        courant.append(ligne)
    if courant:
        segments.append(_bords(courant))
    return [s for s in segments if s]


def _extrait(corps: tuple[str, ...], sortie: tuple[str, ...]) -> tuple[int, str] | None:
    """Chaque morceau contigu est-il dans la sortie, dans l'ordre ? Rend la rupture eventuelle.

    La recherche reprend APRES la fin du morceau precedent : un extrait qui remettrait les
    sections dans un autre ordre que la sortie reelle ne serait pas un extrait.
    """
    segments = _segments(corps)
    if not segments:
        return (0, "(le bloc est vide)")
    depart = 0
    for segment in segments:
        if len(segment) > len(sortie):
            return (min(depart, max(0, len(sortie) - 1)), segment[0])
        trouve = None
        for debut in range(depart, len(sortie) - len(segment) + 1):
            if all(segment[i].strip() == sortie[debut + i].strip() for i in range(len(segment))):
                trouve = debut
                break
        if trouve is None:
            index = min(depart, max(0, len(sortie) - 1))
            return (index, segment[0])
        depart = trouve + len(segment)
    return None


def verifier(texte: str, racine: Path | str, delai: int = 120) -> list[Divergence]:
    """Confronte chaque bloc declare a la sortie reelle de sa commande."""
    racine = Path(racine)
    divergences: list[Divergence] = []
    for bloc in blocs(texte):
        refus = commande_refusee(bloc.commande)
        if refus:
            divergences.append(Divergence(bloc.ligne, bloc.commande, f"REFUS : {refus}", "", ""))
            continue
        try:
            code, sortie = executer(bloc.commande, racine, delai)
        except subprocess.TimeoutExpired:
            divergences.append(Divergence(bloc.ligne, bloc.commande,
                                          f"la commande n'a pas rendu la main en {delai}s",
                                          "", ""))
            continue
        if code != 0 and not sortie:
            divergences.append(Divergence(
                bloc.ligne, bloc.commande, f"la commande sort en {code} sans rien dire",
                bloc.corps[0] if bloc.corps else "", ""))
            continue
        if bloc.exact:
            if tuple(l.strip() for l in bloc.corps) != tuple(l.strip() for l in sortie):
                index = 0
                while (index < len(bloc.corps) and index < len(sortie)
                       and bloc.corps[index].strip() == sortie[index].strip()):
                    index += 1
                divergences.append(Divergence(
                    bloc.ligne, bloc.commande,
                    f"sortie EXACTE divergente a la ligne {index + 1} "
                    f"({len(bloc.corps)} ligne(s) montree(s), {len(sortie)} rendue(s))",
                    bloc.corps[index] if index < len(bloc.corps) else "(rien de plus)",
                    sortie[index] if index < len(sortie) else "(rien de plus)",
                ))
            continue
        rupture = _extrait(bloc.corps, sortie)
        if rupture is not None:
            index, ligne = rupture
            obtenu = sortie[index] if index < len(sortie) else "(rien)"
            divergences.append(Divergence(
                bloc.ligne, bloc.commande,
                "l'extrait ne se retrouve pas dans la sortie reelle", ligne, obtenu))
    return divergences


def liste(texte: str) -> list[str]:
    """Ce que le document promet, en une ligne par bloc — de quoi verifier sans executer."""
    return [f"ligne {b.ligne:>5}  {'EXACTE ' if b.exact else 'extrait'}  "
            f"{len(b.corps):>3} ligne(s)  {b.commande}" for b in blocs(texte)]


def reparer(chemin: Path | str, racine: Path | str,
            delai: int = 120) -> tuple[int, list[str], str]:
    """Reecrit les blocs `sortie-exacte` perimes. Rend `(code, signalements, message)`.

    Les extraits perimes ne sont PAS reecrits : choisir les lignes a montrer demanderait de
    deviner l'intention de l'auteur, et ce depot ne devine pas — il signale. La sauvegarde
    `.avant-jio` suit la meme regle que la generation du corps de la PR : une ecriture doit
    pouvoir etre annulee, et ce qui n'a pas change n'est pas reecrit.
    """
    chemin = Path(chemin)
    racine = Path(racine)
    texte = chemin.read_text(encoding="utf-8")
    signalements: list[str] = []
    corriges = 0
    for bloc in blocs(texte):
        refus = commande_refusee(bloc.commande)
        if refus or not bloc.exact:
            if refus:
                signalements.append(f"ligne {bloc.ligne} : REFUS — {refus}")
            continue
        code, sortie = executer(bloc.commande, racine, delai)
        if tuple(l.strip() for l in bloc.corps) == tuple(l.strip() for l in sortie):
            continue
        if code != 0:
            signalements.append(
                f"ligne {bloc.ligne} : la commande sort en {code}, le bloc n'est PAS reecrit "
                f"(reecrire une sortie d'erreur la presenterait comme un resultat)")
            continue
        ancien = "\n".join(bloc.corps)
        if ancien:
            avant = texte
            textes = "\n".join(bloc.corps)
            texte = texte.replace(f"{textes}\n", "\n".join(sortie) + "\n", 1)
            # la comparaison de longueur est faite plus bas sur le texte entier : un
            # remplacement qui n'a rien change serait un faux « corrige »
            corriges += 1 if texte != avant else 0
        else:
            signalements.append(f"ligne {bloc.ligne} : bloc vide, rien a comparer")

    if corriges:
        sauvegarde = chemin.with_name(chemin.name + ".avant-jio")
        shutil.copyfile(chemin, sauvegarde)
        chemin.write_text(texte, encoding="utf-8")
        message = (f"{corriges} bloc(s) reecrit(s) dans {chemin.name} · sauvegarde : "
                   f"{sauvegarde.name}")
    else:
        message = f"aucun bloc a reecrire dans {chemin.name}"
    restants = verifier(chemin.read_text(encoding="utf-8"), racine, delai)
    for divergence in restants:
        signalements.append(str(divergence))
    return (0 if not restants else 1), signalements, message
