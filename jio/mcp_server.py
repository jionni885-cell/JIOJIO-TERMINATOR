"""Serveur MCP JIO — stdio, JSON-RPC 2.0, zero dependance.

Objectif : rendre la verification JIO appelable depuis N'IMPORTE QUEL client
MCP (Claude Code, opencode, Cursor, Copilot, Hermes). C'est le point de
raccordement : sans lui, le harness reste une CLI que l'agent doit penser a
appeler ; avec lui, la verification est un outil disponible dans le contexte.

Protocole implemente : `initialize`, `tools/list`, `tools/call`, plus les
notifications (sans `id`), qui ne recoivent jamais de reponse.

Securite : tout chemin est confine a `JIO_ROOT` (par defaut le repertoire
courant). Un serveur d'outils qui lit n'importe quel chemin sur demande est une
vulnerabilite, pas une fonctionnalite.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

__all__ = ["TOOLS", "handle", "main"]

PROTOCOL = "2024-11-05"
MAX_SOURCE = 200_000  # caracteres ; au-dela on refuse plutot que de ramer

# --------------------------------------------------------------------------- #
# Outils
# --------------------------------------------------------------------------- #

_PROVE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "description": "Python source under test."},
        "checks": {
            "type": "object",
            "description": (
                "Map rule_id -> python snippet appended after the source. The snippet "
                "must RAISE (AssertionError) to fail. Exit code 0 means the rule holds."
            ),
            "additionalProperties": {"type": "string"},
        },
        "entrypoint": {"type": "string", "description": "Expected entry point name."},
    },
    "required": ["source", "checks"],
}

_AUDIT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "File path, confined to JIO_ROOT."},
        "entrypoint": {"type": "string", "description": "Function or class to audit."},
    },
    "required": ["path"],
}

_SKILLS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Return this skill's full body."},
        "category": {"type": "string", "description": "Filter by category."},
    },
}

TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "jio_prove",
        "description": (
            "Prove a Python source against executable rules. Returns one verdict per "
            "rule with the exact command and output. Fail-closed: a rule whose check "
            "did not run is NOT a pass."
        ),
        "inputSchema": _PROVE_SCHEMA,
    },
    {
        "name": "jio_audit",
        "description": (
            "Audit a file: derive executable rules from the artifact itself "
            "(callability, reproducibility, docstring examples) and prove them. "
            "Returns CONFORME / NON CONFORME / INDETERMINE plus declared limits."
        ),
        "inputSchema": _AUDIT_SCHEMA,
    },
    {
        "name": "jio_contract",
        "description": (
            "Return the JIO delivery contract and the anti-error doctrine. Call this "
            "before producing a deliverable."
        ),
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "jio_skills",
        "description": "List the JIO skills and when to use them, or fetch one body.",
        "inputSchema": _SKILLS_SCHEMA,
    },
)


# --------------------------------------------------------------------------- #
# Securite : confinement des chemins
# --------------------------------------------------------------------------- #


def _root() -> Path:
    return Path(os.environ.get("JIO_ROOT", ".")).resolve()


def _confined(path_str: str) -> Path:
    """Resout un chemin en refusant toute sortie de JIO_ROOT."""
    root = _root()
    candidate = (root / path_str).resolve() if not Path(path_str).is_absolute() else Path(
        path_str
    ).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise PermissionError(
            f"chemin hors de JIO_ROOT ({root}) : {candidate}"
        ) from exc
    return candidate


# --------------------------------------------------------------------------- #
# Implementations
# --------------------------------------------------------------------------- #


def _tool_prove(args: dict[str, Any]) -> str:
    from .verify.executable import ExecutableProver, Sandbox
    from .core.types import Rule, RuleKind, Spec

    source = str(args.get("source", ""))
    if len(source) > MAX_SOURCE:
        return f"REFUS : source trop longue ({len(source)} caracteres)."
    checks = {str(k): str(v) for k, v in (args.get("checks") or {}).items()}
    if not checks:
        return "REFUS : aucune regle fournie. Une preuve sans regle n'existe pas."

    rules = tuple(
        Rule(id=rid, statement=f"regle fournie par l'appelant ({rid})", kind=RuleKind.TEST)
        for rid in checks
    )
    spec = Spec(mission="preuve MCP", rules=rules)
    prover = ExecutableProver(sandbox=Sandbox(timeout=30))
    try:
        res = prover.prove(
            source, spec, hidden_checks=checks, entrypoint=str(args.get("entrypoint", ""))
        )
    except Exception as exc:  # fail-closed : jamais de « ca devrait passer »
        return f"INDETERMINE — la preuve n'a pas pu etre executee : {exc}"

    lines = [
        f"{len(res.witnesses) - len(res.failures)}/{len(res.witnesses)} regles satisfaites",
        f"verdict : {'CONFORME' if res.passed else 'NON CONFORME'}",
        "",
    ]
    for w in res.witnesses:
        mark = "ok" if w.ok else "KO"
        detail = ""
        if not w.ok:
            rows = [x.strip() for x in (w.stderr or "").splitlines() if x.strip()]
            detail = rows[-1][:200] if rows else f"exit {w.exit_code}"
        lines.append(f"[{mark}] {w.rule_id} {detail}".rstrip())
    if not res.passed:
        lines += ["", "Rappel : l'echec d'un test n'accuse pas toujours l'artefact.",
                  "Verifier dans l'ordre : artefact, specification, test, environnement."]
    return "\n".join(lines)


def _tool_audit(args: dict[str, Any]) -> str:
    from .verify.autocheck import derive
    from .verify.executable import ExecutableProver, Sandbox

    try:
        path = _confined(str(args.get("path", "")))
    except PermissionError as exc:
        return f"REFUS : {exc}"
    if not path.is_file():
        return f"REFUS : {path} n'est pas un fichier."
    if path.stat().st_size > MAX_SOURCE:
        return "REFUS : fichier trop volumineux."

    source = path.read_text(encoding="utf-8", errors="replace")
    derived = derive(source, entrypoint=str(args.get("entrypoint", "")), path=path)
    out = [f"AUDIT {path}", f"entree : {derived.entrypoint or 'aucune'}", ""]

    if not derived.verifiable:
        out.append("0 regle executable -> RIEN N'A ETE PROUVE.")
        out += [f"- {lim}" for lim in derived.spec.under_specified]
        out.append("")
        out.append("VERDICT : INDETERMINE — declarer un succes ici serait un mensonge.")
        return "\n".join(out)

    prover = ExecutableProver(sandbox=Sandbox(timeout=30))
    res = prover.prove(
        source,
        derived.spec,
        hidden_checks=derived.checks,
        entrypoint=derived.entrypoint,
        preamble=derived.preamble,
    )
    out.append(f"{len(res.witnesses) - len(res.failures)}/{len(res.witnesses)} regles satisfaites")
    out.append("")
    for w in res.witnesses:
        mark = "ok" if w.ok else ("??" if w.rule_id in res.advisory_ids else "KO")
        detail = ""
        if not w.ok:
            rows = [x.strip() for x in (w.stderr or "").splitlines() if x.strip()]
            detail = rows[-1][:200] if rows else f"exit {w.exit_code}"
        out.append(f"[{mark}] {w.rule_id} {detail}".rstrip())
    if res.reservations:
        out += ["", "RESERVES (suspect, non prouve) :"]
        out += [f"- {w.rule_id}" for w in res.reservations]
    if derived.spec.under_specified:
        out += ["", "LIMITES DECLAREES (ce qui n'a PAS ete prouve) :"]
        out += [f"- {lim}" for lim in derived.spec.under_specified]
    out += [
        "",
        "VERDICT : "
        + (
            "CONFORME sur les regles verifiables (et seulement sur celles-la)."
            if res.passed
            else "NON CONFORME — livrer en l'etat serait une erreur silencieuse."
        ),
    ]
    return "\n".join(out)


def _tool_contract(_args: dict[str, Any]) -> str:
    from .artifacts.doctrine import FULL

    return FULL


def _tool_skills(args: dict[str, Any]) -> str:
    from .artifacts.definitions import SKILLS

    wanted = str(args.get("name", ""))
    category = str(args.get("category", ""))
    if wanted:
        for skill in SKILLS:
            if skill.name == wanted:
                return skill.body
        return f"competence inconnue : {wanted}"
    rows = ["Competences disponibles (charger selon le declencheur, pas d'avance) :", ""]
    for skill in SKILLS:
        if category and skill.category != category:
            continue
        rows.append(f"- {skill.name} [{skill.category}] — {skill.description}")
    rows += [
        "",
        "Regle de contexte : une competence se charge quand son declencheur apparait,",
        "pas par precaution. Le contexte est un budget, pas une etagere.",
    ]
    return "\n".join(rows)


_HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "jio_prove": _tool_prove,
    "jio_audit": _tool_audit,
    "jio_contract": _tool_contract,
    "jio_skills": _tool_skills,
}


# --------------------------------------------------------------------------- #
# Protocole
# --------------------------------------------------------------------------- #


def handle(request: dict[str, Any]) -> dict[str, Any] | None:
    """Traite une requete JSON-RPC. Renvoie None pour une notification."""
    method = request.get("method")
    rid = request.get("id")
    params = request.get("params") or {}

    if rid is None:
        return None  # notification : jamais de reponse

    if method == "initialize":
        result = {
            "protocolVersion": PROTOCOL,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "jio", "version": _version()},
        }
    elif method == "tools/list":
        result = {"tools": list(TOOLS)}
    elif method == "tools/call":
        name = str(params.get("name", ""))
        handler = _HANDLERS.get(name)
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "error": {"code": -32602, "message": f"outil inconnu : {name}"},
            }
        try:
            text = handler(dict(params.get("arguments") or {}))
            result = {"content": [{"type": "text", "text": text}], "isError": False}
        except Exception as exc:  # un outil qui plante ne doit pas tuer le serveur
            result = {
                "content": [{"type": "text", "text": f"ERREUR outil {name} : {exc}"}],
                "isError": True,
            }
    elif method in ("ping", "resources/list", "prompts/list"):
        result = {}
    else:
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "error": {"code": -32601, "message": f"methode inconnue : {method}"},
        }

    return {"jsonrpc": "2.0", "id": rid, "result": result}


def _version() -> str:
    try:
        from . import __version__

        return __version__
    except Exception:  # pragma: no cover
        return "0.0.0"


def main(argv: list[str] | None = None) -> int:
    """Boucle stdio : une ligne JSON par message, comme le veut le protocole."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "JSON invalide"},
                    }
                ),
                flush=True,
            )
            continue
        response = handle(request)
        if response is None:
            continue
        print(json.dumps(response, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
