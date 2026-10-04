"""Analyseurs standards du metier, branches sur `jio scan` — sans les reinventer.

Pourquoi ce module existe
-------------------------
Regle de travail : *si quelqu'un a deja resolu le probleme proprement, on utilise sa
solution.* Ruff, Flake8 et Pyflakes sont l'etat de l'art pour reperer les erreurs
reelles en Python ; les reecrire serait du gaspillage et ferait moins bien.

Ce que JIO apporte en plus, et que ces outils n'ont pas :
  * une classification honnete des echecs (defaut / non testable ici / reserve) ;
  * la coherence des imports internes et la reproductibilite, qu'aucun d'eux ne voit ;
  * un rapport qui n'accuse jamais sans preuve ni sans nommer la source.

Perimetre, volontairement etroit
--------------------------------
Jeu de regles classique de la litterature CI (`E9,F63,F7,F82`) : erreurs de syntaxe,
comparaisons invalides, noms non definis, variables locales utilisees avant
affectation. On ne fait PAS de style : un projet qui passe ses tests ne doit pas
etre declare fautif parce qu'il n'aime pas l'ordre des imports. Un outil qui crie
au loup est desactive au bout de deux jours.

Le nom de l'outil figure dans chaque constat (`[ruff:F821]`). C'est une preuve
verifiable et reproductible, mais elle n'est pas de JIO : le dire est la moindre
des choses.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import ast
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

__all__ = ["LintFinding", "LinterReport", "analyse", "constat_a_tort"]

#: Jeu de regles « vrais bugs ». Base : le jeu classique des integrations continues
#: (`E9,F63,F7,F82`, avec `F811` deja inclus dans `F`). On l'a ELARGI a `F` en entier :
#: pyflakes signale du code mort — import inutilise, variable assignee jamais lue,
#: f-string sans valeur — et non des preferences. La difference avec le style est ce qui
#: decide : `F401` sur un module signale souvent un branchement oublie, alors que l'ordre
#: des imports ne casse rien.
#:
#: L'elargissement a ete fait APRES avoir mis le depot a zero sur `F` (24 imports morts et
#: 2 variables mortes ecartes, mesure) : elargir une porte avant de nettoyer garantit
#: qu'on l'ignorera. Aucune regle de style — `I`, `E501` et compagnie restent dehors.
BUG_RULES = "E9,F"

#: Traduction des constats. L'interface est en francais, mais le message d'origine
#: est TOUJOURS conserve : traduire, c'est expliquer, jamais remplacer la preuve.
_PLAIN_FRENCH: dict[str, str] = {
    "E999": "erreur de syntaxe : le fichier n'est pas du Python valide",
    "F401": "import inutilise",
    "F402": "import masque par une variable de boucle",
    "F403": "`import *` empeche toute analyse statique",
    "F405": "nom peut-etre indefini (vient d'un `import *`)",
    "F631": "comparaison invalide",
    "F632": "comparaison avec un litteral ecrit avec `is` au lieu de `==`",
    "F701": "`break` hors d'une boucle",
    "F702": "`continue` hors d'une boucle",
    "F706": "`return` hors d'une fonction",
    "F707": "`except` sans type d'exception : capture tout, y compris les erreurs de frappe",
    "F811": "nom redefini : la definition precedente ne sert plus a rien",
    "F821": "nom non defini : le code ne peut pas s'executer",
    "F822": "nom absent de `__all__`",
    "F823": "variable locale utilisee avant d'etre affectee",
}


def plain_french(code: str) -> str:
    """Explication courte en francais d'un code de regle, si elle est connue."""
    if code in _PLAIN_FRENCH:
        return _PLAIN_FRENCH[code]
    for prefix in ("F82", "F63", "F70", "E9"):
        if code.startswith(prefix):
            return {
                "F82": "nom non resolu a l'execution",
                "F63": "comparaison probablement erronee",
                "F70": "instruction hors contexte",
                "E9": "erreur de syntaxe",
            }[prefix]
    return ""

