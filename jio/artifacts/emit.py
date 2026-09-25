"""Emetteurs : une doctrine, tous les dialectes.

Chaque outil d'agent a son format d'instructions. Plutot que d'ecrire sept fois
la meme chose (et de les laisser diverger), on ecrit la doctrine une fois dans
`doctrine.py` et on la traduit ici.

Formats couverts :
  opencode   .opencode/agents/<nom>.md  (frontmatter YAML + prompt)
  hermes     .hermes/skills/<cat>/<nom>/SKILL.md  (standard agentskills.io)
  claude     CLAUDE.md
  agents     AGENTS.md        (volontairement <= 150 lignes : au-dela, survole)
  gemini     GEMINI.md
  cursor     .cursor/rules/jio.mdc
  copilot    .github/copilot-instructions.md
  mcp        .mcp.json + serveur MCP local
"""

from __future__ import annotations

import json
from pathlib import Path

from .definitions import AGENTS, PRINCIPLES, SKILLS, AgentSpec
from .doctrine import COMPACT

__all__ = ["manifest", "write_manifest", "TARGETS"]

TARGETS = (
    "opencode", "hermes", "claude", "agents", "gemini", "cursor", "copilot", "mcp",
    # Le CABLAGE du serveur MCP dans les outils qui ne lisent pas `.mcp.json`. Sans ces
    # deux cibles, les outils JIO existaient et etaient injoignables depuis opencode et
    # Hermes : la difference entre « ecrit » et « branche ».
    "opencode-mcp", "hermes-mcp",
)


# --------------------------------------------------------------------------- #
# Blocs communs
# --------------------------------------------------------------------------- #


def _principles_block() -> str:
    return "\n".join(f"{i}. {p}" for i, p in enumerate(PRINCIPLES, 1))


def _commands_block() -> str:
    return """\
```
jio doctor                 etat du systeme, fournisseurs detectes
jio bench --skill 0.30     mesure le gain du harness (S0 -> S3, controle a budget egal)
jio audit <fichier>        audite un artefact ; derive des regles executables de lui-meme
jio run "<objectif>"       mission complete avec la boucle verifiee
jio run "<objectif>" --prose   mission de DOCUMENT : la boucle de preuve complete
                               s'applique a un texte (calculs, blocs, chemins cites)
jio claims <document>      verifie les faits d'une prose : calculs annonces, blocs
                           presentes comme Python, chemins cites (0 = conforme)
jio trace <journal>        rejoue et verifie un journal (chaine de hachage + exploits)
```
Le banc est executable sans aucune cle API : les reponses sont simulees, la
verification est reelle. `jio bench` refusera de vous vendre un chiffre : il
compare toujours a un tirage aveugle de meme budget."""


def _agent_markdown(agent: AgentSpec, *, frontmatter: bool = True) -> str:
    if not frontmatter:
        return agent.prompt
    perm = "\n".join(f"  {k}: {v}" for k, v in sorted(agent.permission.items()))
    tools = "\n".join(f"  {k}: {str(v).lower()}" for k, v in sorted(agent.tools.items()))
    parts = [
        "---",
        f"description: {json.dumps(agent.description, ensure_ascii=False)}",
        f"mode: {agent.mode}",
        f"temperature: {agent.temperature}",
        f"steps: {agent.steps}",
    ]
    if tools:
        parts += ["tools:", tools]
    parts += ["permission:", perm, "---", "", agent.prompt.rstrip(), ""]
    return "\n".join(parts)


def _hermes_skill(skill) -> str:
    tags = ", ".join(skill.tags)
    return f"""\
---
name: {skill.name}
description: {skill.description}
version: {skill.version}
platforms: [claude-code, opencode, codex, cursor, any]
metadata:
  hermes:
    tags: [{tags}]
    category: {skill.category}
---

{skill.body.rstrip()}

## Reference
Doctrine complete : `jio/artifacts/doctrine.py`. Cette competence est generee
depuis une source unique : ne l'editez pas a la main, editez la source.
"""


