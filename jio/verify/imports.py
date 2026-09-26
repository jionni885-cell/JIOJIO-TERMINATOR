"""Coherence des imports internes d'un projet — l'erreur la plus banale et la plus coûteuse.

Pourquoi cette verification existe
----------------------------------
Renommer une fonction publique, deplacer un module, supprimer un symbole : c'est
la cause numero un des ruptures silencieuses. Le fichier modifie reste
parfaitement valide ; c'est le fichier *consommateur* qui casse, a l'execution,
parfois longtemps apres.

Constate sur un vrai projet : apres renommage d'une fonction de `filesize.py`,
l'outil ne detectait rien — l'erreur n'apparaissait que chez le consommateur, et
sous forme d'ImportError donc classee « environnement ».

Principe
--------
Aucun LLM, aucune execution : on lit les imports de chaque fichier du projet et
on verifie que les noms importes EXISTENT dans le fichier cible, lu lui aussi.
C'est deterministe, instantane, et ca attrape exactement la classe de bug
« renomme sans mettre a jour les appelants ».

Regle de prudence
-----------------
On ne verifie QUE les imports resolvables a l'interieur du projet analyse. Un
import externe, un import dynamique, un `import *` ou une resolution ambigue sont
IGNORES : mieux vaut ne rien dire que produire une fausse alerte. Un outil qui
crie au loup est desactive au bout de deux jours.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

__all__ = ["ImportProblem", "ModuleInfo", "analyse", "check_project"]


@dataclass(frozen=True)
class ImportProblem:
    path: Path
    line: int
    message: str


@dataclass
class ModuleInfo:
    """Ce qu'un fichier du projet declare et importe."""

    path: Path
    dotted: str                       # nom module plausible ("pkg.mod" vu depuis la racine)
    package: str                      # paquet contenant le fichier
    defines: set[str]                 # noms de premier niveau declares
    imports: list[tuple[str, tuple[str, ...], int]]  # (module, noms, ligne)
    relative: list[tuple[int, str, tuple[str, ...]]]  # (niveau, module, noms)
    attributes: list[tuple[str, int]] = field(default_factory=list)  # ("pkg.a.helper", ligne)
    parses: bool = True
    error: str = ""
    #: Le module contient un `from X import *`. Ses noms exportables ne sont donc PAS
    #: tous visibles dans son code : une partie vient d'ailleurs, et l'analyse statique
    #: ne peut pas les suivre. Accuser un consommateur parce que le nom est introuvable
    #: dans un module qui importe tout serait accuser l'analyseur, pas le code.
    etoile: bool = False


def _toplevel_names(tree: ast.Module) -> set[str]:
    """Noms exportables declares par le module.

    Les declarations COMPTEES sont celles du niveau module ET celles des blocs qui
    s'executent au chargement (`if`, `try`, `with`, boucles). La version precedente ne
    regardait que `tree.body` : tout nom defini sous une condition etait invisible, et
    le verificateur d'imports accusait alors des modules parfaitement corrects.

    Mesure sur des bibliotheques reelles publiees : `from .recipes import batched`
    (more-itertools, `batched` defini sous `if sys.version_info >= (3, 12)`),
    `from ._termui_impl import getchar` (click, defini sous `if WIN`),
    `from ._compat import _get_argv_encoding` (click, defini sous `if WIN`) — trois
    fausses accusations, toutes de la meme cause.

    On ne descend PAS dans le corps des fonctions et des classes : un nom defini la
    n'est pas exportable, et le compter rendrait le controle muet.
    """
    out: set[str] = set()

    def parcours(corps: list[ast.stmt]) -> None:
        for node in corps:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                out.add(node.name)
                if isinstance(node, ast.ClassDef):
                    # Une classe declare ses METHODES : `from .m import MaClasse` puis
                    # `MaClasse.methode` doit resoudre.
                    out.update(
                        child.name
                        for child in node.body
                        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    )
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        out.add(target.id)
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                out.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    out.add(alias.asname or alias.name.split(".")[0])
            elif isinstance(node, ast.Try):
                parcours(node.body)
                for handler in node.handlers:
                    parcours(handler.body)
                parcours(node.orelse)
                parcours(node.finalbody)
            elif isinstance(node, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.With,
                                   ast.AsyncWith)):
                parcours(node.body)
                # `node.orelse` est vide pour With ; l'attribut existe pour les autres.
                parcours(getattr(node, "orelse", []))

    parcours(tree.body)
    return out