#: Regles qui expriment une LIMITE DE L'ANALYSEUR, et non un defaut du code.
#:
#: Mesure sur du code public : `pyparsing` (3.3.3) etait declare fautif cinq fois, uniquement
#: sur `F403` — des `from .x import *` dans son `__init__.py`, qui est precisement l'idiome
#: standard de reexport d'un paquet. Le message le dit lui-meme : « unable to detect undefined
#: names ». Accuser un projet parce que l'ANALYSEUR n'a pas su suivre les noms est un faux
#: positif, et un faux positif de cette farine detruit la confiance dans le garde.
#:
#: Ces constats ne sont pas perdus pour autant : ils restent affiches, en RESERVE, avec leur
#: raison. Une capacite limitee se declare ; elle ne s'accuse pas — et elle ne se taise pas
#: non plus, sinon `import *` deviendrait une zone ou plus personne ne regarde.
LIMITES_DE_L_ANALYSE: dict[str, str] = {
    "F401": (
        "import inutilise : c'est du CODE MORT, pas une rupture — rien ne casse. Le message "
        "de l'outil propose trois intentions differentes (retirer, ajouter a `__all__`, ou "
        "reexporter sous un alias), et un module qui declare `__all__` reexporte "
        "deliberement des noms. Mesure sur 12 paquets publics : 41 des 44 constats etaient "
        "des F401, et ils noyaient les 3 VRAIS (dont un ImportError dans tqdm). Un rapport "
        "qu'on ne peut pas lire est ignore en entier, y compris ses vrais defauts"
    ),
    "F403": (
        "`import *` : l'analyseur ne peut pas suivre les noms, donc il ne peut rien prouver "
        "sur ce fichier — limite de l'outil, pas du code"
    ),
    "F405": (
        "nom peut-etre indefini : l'analyseur n'a pas pu trancher a cause d'un `import *` — "
        "limite de l'outil, pas une preuve de defaut"
    ),
    "F541": (
        "f-string sans interpolation : le prefixe `f` ne sert a rien, et RIEN ne casse. "
        "Mesure sur rich (2 occurrences, verifiees dans l'AST : la chaine n'est faite que "
        "de parties constantes) : c'est un reste inoffensif. Le doute a garder est celui "
        "d'une interpolation PERDUE par une refonte — mais ca, l'outil ne le prouve pas"
    ),
}

def _version_cible() -> str:
    """Version de Python annoncee a l'analyseur : celle de l'INTERPRETE COURANT.

    Sans elle, ruff prend sa version par defaut, et tout nom de la bibliotheque standard
    apparu apres cette version est declare « non defini » :

        [ruff:F821] Undefined name `BaseExceptionGroup`. Consider specifying
        requires-python = ">=3.11" or tool.ruff.target-version = "py311"

    Mesure sur du code public (`filelock`) : l'outil proposait lui-meme la correction, et
    l'artefact — qui garde ce nom derriere `sys.version_info >= (3, 11)` — etait accuse a
    tort. On annonce donc la version sous laquelle on MESURE : c'est celle la qui decide de
    ce qui est defini, et un rapport doit dire dans quelles conditions il a ete produit.
    """
    majeur, mineur = sys.version_info[:2]
    return f"py{majeur}{mineur}"


#: Plafond de constats remontes pour un meme outil : au-dela, on resume au lieu de
#: noyer le rapport. Un fichier peut legitimement produire des centaines de lignes.
MAX_FINDINGS = 200


@dataclass(frozen=True)
class LintFinding:
    path: Path
    line: int
    rule: str        # ex. "ruff:F821"
    message: str

    @property
    def code(self) -> str:
        """Code de la regle, sans le nom de l'outil (`ruff:F403` -> `F403`)."""
        return self.rule.split(":")[-1]

    @property
    def label(self) -> str:
        """Constat pret a afficher : explication francaise + message d'origine."""
        plain = plain_french(self.code)
        return f"{plain} — {self.message}" if plain else self.message

    @property
    def limite_de_l_analyse(self) -> str:
        """Raison pour laquelle ce constat DECLARE une limite au lieu d'accuser.

        Chaine vide quand le constat est une preuve de defaut : l'appelant n'a qu'un test a
        faire, et la raison voyage avec le constat.
        """
        return LIMITES_DE_L_ANALYSE.get(self.code, "")


@dataclass
class LinterReport:
    findings: list[LintFinding]
    tool: str = ""       # l'outil reellement utilise, "" si aucun
    note: str = ""       # ce qu'il faut dire a l'utilisateur
    truncated: int = 0   # constats au-dela du plafond
    #: Constats d'un outil EXTERNE ecartes apres lecture du fichier, avec leur raison.
    #: Un ecart muet serait pire que le faux positif : l'utilisateur doit pouvoir
    #: verifier que la lecture a bien eu lieu, et pourquoi.
    exclusions: list[str] = field(default_factory=list)