# --------------------------------------------------------------------------- #
# Emetteurs par outil
# --------------------------------------------------------------------------- #


def _target_opencode() -> dict[str, str]:
    files: dict[str, str] = {}
    for agent in AGENTS:
        files[f".opencode/agents/{agent.name}.md"] = _agent_markdown(agent)
    files[".opencode/agents/README.md"] = (
        "# Agents JIO pour opencode\n\n"
        "Genere par `jio artifacts --target opencode --write`. Ne pas editer a la "
        "main : editer `jio/artifacts/definitions.py`.\n\n"
        + "\n".join(f"- `{a.name}` — {a.description}" for a in AGENTS)
        + "\n\nUsage : `opencode run \"<objectif>\" --agent jio --format json`\n"
    )
    return files


def _target_hermes() -> dict[str, str]:
    files: dict[str, str] = {}
    for skill in SKILLS:
        files[f".hermes/skills/{skill.category}/{skill.name}/SKILL.md"] = _hermes_skill(skill)
    files[".hermes/skills/README.md"] = (
        "# Competences JIO (standard agentskills.io)\n\n"
        "Copier ou lier dans `~/.hermes/skills/` :\n\n"
        "```sh\n"
        "mkdir -p ~/.hermes/skills\n"
        "cp -r .hermes/skills/* ~/.hermes/skills/\n"
        "```\n\n"
        + "\n".join(
            f"- `{s.category}/{s.name}` — {s.description}" for s in SKILLS
        )
        + "\n"
    )
    return files


def _context_file(title: str, extra: str = "") -> str:
    return f"""\
# {title}

> Genere par `jio artifacts`. Source unique : `jio/artifacts/doctrine.py`.
> Ne pas editer a la main.

## Les trois etats d'une livraison

`DELIVERED` / `DELIVERED_UNDER_RESERVATION` / `ABSTAINED`. Un quatrieme etat
n'existe pas : « ca devrait marcher » est l'absence d'etat, pas un etat.

## Principes

{_principles_block()}

## Doctrine (extrait)

{COMPACT}

## Commandes

{_commands_block()}
{extra}"""


def _target_claude() -> dict[str, str]:
    extra = """
## Sous-agents

Les roles du harness sont disponibles comme agents (`jio`, `jio-verifier`,
`jio-redteam`, `jio-grounder`, `jio-comptroller`, `jio-archaeologist`,
`jio-forge`). Le verificateur n'a **pas** le droit d'ecrire : un verificateur qui
peut modifier l'artefact qu'il juge finit toujours par le rendre conforme.
"""
    return {"CLAUDE.md": _context_file("CLAUDE.md — instructions projet", extra)}


def _target_agents() -> dict[str, str]:
    # <= 150 lignes : au-dela, le fichier est survole et non lu.
    content = _context_file(
        "AGENTS.md",
        "\n## Regle de taille\n\nCe fichier est volontairement court. Detail complet : "
        "`docs/VISION-ARCHITECTURE.md`, doctrine : `jio/artifacts/doctrine.py`.\n",
    )
    lines = content.splitlines()
    if len(lines) > 150:  # pragma: no cover - garde-fou de qualite
        raise ValueError(f"AGENTS.md ferait {len(lines)} lignes (limite 150)")
    return {"AGENTS.md": content}


def _target_gemini() -> dict[str, str]:
    return {"GEMINI.md": _context_file("GEMINI.md — instructions projet")}


def _target_cursor() -> dict[str, str]:
    body = _context_file("JIO — harness anti-erreur").replace("# ", "## ", 1)
    return {
        ".cursor/rules/jio.mdc": (
            "---\n"
            "description: JIO anti-error harness rules\n"
            "alwaysApply: true\n"
            "---\n\n"
            f"{body}"
        )
    }


def _target_copilot() -> dict[str, str]:
    return {
        ".github/copilot-instructions.md": _context_file(
            "Copilot instructions — JIO harness"
        )
    }


