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


def _toplevel_names(tree: ast.Module) -> set[str]:
    """Noms exportables declares au premier niveau."""
    out: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            out.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    out.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            out.add(node.target.id)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                out.add(alias.asname or alias.name.split(".")[0])
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
    attributes: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            try:
                raw = ast.unparse(node)
            except Exception:  # arbre partiel : on ne devine pas
                continue
            if raw.split(".")[0] in bound:
                attributes.append((raw, node.lineno))
    return ModuleInfo(
        path, dotted, package, _toplevel_names(tree), imports, relative, attributes
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


def _resolve(module: str, table: dict[str, ModuleInfo]) -> ModuleInfo | None:
    """Resout un module par son nom, puis par ses suffixes — seulement si non ambigu.

    On prefere ne rien dire que de designer le mauvais fichier : si deux modules
    partagent le meme suffixe (`a.utils` et `b.utils`), la resolution est
    abandonnee. Un outil qui accuse le mauvais fichier est pire qu'un outil muet.
    """
    if module in table:
        return table[module]
    parts = module.split(".")
    for i in range(1, len(parts)):
        suffix = parts[i:]
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


def check_project(paths: list[Path], root: Path) -> list[ImportProblem]:
    """Verifie que chaque nom importe existe bien dans le module cible du projet."""
    infos = [analyse(p, root) for p in paths]
    table = _index(infos)
    problems: list[ImportProblem] = []

    for info in infos:
        if not info.parses:
            continue

        # imports absolus resolvables dans le projet
        for module, names, line in info.imports:
            target = _resolve(module, table)
            if target is None and info.package:
                # un projet peut s'importer depuis sa propre racine
                target = _resolve(f"{info.package}.{module}", table)
            if target is None or not target.parses:
                continue  # import externe ou non resolu : on ne dit rien
            for name in names:
                if name == "*" or name in target.defines:
                    continue
                # `from pkg import a` ou `a` est le SOUS-MODULE pkg/a.py : forme
                # parfaitement valide en Python, et courante dans le code reel.
                # L'ignorer produisait une fausse alerte sur chaque projet.
                if _resolve(f"{module}.{name}", table) is not None:
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
        target = _resolve(module, table)
        if target is None and info.package:
            target = _resolve(f"{info.package}.{module}", table)
        if target is None or not target.parses:
            continue
        current = target
        for segment in parts[cut:]:
            if segment in current.defines:
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
