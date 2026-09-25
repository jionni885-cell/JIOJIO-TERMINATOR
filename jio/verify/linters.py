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
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

__all__ = ["LintFinding", "LinterReport", "analyse"]

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
    def label(self) -> str:
        """Constat pret a afficher : explication francaise + message d'origine."""
        code = self.rule.split(":")[-1]
        plain = plain_french(code)
        return f"{plain} — {self.message}" if plain else self.message


@dataclass
class LinterReport:
    findings: list[LintFinding]
    tool: str = ""       # l'outil reellement utilise, "" si aucun
    note: str = ""       # ce qu'il faut dire a l'utilisateur
    truncated: int = 0   # constats au-dela du plafond


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
        cmd = [*ruff, "check", "--select", BUG_RULES, "--output-format", "json", *files]
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
    return LinterReport(findings[:MAX_FINDINGS], tool=tool, note=note, truncated=truncated)