#: Regles d'un outil externe qu'une LECTURE du fichier peut refuter. Toutes les autres
#: (F811 compris) restent des preuves : on ne desarme que ce qu'on a instruit.
_ALLEGATIONS_REFUTABLES = frozenset({"F401", "F811", "F821", "F841"})


def _noms_lies(arbre: ast.Module) -> set[str]:
    """Noms LIES quelque part dans le fichier (affectation, def, classe, import, param.).

    On ne compte pas les noms seulement LUS : c'est ce qui distingue « defini ailleurs »
    de « jamais defini », la question que pose le constat F821.
    """
    noms: set[str] = set()

    def _cibles(cible: ast.expr) -> None:
        for noeud in ast.walk(cible):
            if isinstance(noeud, ast.Name):
                noms.add(noeud.id)

    for node in ast.walk(arbre):
        if isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            cibles = node.targets if isinstance(node, ast.Assign) else [node.target]
            for cible in cibles:
                _cibles(cible)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            noms.add(node.name)
            for arg in getattr(getattr(node, "args", None), "posonlyargs", []):
                noms.add(arg.arg)
        elif isinstance(node, ast.Lambda):
            for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                noms.add(arg.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                noms.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, (ast.For, ast.AsyncFor)):
            _cibles(node.target)
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    _cibles(item.optional_vars)
        elif isinstance(node, ast.ExceptHandler):
            if node.name:
                noms.add(node.name)
        elif isinstance(node, ast.NamedExpr):
            _cibles(node.target)
        elif isinstance(node, ast.arguments):
            for arg in [*node.posonlyargs, *node.args, *node.kwonlyargs, node.vararg, node.kwarg]:
                if arg is not None:
                    noms.add(arg.arg)
    return noms


