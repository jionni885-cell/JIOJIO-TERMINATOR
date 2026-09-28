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

_CLAIMS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": (
                "The document to verify, passed DIRECTLY as text — a draft you are "
                "about to deliver. Markdown, plain text, report."
            ),
        },
        "root": {
            "type": "string",
            "description": (
                "Project root used to resolve cited file paths, confined to "
                "JIO_ROOT. Omit to skip path checking entirely."
            ),
        },
    },
    "required": ["text"],
}

_SKILLS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "name": {"type": "string", "description": "Return this skill's full body."},
        "category": {"type": "string", "description": "Filter by category."},
    },
}

_CLARIFY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "objective": {
            "type": "string",
            "description": "The task as the human wrote it, verbatim.",
        },
        "context": {
            "type": "string",
            "description": (
                "Optional project context (README, AGENTS.md). It can supply where the work "
                "comes from and what is forbidden — never the action, the target or the "
                "success criterion: those belong to the request."
            ),
        },
    },
    "required": ["objective"],
}

_STATUS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
}

_COHERENCE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
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
        "name": "jio_claims",
        "description": (
            "Verify the CHECKABLE FACTS of a document you are about to deliver: "
            "stated arithmetic (recomputed), fenced code blocks labelled as Python "
            "(must compile), cited file paths (must exist). Returns the refuted "
            "claims with their proof. Exit meaning: conforme / refuted / nothing to "
            "verify — the last is NOT a pass. A wrong number is the cheapest way to "
            "be confidently wrong, and it is detectable in milliseconds."
        ),
        "inputSchema": _CLAIMS_SCHEMA,
    },
    {
        "name": "jio_skills",
        "description": "List the JIO skills and when to use them, or fetch one body.",
        "inputSchema": _SKILLS_SCHEMA,
    },
    {
        "name": "jio_clarify",
        "description": (
            "Call this BEFORE doing any work. It reports the 0-3 ESSENTIAL questions your "
            "objective leaves open, each with the consequence of not answering and the "
            "assumption that will be taken instead. If it returns questions, ASK THE HUMAN "
            "them — do not start. An answer to the wrong question is the most expensive "
            "failure there is. If it returns none, the objective carries an action, a named "
            "target and a success criterion: work, and declare any assumption you take."
        ),
        "inputSchema": _CLARIFY_SCHEMA,
    },
    {
        "name": "jio_coherence",
        "description": (
            "Call this BEFORE declaring work FINISHED. Runs NINE checks over this whole "
            "repository — generated artifacts match their doctrine, announced numbers match "
            "the measurement, verifiable claims of the documents hold, every `jio <command>` "
            "cited by a document or an artifact exists in the REAL parser, the skills an agent "
            "will read stay inside the budget and carry no dangerous instruction, environment "
            "variables are documented, the package passes its own gates, the journal hash chain "
            "is intact, and no autonomous plan leaves steps unattempted. Returns one verdict per "
            "check WITH its evidence. Exit 0 means coherent; anything else names the file, the "
            "line and the fix. An unchecked state is not a good state."
        ),
        "inputSchema": _COHERENCE_SCHEMA,
    },
    {
        "name": "jio_status",
        "description": (
            "Is this project integrated, and what is missing? Reports which native artifacts "
            "exist, whether the MCP server is wired, whether `.jio/ACTIVE.md` exists, and the "
            "exact command to fix what is missing. Fail-closed: an unreported state is not a "
            "good state."
        ),
        "inputSchema": _STATUS_SCHEMA,
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


def _tool_claims(args: dict[str, Any]) -> str:
    """Verifie les faits verifiables d'un TEXTE.

    Le texte arrive directement, pas par un chemin : un agent qui redige tient son
    brouillon en contexte, et lui demander d'ecrire un fichier pour pouvoir le
    verifier serait une friction qui garantit que la verification n'aura pas lieu.
    """
    from .verify.claims import verifier

    texte = str(args.get("text", ""))
    if not texte.strip():
        return "REFUS : aucun texte fourni."
    if len(texte) > MAX_SOURCE:
        return f"REFUS : document trop long ({len(texte)} caracteres)."

    racine: Path | None = None
    demande = str(args.get("root", ""))
    if demande:
        try:
            racine = _confined(demande)
        except PermissionError as exc:
            return f"REFUS : {exc}"

    rapport = verifier(texte, racine=racine)
    if not rapport.verifications:
        return (
            "RIEN A VERIFIER — ce document ne contient aucun fait controlable (aucun "
            "calcul annonce, aucun bloc annonce comme Python). Ce n'est NI un succes, "
            "NI un echec : le document n'offre rien a prouver."
        )

    out = [rapport.resume(), ""]
    for verification in rapport.verifications:
        marque = "ok" if verification.ok else ("KO" if verification.bloquant else "!!")
        out.append(f"[{marque}] {verification.message[:300]}")
    out.append("")
    if rapport.bloquantes:
        out.append(
            "NON CONFORME — une affirmation refutee est un fait, pas une opinion. "
            "Corrigez le texte, ou retirez l'affirmation."
        )
    else:
        out.append("CONFORME sur ce qui est verifiable ; le reste est declare non verifie.")
    if rapport.ignorees or rapport.non_evaluees:
        out.append(
            f"PARTIEL : {rapport.ignorees} affirmation(s) au-dela de la limite de volume "
            f"et {rapport.non_evaluees} calcul(s) trop long(s) : NON verifies."
        )
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


def _tool_clarify(args: dict[str, Any]) -> str:
    """La porte de clarification, accessible DANS la boucle de l'agent.

    C'est le point qui compte : l'agent n'a pas besoin de quitter son contexte pour demander
    « qu'est-ce qui manque pour decider ? ». Il appelle l'outil, obtient les questions, et
    les pose a l'humain. Un controle qui exige de sortir de la boucle n'est pas applique.
    """
    from .clarify import analyser, formater

    objectif = str(args.get("objective", ""))
    if not objectif.strip():
        return "REFUS : aucun objectif. Donnez la demande telle que l'humain l'a ecrite."
    analyse = analyser(objectif, contexte=str(args.get("context", "")))
    texte = formater(analyse)
    if analyse.actionnable:
        return texte + "\n\nVERDICT : actionnable — travaille, et declare tes hypotheses."
    return (
        texte
        + "\n\nVERDICT : demande CES questions a l'humain AVANT de commencer.\n"
        + "Si tu ne peux pas lui parler, prends les hypotheses ci-dessus et ECRIS-LES en tete "
        + "de livraison, une ligne chacune."
    )


def _tool_status(_args: dict[str, Any]) -> str:
    """L'etat d'integration du projet, lu sur le disque et jamais suppose.

    Un agent qui arrive dans un depot inconnu n'a aucun moyen de savoir si les artefacts
    qu'il lit sont a jour, ou si le serveur MCP qu'on lui propose repond vraiment. Cet outil
    le dit — y compris « je ne sais pas », quand le fichier de registre manque.
    """
    import json

    from .artifacts import TARGETS, manifest
    from .artifacts.write_guard import REGISTRE

    racine = _root()
    attendus = manifest(TARGETS)
    manquants = [rel for rel in sorted(attendus) if not (racine / rel).is_file()]
    fiche = racine / ".jio" / "ACTIVE.md"
    lignes = [
        f"PROJET : {racine}",
        f"artefacts natifs : {len(attendus) - len(manquants)}/{len(attendus)} presents",
    ]
    if manquants:
        lignes.append("  manquants : " + ", ".join(manquants[:6]) + (" ..." if len(manquants) > 6 else ""))
        lignes.append("  -> `jio start` les ecrit, sans rien detruire.")
    registre = racine / REGISTRE
    if registre.is_file():
        try:
            entrees = json.loads(registre.read_text(encoding="utf-8")).get("fichiers", {})
            lignes.append(f"registre : {len(entrees)} fichier(s) signes par jio (mise a jour sure)")
        except (OSError, ValueError):
            lignes.append("registre : ILLISIBLE — jio redeviendra prudent (regle de repli : la marque)")
    else:
        lignes.append("registre : absent — jio ne sait pas quels fichiers sont les siens")
    lignes.append(
        f"fiche d'integration : {'presente' if fiche.is_file() else 'ABSENTE (.jio/ACTIVE.md)'}"
    )
    cablage = [rel for rel in ("opencode.json", ".cursor/mcp.json", ".mcp.json")
               if (racine / rel).is_file()]
    lignes.append("cablage MCP : " + (", ".join(cablage) if cablage else "aucun fichier trouve"))
    lignes += [
        "",
        "PROCHAINES ETAPES",
        "  1. si des artefacts manquent : `jio start`",
        "  2. avant de travailler : `jio clarify \"<objectif>\"` (code 3 = il faut DEMANDER)",
        "  3. etat du systeme : `jio doctor`",
    ]
    return "\n".join(lignes)


def _tool_coherence(_args: dict[str, Any]) -> str:
    """Le portail d'ensemble, du point de vue de l'agent qui doit declarer « fini ».

    Neuf controles sur le depot, un verdict, et la preuve de chaque constat. Un agent qui
    s'apprete a rendre son travail a besoin de cette porte : sans elle, « c'est fini » est une
    opinion — et c'est exactement ce que ce serveur existe pour empecher.
    """
    from .verify.coherence import controler, formater

    rapport = controler(_root())
    return formater(rapport)


_HANDLERS: dict[str, Callable[[dict[str, Any]], str]] = {
    "jio_prove": _tool_prove,
    "jio_audit": _tool_audit,
    # La prose : le seul outil qui repond a « mon brouillon dit-il quelque chose de
    # faux ? » sans rien executer de l'agent, et sans quitter son contexte.
    "jio_claims": _tool_claims,
    "jio_contract": _tool_contract,
    "jio_skills": _tool_skills,
    "jio_clarify": _tool_clarify,
    "jio_status": _tool_status,
    # La porte finale : elle ne dit pas seulement qu'il y a un probleme, elle dit lequel et
    # avec quelle preuve — l'agent peut donc la relancer apres correction.
    "jio_coherence": _tool_coherence,
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
    """Boucle stdio : une ligne JSON par message, comme le veut le protocole.

    Le nombre de messages TRAITES est compte, et une session qui en traite zero le DIT sur la
    sortie d'erreur. Sans cela, un client mal configure qui ouvre le serveur sans rien envoyer
    obtenait une sortie vide et un code 0 : indistinguable d'un serveur qui aurait tout bien
    repondu. La sortie d'erreur n'est pas le canal du protocole, donc cette note ne peut pas
    corrompre un echange en cours.
    """
    traites = 0
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
        traites += 1
    if traites == 0:
        print(
            "[JIO-MCP] aucun message recu : le serveur n'a rien eu a servir. Il attend une "
            "ligne JSON par requete sur son entree standard (JSON-RPC 2.0). Pour verifier "
            "qu'un client le branche vraiment : `jio mcp --prove`.",
            file=sys.stderr,
            flush=True,
        )
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