def _target_opencode_mcp() -> dict[str, str]:
    """`opencode.json` : le cablage du serveur MCP pour opencode.

    Les agents `jio-*` de `.opencode/agents/` n'avaient AUCUN moyen d'appeler les outils
    MCP de JIO : `.mcp.json` est le dialecte de Claude Code, et opencode lit
    `opencode.json`. Le serveur etait ecrit, teste, et injoignable.
    """
    from .wiring import fragment_opencode

    return {"opencode.json": json.dumps(fragment_opencode(), indent=2, ensure_ascii=False) + "\n"}


def _target_hermes_mcp() -> dict[str, str]:
    """Le fragment Hermes, livre comme FICHIER plutot que comme texte d'aide.

    Hermes lit `~/.hermes/config.yaml`, qui appartient a l'utilisateur : ce depot ne
    l'ecrit donc pas. Il livre le bloc pret a coller, dans un fichier nomme pour ce qu'il
    est — un extrait a fusionner, pas une configuration.
    """
    from .wiring import fragment_hermes

    return {
        ".hermes/mcp-fragment.yaml": (
            "# Fragment a fusionner dans ~/.hermes/config.yaml (cle `mcp_servers`),\n"
            "# puis `/reload-mcp` dans une session Hermes. NON ecrit dans votre config :\n"
            "# ce depot ne modifie pas les fichiers de configuration de l'utilisateur.\n"
            "\n" + fragment_hermes()
        )
    }


def _target_mcp() -> dict[str, str]:
    config = {
        "mcpServers": {
            "jio": {
                "command": "python3",
                "args": ["-m", "jio.mcp_server"],
                "env": {"JIO_ROOT": "."},
            }
        }
    }
    return {
        ".mcp.json": json.dumps(config, indent=2, ensure_ascii=False) + "\n",
        ".mcp.README.md": (
            "# Serveur MCP JIO\n\n"
            "Expose la verification JIO a tout client MCP (Claude Code, opencode,\n"
            "Cursor, Copilot, Hermes) :\n\n"
            "- `jio_prove` — prouve une source contre des regles executables\n"
            "- `jio_audit` — audite un fichier et derive ses regles\n"
            "- `jio_contract` — renvoie le contrat de livraison (3 etats)\n"
            "- `jio_skills` — liste les competences et leur declencheur\n\n"
            "Transport : stdio, JSON-RPC 2.0, **zero dependance**.\n"
        ),
    }


_EMITTERS = {
    "opencode": _target_opencode,
    "hermes": _target_hermes,
    "claude": _target_claude,
    "agents": _target_agents,
    "gemini": _target_gemini,
    "cursor": _target_cursor,
    "copilot": _target_copilot,
    "mcp": _target_mcp,
    "opencode-mcp": _target_opencode_mcp,
    "hermes-mcp": _target_hermes_mcp,
}


def manifest(targets: tuple[str, ...] | None = None) -> dict[str, str]:
    """Chemin relatif -> contenu, pour tous les artefacts demandes."""
    wanted = targets or TARGETS
    unknown = [t for t in wanted if t not in _EMITTERS]
    if unknown:
        raise ValueError(f"cible inconnue : {', '.join(unknown)}")
    files: dict[str, str] = {}
    for target in wanted:
        files.update(_EMITTERS[target]())
    return files


def write_manifest(root: Path, targets: tuple[str, ...] | None = None) -> list[Path]:
    """Ecrit les artefacts sous `root` et renvoie la liste des fichiers ecrits.

    Cette fonction n'ecrit plus elle-meme : elle DELEGUE a `write_guard.ecrire_manifest`.
    Il y avait ici une seconde implementation de l'ecriture, qui ecrasait tout ce qu'elle
    trouvait. Deux implementations pour un meme risque, c'est une regle qui tombe : celle
    du garde-fou, qui PRESERVE un fichier ne portant pas la marque de jio, n'etait pas
    appliquee a ceux qui passaient par ce chemin. Un seul ecrivain, une seule doctrine.
    """
    from .write_guard import ecrire_manifest

    decisions = ecrire_manifest(root, manifest(targets))
    return [root / d.chemin for d in decisions]