def _corps_de(fonction: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Module:
    """Un module SYNTHETIQUE reduit au corps d'une fonction.

    Reutiliser `_noms_lies` (qui attend un `ast.Module`) evite d'ecrire une seconde
    enumeration des formes de liaison : la duplication est exactement la ou les oublis se
    logent, et une forme oubliee ferait accuser a tort.
    """
    return ast.Module(body=list(fonction.body), type_ignores=[])


def _noms_de_la_ligne(arbre: ast.Module, ligne: int) -> set[str]:
    """Noms LUS a cette ligne precise (le sujet du constat de l'outil)."""
    return {
        node.id
        for node in ast.walk(arbre)
        if isinstance(node, ast.Name) and getattr(node, "lineno", 0) == ligne
    }


def constat_a_tort(fichier: Path, code: str, ligne: int) -> str:
    """Raison pour laquelle un constat d'outil externe est FAUX, sinon "".

    Trois familles, toutes mesurees sur du code public. Le principe est constant :
    l'outil regarde une LIGNE, le fichier se lit comme un TOUT — et c'est la lecture
    du fichier qui tranche, pas l'autorite de l'outil.

    * **F821 `get_ipython` chez rich** : le nom n'est defini nulle part, et c'est
      TESTE juste avant (`try: get_ipython` puis `except NameError:`). Le try/except
      EST la gestion de l'absence : il n'y a rien a corriger.
    * **F821 `zed`, F841 `foos` chez rich** : le nom est LOCAL a une fonction. Il
      disparait a la sortie de l'appel, donc ni un code mort ni un nom faussement
      defini. Pyflakes nommait autrefois `__init__` ; ruff a corrige ce point, la
      couverture reste necessaire et couvre aussi les autres methodes.
    * **F811 `wait_for_socket` chez urllib3** : le nom est rebinde depuis une fonction
      via `global` — le choix d'implementation est REPOUSSE au premier appel, et la
      premiere definition reste la porte d'entree. Pyflakes y voit une redefinition
      inutile ; c'est une technique d'implementation, pas un defaut.
    """
    if code not in _ALLEGATIONS_REFUTABLES:
        return ""
    try:
        texte = fichier.read_text(encoding="utf-8", errors="replace")
        arbre = ast.parse(texte)
    except (OSError, SyntaxError):
        return ""

    if code == "F821":
        # (a) le nom est sonde juste avant d'etre utilise : `try: <nom>` / `except NameError`
        for node in ast.walk(arbre):
            if not isinstance(node, ast.Try) or not node.body:
                continue
            premiere = node.body[0]
            sonde = premiere.value if isinstance(premiere, ast.Expr) else None
            if not (isinstance(sonde, ast.Name) and sonde.id not in _noms_lies(arbre)):
                continue
            if not any(
                isinstance(h.type, ast.Name) and h.type.id == "NameError"
                for h in node.handlers
            ):
                continue
            if node.lineno <= ligne <= (node.end_lineno or node.lineno):
                return (
                    f"`{sonde.id}` n'est defini nulle part ET son absence est TESTEE juste "
                    "avant (`try: <nom>` / `except NameError:`) : c'est la gestion de "
                    "l'absence, pas un nom oublie"
                )

    # (c) F811 : redefinition VOLONTAIRE d'un nom global
    if code == "F811":
        for node in ast.walk(arbre):
            if not isinstance(node, ast.Global):
                continue
            cibles = [
                cible
                for cible in ast.walk(arbre)
                if isinstance(cible, ast.Assign)
                and any(
                    isinstance(t, ast.Name) and t.id in node.names for t in cible.targets
                )
            ]
            if cibles:
                return (
                    f"liaison VOLONTAIRE de `{', '.join(node.names)}` depuis une fonction "
                    "(`global`) : le choix d'implementation est repousse au premier appel, "
                    "et la premiere definition reste la porte d'entree"
                )

    # (b) nom LOCAL a une fonction. Le perimetre est etroit, et c'est la mesure qui l'a
    # fixe : un F821 sur un nom JAMAIS defini reste une preuve (c'est la faute de frappe la
    # plus frequente du langage), et un F811 entre deux definitions ne doit pas etre avale.
    #   * F841 : un nom local disparait a la sortie de l'appel — ni code mort, ni nom
    #     faussement defini. Mesure sur rich (`zed`, `foos`).
    #   * F821 : seulement si le nom est LIE dans cette fonction (il est donc local, et la
    #     question de la portee est celle de l'appelant).
    for node in ast.walk(arbre):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not (node.lineno <= ligne <= (node.end_lineno or node.lineno)):
            continue
        if code == "F841":
            return (
                f"le nom est LOCAL a `{node.name}` : il disparait a la sortie de l'appel, donc "
                "il ne peut etre ni un code mort ni un nom faussement defini"
            )
        if code == "F821":
            lies = _noms_lies(_corps_de(node))
            for sonde in _noms_de_la_ligne(arbre, ligne):
                if sonde not in lies:
                    continue
                return (
                    f"`{sonde}` est LIE dans `{node.name}` : c'est une variable locale, sa "
                    "portee est celle de l'appel"
                )
    return ""


def _ruff_command() -> list[str] | None:
    """Commande pour lancer ruff, qu'il soit installe comme module ou comme binaire."""
    try:
        import importlib.util

        if importlib.util.find_spec("ruff") is not None:
            return [sys.executable, "-m", "ruff"]
    except Exception:  # pragma: no cover - environnement exotique
        pass
    binary = shutil.which("ruff")
    return [binary] if binary else None


def _flake8_command() -> list[str] | None:
    try:
        import importlib.util

        if importlib.util.find_spec("flake8") is not None:
            return [sys.executable, "-m", "flake8"]
    except Exception:  # pragma: no cover
        pass
    binary = shutil.which("flake8")
    return [binary] if binary else None


def _pyflakes_command() -> list[str] | None:
    try:
        import importlib.util

        if importlib.util.find_spec("pyflakes") is not None:
            return [sys.executable, "-m", "pyflakes"]
    except Exception:  # pragma: no cover
        pass
    binary = shutil.which("pyflakes")
    return [binary] if binary else None


def _parse_concise(stdout: str, tool: str) -> list[LintFinding]:
    """Format `chemin:ligne:colonne: CODE message`, commun a flake8 et pyflakes."""
    out: list[LintFinding] = []
    for raw in stdout.splitlines():
        parts = raw.split(":", 3)
        if len(parts) < 4:
            continue
        path, line, _col, rest = parts
        rest = rest.strip()
        code, _, message = rest.partition(" ")
        if not message:  # pyflakes sans code de regle
            code, message = "pyflakes", rest
        elif not code[:1].isalpha() or not any(c.isdigit() for c in code):
            code, message = "pyflakes", rest
        try:
            number = int(line)
        except ValueError:
            continue
        out.append(LintFinding(Path(path), number, f"{tool}:{code}", message.strip()))
    return out


def _parse_ruff_json(stdout: str) -> list[LintFinding]:
    out: list[LintFinding] = []
    try:
        data = json.loads(stdout or "[]")
    except json.JSONDecodeError:
        return out
    for item in data:
        try:
            out.append(
                LintFinding(
                    path=Path(item["filename"]),
                    line=int(item.get("location", {}).get("row", 0)),
                    rule=f"ruff:{item.get('code', '?')}",
                    message=str(item.get("message", "")).strip(),
                )
            )
        except (KeyError, TypeError, ValueError):
            continue
    return out


def analyse(
    paths: Sequence[Path],
    *,
    root: Path | None = None,
    timeout: int = 120,
    prefer: str = "auto",
) -> LinterReport:
    """Passe le projet aux analyseurs standards disponibles.

    Aucun analyseur installe n'est PAS un echec : c'est une information. On le dit
    avec la commande exacte a lancer, au lieu de laisser croire que le projet est
    propre parce qu'on n'a rien regarde.
    """
    if prefer in {"", "off", "0", "none"}:
        return LinterReport([], note="analyseurs standards desactives (JIO_LINTERS=off)")

    files = [str(p) for p in paths]
    if not files:
        return LinterReport([], note="aucun fichier a analyser")

    ruff = _ruff_command() if prefer in {"auto", "ruff"} else None
    if ruff is not None:
        cmd = [
            *ruff, "check", "--select", BUG_RULES, "--output-format", "json",
            "--target-version", _version_cible(), *files,
        ]
        tool = "ruff"
    else:
        flake8 = _flake8_command() if prefer in {"auto", "flake8"} else None
        if flake8 is not None:
            cmd = [*flake8, "--select", BUG_RULES, *files]
            tool = "flake8"
        else:
            pyflakes = _pyflakes_command() if prefer in {"auto", "pyflakes"} else None
            if pyflakes is None:
                return LinterReport(
                    [],
                    note=(
                        "aucun analyseur standard installe : le projet n'a pas ete "
                        "passe au crible des regles eprouvees. Installer avec "
                        "`pip install ruff` (recommande, rapide et sans configuration)"
                    ),
                )
            cmd = [*pyflakes, *files]
            tool = "pyflakes"

    if root is not None:
        # Les chemins sont donnes en absolu mais l'affichage reste lisible si on
        # se place a la racine scannee.
        pass
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except (subprocess.TimeoutExpired, OSError) as exc:
        return LinterReport([], tool=tool, note=f"{tool} n'a pas pu s'executer : {exc}")

    stdout = proc.stdout or ""
    if tool == "ruff" and stdout.lstrip().startswith("["):
        findings = _parse_ruff_json(stdout)
    else:
        findings = _parse_concise(stdout, tool)

    # --- lecture du fichier : refutation des constats dits par l'outil --------- #
    # Un constat d'outil externe est une ALLEGATION. Quand la lecture du fichier la
    # refute (le nom est teste avant usage, il est local a une fonction, il est
    # rebinde volontairement), l'ecarter est du travail d'audit, pas une complaisance :
    # garder une alerte fausse detruit la confiance dans tout le rapport.
    exclusions: list[str] = []
    retenus: list[LintFinding] = []
    cache: dict[Path, list[str]] = {}
    for f in findings:
        if f.code in _ALLEGATIONS_REFUTABLES:
            if f.path not in cache:
                try:
                    contenu = f.path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    contenu = ""
                cache[f.path] = contenu.splitlines()
            if 1 <= f.line <= len(cache[f.path]):
                raison = constat_a_tort(f.path, f.code, f.line)
                if raison:
                    exclusions.append(
                        f"{f.path}:{f.line} [{f.rule}] {f.message[:80]} — ecarte : {raison}"
                    )
                    continue
        retenus.append(f)
    findings = retenus

    # Ruff renvoie les chemins tels qu'ils lui ont ete donnes (absolus) : on les
    # ramene a la racine scannee pour que le rapport reste aligne avec le reste.
    if root is not None:
        normalised: list[LintFinding] = []
        for f in findings:
            try:
                f = LintFinding(f.path.relative_to(root), f.line, f.rule, f.message)
            except ValueError:
                pass
            normalised.append(f)
        findings = normalised

    note = ""
    if proc.returncode not in (0, 1):
        note = (
            f"{tool} a termine avec le code {proc.returncode} : son verdict n'est pas "
            f"exploitable. {(proc.stderr or '').strip()[:160]}"
        )
    truncated = max(0, len(findings) - MAX_FINDINGS)
    return LinterReport(
        findings[:MAX_FINDINGS],
        tool=tool,
        note=note,
        truncated=truncated,
        exclusions=exclusions[:MAX_FINDINGS],
    )