def analyse(path: Path, root: Path) -> ModuleInfo:
    """Lit un fichier et decrit ce qu'il declare et importe."""
    rel = path.relative_to(root) if path.is_relative_to(root) else Path(path.name)
    parts = list(rel.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    dotted = ".".join(parts)
    # Le paquet est le DOSSIER du fichier, sans exception. Deduire le paquet de
    # `parts[:-1]` donnait, pour un `__init__.py`, le paquet PARENT : `from .cli
    # import X` etait alors resolu vers `jio/cli.py` au lieu de
    # `jio/providers/cli.py`, et accusait un symbole inexistant. Constate par
    # auto-audit, pas en theorie.
    package = ".".join(rel.parent.parts) if rel.parent.parts else ""

    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError as exc:
        return ModuleInfo(path, dotted, package, set(), [], [], parses=False,
                          error=f"{exc.msg} (ligne {exc.lineno})")

    imports: list[tuple[str, tuple[str, ...], int]] = []
    relative: list[tuple[int, str, tuple[str, ...]]] = []
    bound: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                bound.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            names = tuple(a.name for a in node.names)
            for alias in node.names:
                bound.add(alias.asname or alias.name)
            if node.level:  # import relatif
                relative.append((node.level, node.module or "", names))
            elif node.module:
                imports.append((node.module, names, node.lineno))

    # Usages par attribut (`pkg.a.helper()`, `a.helper()` apres `from pkg import a`).
    # Sans cela, TOUT appel de fonction importee etait invisible : seul le nom
    # importe etait verifie, jamais ce qu'on en utilise. Un renommage d'attribut
    # passait donc sans bruit.
    # Un nom peut etre lie par un import ET reutilise comme variable locale : dans
    # `def __init__(self, box: str)`, `box` est un PARAMETRE. Le prendre pour un
    # module faisait accuser `box.splitlines()` et `box.ascii` (rich/box.py) alors que
    # `box` est une chaine de caracteres. On ne suit donc un attribut que si sa racine
    # est liee par un import ET jamais masquee ailleurs dans le fichier.
    shadows: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            args = node.args if not isinstance(node, ast.Lambda) else node.args
            for arg in list(getattr(args, "posonlyargs", [])) + list(args.args) + list(
                args.kwonlyargs
            ):
                shadows.add(arg.arg)
            if args.vararg:
                shadows.add(args.vararg.arg)
            if args.kwarg:
                shadows.add(args.kwarg.arg)
        elif isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            shadows.add(node.id)
        elif isinstance(node, ast.alias):
            pass
    attributes: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            try:
                raw = ast.unparse(node)
            except Exception:  # arbre partiel : on ne devine pas
                continue
            racine = raw.split(".")[0]
            if racine in bound and racine not in shadows:
                attributes.append((raw, node.lineno))
    # Import etoile, cherche PARTOUT : un `from .core import *` ecrit dans un `try` ou
    # un `if` fournit tout autant de noms au module. Le doute profite a l'artefact.
    etoile = any(
        isinstance(node, ast.ImportFrom) and any(a.name == "*" for a in node.names)
        for node in ast.walk(tree)
    )
    return ModuleInfo(
        path, dotted, package, _toplevel_names(tree), imports, relative, attributes,
        etoile=etoile,
    )


def _index(infos: list[ModuleInfo]) -> dict[str, ModuleInfo]:
    """Table nom module -> fichier, indexee aussi par SUFFIXES.

    Pourquoi les suffixes : le nom sous lequel un module est importe depend de la
    racine depuis laquelle le projet est importe, et l'utilisateur pointe l'outil
    ou il veut. Scanner `monprojet/` ou `monprojet/pkg/` doit donner le meme
    verdict. Constate sur un vrai projet : le meme renommage etait detecte depuis
    la racine du depot, et invisible depuis le dossier du paquet.
    """
    table: dict[str, ModuleInfo] = {}
    for info in infos:
        if not info.dotted:
            continue
        table.setdefault(info.dotted, info)
    return table


def _espaces_d_import(path: Path, root: Path) -> frozenset[str]:
    """Prefixes sous lesquels les paquets ANCETRES de ce fichier s'importent.

    Un fichier ne sait pas depuis quelle racine on l'audite : `src/humanize/__init__.py`
    s'importe `humanize` pour Python, que l'on scanne le depot ou `src/humanize/`. Ces noms
    se lisent sur le DISQUE — tout dossier ancetre portant un `__init__.py` est un paquet,
    et il s'importe par son nom de dossier ; on ajoute la forme derivee de la racine de
    scan (`src.humanize`), celle que l'outil utilise dans sa propre table. Mesure : le meme
    renommage etait vu depuis la racine du depot et invisible depuis le dossier du paquet.

    Le nom du dossier racine est ajoute : auditer `site-packages/tqdm` doit permettre
    `from tqdm.utils import ...` meme si `__init__.py` manque la ou l'on regarde.
    """
    noms = {Path(root).name}
    cible, borne = Path(path).resolve(), Path(root).resolve()
    for parent in cible.parents:
        if not (parent / "__init__.py").is_file():
            if parent == borne:
                break
            continue
        noms.add(parent.name)
        derive = ".".join(parent.relative_to(borne).parts) if parent != borne else ""
        if derive:
            noms.add(derive)
        if parent == borne:
            break
    return frozenset(noms)


def _resolve(
    module: str,
    table: dict[str, ModuleInfo],
    *,
    absolu: bool = False,
    racine: str = "",
    espaces: frozenset[str] | None = None,
) -> ModuleInfo | None:
    """Resout un module par son nom, puis par ses suffixes — seulement si non ambigu.

    On prefere ne rien dire que de designer le mauvais fichier : si deux modules
    partagent le meme suffixe (`a.utils` et `b.utils`), la resolution est
    abandonnee. Un outil qui accuse le mauvais fichier est pire qu'un outil muet.

    `absolu=True` pour un import ECRIT EN ABSOLU (`from requests.utils import ...`). La
    resolution par suffixe n'est alors acceptee QUE si les segments abandonnes forment
    EXACTEMENT le nom d'un paquet ancetre du fichier (`espaces`, voir `_espaces_d_import`) :
    le code parle alors de son propre paquet, et le reste du nom se resout chez lui.

    Sans cette condition, `tqdm/contrib/discord.py` faisait resoudre `requests.utils` vers
    le `tqdm/utils.py` voisin : l'audit accusait une bibliotheque correcte d'un nom
    inexistant. Mesure faite sur du code public, et le meme mecanisme accusait
    `keras.callbacks` dans `tqdm/keras.py`.

    Le prix est un faux NEGATIF : un import absolu du paquet lui-meme, ecrit depuis un
    dossier racine qui ne porte pas son nom, n'est plus verifie. C'est le bon sens du
    compromis — un faux negatif se declare, un faux positif detruit la confiance.

    Le nom construit depuis le paquet du fichier (`from .utils import ...`) n'est pas
    concerne : la, le suffixe vient du paquet lui-meme, et le module a un segment est
    la bonne cible.
    """
    if module in table:
        return table[module]
    parts = module.split(".")
    autorises = espaces if espaces is not None else frozenset({racine})
    for i in range(1, len(parts)):
        suffix = parts[i:]
        # Pour un nom ABSOLU, les segments abandonnes doivent former le nom d'un paquet
        # ancetre du fichier : sinon l'import designe un paquet EXTERIEUR, et resoudre son
        # reste chez nous accusait une bibliotheque correcte.
        #
        # Le compte des segments compte : `tqdm/contrib/discord.py` importe
        # `requests.utils` ; abandonner `tqdm`, puis `tqdm.contrib`, menait a abandonner
        # aussi `requests` et a tomber sur n'importe quel `...utils` du projet.
        if absolu and ".".join(parts[:i]) not in autorises:
            continue
        matches = {
            info.path: info
            for info in table.values()
            if len(info.dotted.split(".")) >= len(suffix)
            and info.dotted.split(".")[-len(suffix):] == suffix
        }
        if len(matches) == 1:
            return next(iter(matches.values()))
        if len(matches) > 1:
            return None  # ambigu : on ne dit rien
    return None


#: Modules de la bibliotheque standard (Python 3.10+). Sur une version plus
#: ancienne, l'ensemble est vide : on retombe alors sur le comportement precedent.
_STDLIB = frozenset(getattr(sys, "stdlib_module_names", ()))


def _est_stdlib(module: str) -> bool:
    """Le module est-il celui de la bibliotheque standard (et non un homonyme local)?"""
    return bool(_STDLIB) and module.split(".")[0] in _STDLIB


def check_project(paths: list[Path], root: Path) -> list[ImportProblem]:
    """Verifie que chaque nom importe existe bien dans le module cible du projet."""
    infos = [analyse(p, root) for p in paths]
    table = _index(infos)
    problems: list[ImportProblem] = []
    # Prefixes qu'un fichier peut abandonner dans un import absolu : les noms des paquets
    # ancetres, lus sur le disque (voir `_espaces_d_import`). C'est le SEUL ensemble
    # accepte (voir `_resolve`).
    espaces_vus: dict[Path, frozenset[str]] = {}

    def _prefixes(info: ModuleInfo) -> frozenset[str]:
        cle = Path(info.path)
        if cle not in espaces_vus:
            espaces_vus[cle] = _espaces_d_import(cle, root)
        return espaces_vus[cle]

    for info in infos:
        if not info.parses:
            continue

        # imports absolus resolvables dans le projet
        for module, names, line in info.imports:
            if _est_stdlib(module):
                # `from types import ModuleType` designe la bibliotheque standard.
                # Or un paquet qui contient son PROPRE `types.py` (click en est un)
                # faisait resoudre l'import vers ce fichier local, qui ne declare pas
                # `ModuleType` : le projet etait accuse a tort, six fois. Un nom de la
                # stdlib ne se cherche jamais dans le projet : on se tait plutot que
                # d'accuser, et rater une ombre de la stdlib est le prix acceptable.
                continue
            noms_du_fichier = _prefixes(info)
            target = _resolve(module, table, absolu=True, espaces=noms_du_fichier)
            if target is None and info.package:
                # un projet peut s'importer depuis sa propre racine
                target = _resolve(
                    f"{info.package}.{module}", table, absolu=True, espaces=noms_du_fichier
                )
            if target is None or not target.parses:
                continue  # import externe ou non resolu : on ne dit rien
            for name in names:
                if name == "*" or name in target.defines:
                    continue
                if target.etoile:
                    # `from .helpers import X` ou helpers fait `from .core import *` :
                    # X existe a l'execution mais reste invisible ici. Mesure sur du code
                    # public : pyparsing accusait `DelimitedList` et `ParseException`, deux
                    # symboles bien presents (verifie a l'import). Le nom peut venir de
                    # l'etoile : on ne peut pas conclure, donc on n'accuse pas.
                    continue
                # `from pkg import a` ou `a` est le SOUS-MODULE pkg/a.py : forme
                # parfaitement valide en Python, et courante dans le code reel.
                # L'ignorer produisait une fausse alerte sur chaque projet.
                if _resolve(
                    f"{module}.{name}", table, absolu=True, espaces=noms_du_fichier
                ) is not None:
                    continue
                if _resolve(f"{target.dotted}.{name}", table) is not None:
                    continue
                problems.append(
                    ImportProblem(
                        info.path, line,
                        f"`{name}` est importe de `{module}` mais n'y existe pas "
                        f"({target.path.name} ne declare pas ce nom, et aucun "
                        f"sous-module ne porte ce nom)",
                    )
                )

        # imports relatifs
        for level, module, names in info.relative:
            base = info.package.split(".") if info.package else []
            # level=1 -> paquet courant ; level=2 -> parent ; etc.
            keep = len(base) - (level - 1)
            if keep < 0:
                continue
            prefix = ".".join(base[:keep])
            wanted = f"{prefix}.{module}" if module else prefix
            target = _resolve(wanted, table) if wanted else None
            if target is None and module:
                target = _resolve(module, table)
            if target is None or not target.parses:
                continue
            if not module:
                continue  # `from . import X` : X peut etre un sous-module, ambigu
            for name in names:
                if name == "*" or name in target.defines:
                    continue
                if target.etoile:
                    continue  # voir le commentaire des imports absolus
                if _resolve(f"{wanted}.{name}", table) is not None:
                    continue
                problems.append(
                    ImportProblem(
                        info.path, 0,
                        f"`{name}` est importe de `{module}` (relatif) mais n'y existe pas",
                    )
                )

        # Usages par attribut : `a.helper()` avec `a` importe du projet.
        for chain, line in info.attributes:
            problem = _check_attribute(info, chain, table)
            if problem is not None:
                problems.append(ImportProblem(info.path, line, problem))

    return problems


def _check_attribute(info: ModuleInfo, chain: str, table: dict[str, ModuleInfo]) -> str | None:
    """Verifie qu'un attribut utilise existe bien dans le module d'origine.

    On cherche le plus long prefixe qui designe un module DU PROJET ; si aucun
    prefixe n'en designe un, l'expression est externe (ou indeterminable) et on se
    tait. Chaque segment restant doit alors etre declare, ou etre lui-meme un
    sous-module. Sinon : le code appelle quelque chose qui n'existe pas.
    """
    parts = chain.split(".")
    for cut in range(len(parts) - 1, 0, -1):
        module = ".".join(parts[:cut])
        if cut == 1 and _est_stdlib(module):
            # `logging.NOTSET` / `types.ModuleType` : la cible est la bibliotheque
            # standard, meme si le projet contient un homonyme (`rich/logging.py`,
            # `click/types.py`). Chercher dans l'homonyme local accusait des appels
            # parfaitement valides — mesure sur cinq paquets publies.
            return None
        target = _resolve(module, table)
        if target is None and info.package:
            target = _resolve(f"{info.package}.{module}", table)
        if target is None or not target.parses:
            continue
        if target.path == info.path:
            # Le nom se resout sur le FICHIER LUI-MEME : c'est un homonyme, pas une
            # reference. Mesure sur du code public : `tqdm/keras.py` contient
            # `import keras` (le vrai paquet Keras, externe) puis
            # `keras.callbacks.Callback` — resolu vers `tqdm/keras.py`, d'ou deux
            # accusations fausses. Un fichier ne s'importe pas lui-meme sous son nom
            # absolu : dans ce cas le nom designe forcement autre chose.
            continue
        current = target
        for segment in parts[cut:]:
            if segment in current.defines:
                return None
            if current.etoile:
                # Le nom peut venir d'un `from X import *` : invisible ici, mais bien
                # present a l'execution. On ne peut pas conclure — donc on n'accuse pas.
                return None
            deeper = _resolve(f"{current.dotted}.{segment}", table)
            if deeper is not None and deeper.parses:
                current = deeper
                continue
            return (
                f"`{chain}` : `{segment}` n'existe pas dans "
                f"`{current.dotted}` ({current.path.name})"
            )
        return None
    return None
