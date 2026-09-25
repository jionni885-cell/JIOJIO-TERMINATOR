"""Brancher le serveur MCP JIO dans les outils, SANS jamais ecraser une config existante.

Le depot emet des artefacts natifs pour chaque outil, mais jusqu'ici il n'y avait RIEN
pour brancher le serveur MCP dans les deux outils qui comptent pour l'utilisateur :
opencode et Hermes. `.mcp.json` est le dialecte de Claude Code ; opencode lit
`opencode.json` sous la cle `mcp` avec `type: "local"` et un tableau `command` ; Hermes lit
`~/.hermes/config.yaml` sous la cle `mcp_servers`. Le serveur JIO etait donc ecrit, teste,
et injoignable depuis ces deux-la.

Deux regles, non negociables
----------------------------
1. **On ne touche jamais a une configuration existante.** Si le fichier n'existe pas, on
   l'ecrit. S'il existe, on ne le reecrit pas en silence : on rend le FRAGMENT a inserer,
   et on dit pourquoi. Une configuration utilisateur n'est pas un artefact genere par ce
   depot — c'est le meme principe que `scripts/install.sh`, qui refuse d'ecraser.

2. **Le fragment est du TEXTE genere a partir d'une seule source.** La commande, les
   variables d'environnement et les cles de chaque dialecte vivent ici, une fois.

Le troisieme dialecte (`~/.codex/config.toml`, cle `[mcp_servers.<nom>]`) est du TOML :
"emettre le fragment" pour un humain qui doit le coller a la main suffit, et un mergeur de
TOML ecrit a la main serait un risque pour un gain nul.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

__all__ = [
    "NOM_SERVEUR",
    "prouver_branchement",
    "fragment_opencode",
    "fragment_hermes",
    "fragment_codex",
    "fragments",
    "brancher",
    "DIALECTES",
]

#: Nom du serveur MCP tel qu'il apparaitra dans les outils de l'IA.
NOM_SERVEUR = "jio"

#: L'outil est recherche comme module Python (`python3 -m jio.mcp_server`) : cela marche
#: partout ou `jio` est importable, sans dependre du PATH ni d'un chemin absolu — un
#: chemin absolu copie dans une config ne survit pas au deplacement du depot.
_COMMANDE = ("python3", "-m", "jio.mcp_server")


def fragment_opencode() -> dict[str, object]:
    """Bloc `mcp` de `opencode.json` (schema opencode.ai).

    `enabled: true` est explicite : un serveur present mais desactive serait un cablage
    qui ne fait rien, ce qui est exactement le defaut que ce module corrige.
    """
    return {
        "mcp": {
            NOM_SERVEUR: {
                "type": "local",
                "command": list(_COMMANDE),
                "enabled": True,
                "environment": {"JIO_ROOT": "."},
            }
        }
    }


def fragment_hermes() -> str:
    """Bloc YAML `mcp_servers` de `~/.hermes/config.yaml`.

    Rend du TEXTE : on ne peut pas fusionner un YAML sans charger puis reecrire le fichier
    de l'utilisateur, donc on n'essaie pas. L'humain colle, et JIO lui dit ou.
    """
    return (
        "# Ajouter sous la cle de premier niveau `mcp_servers` de\n"
        "# ~/.hermes/config.yaml, puis `/reload-mcp` dans une session :\n"
        "mcp_servers:\n"
        f"  {NOM_SERVEUR}:\n"
        '    command: "python3"\n'
        '    args: ["-m", "jio.mcp_server"]\n'
        "    env:\n"
        '      JIO_ROOT: "${JIO_ROOT}"\n'
    )


def fragment_codex() -> str:
    """Bloc TOML `[mcp_servers.jio]` de `~/.codex/config.toml`."""
    return (
        "# Ajouter a ~/.codex/config.toml :\n"
        f"[mcp_servers.{NOM_SERVEUR}]\n"
        'command = "python3"\n'
        'args = ["-m", "jio.mcp_server"]\n'
    )


def fragment_claude_code() -> str:
    """`claude mcp add` — la CLI ecrit la config elle-meme, on donne la commande."""
    return (
        "# Ajouter le serveur avec la CLI (elle ecrit la configuration) :\n"
        f"claude mcp add {NOM_SERVEUR} -- python3 -m jio.mcp_server\n"
    )


def fragment_cursor() -> str:
    """Bloc `mcpServers` de `.cursor/mcp.json` (ou ~/.cursor/mcp.json)."""
    return json.dumps(
        {"mcpServers": {NOM_SERVEUR: {"command": "python3", "args": list(_COMMANDE[1:])}}},
        indent=2,
        ensure_ascii=False,
    ) + "\n"


#: Dialecte -> (fichier a creer si absent, fonction de fragment, description pour l'aide).
#: `None` comme fichier signifie : « il n'y a rien a ecrire, c'est une commande a lancer ».
DIALECTES: tuple[tuple[str, str | None, str], ...] = (
    ("opencode", "opencode.json", "opencode (JSON)"),
    ("hermes", None, "Hermes (YAML, ~/.hermes/config.yaml)"),
    ("codex", None, "Codex (TOML, ~/.codex/config.toml)"),
    ("claude-code", None, "Claude Code (commande CLI)"),
    ("cursor", ".cursor/mcp.json", "Cursor (JSON, .cursor/mcp.json)"),
)


def _contenu(dialecte: str) -> str:
    """Le fragment d'un dialecte, en texte pret a coller."""
    if dialecte == "opencode":
        return json.dumps(fragment_opencode(), indent=2, ensure_ascii=False) + "\n"
    return {
        "hermes": fragment_hermes,
        "codex": fragment_codex,
        "claude-code": fragment_claude_code,
        "cursor": fragment_cursor,
    }[dialecte]()


def fragments() -> dict[str, str]:
    """Tous les fragments, dans l'ordre de `DIALECTES`."""
    return {nom: _contenu(nom) for nom, _, _ in DIALECTES}


def brancher(racine: Path, dialecte: str = "opencode") -> tuple[bool, str]:
    """Branche le serveur MCP pour un dialecte. Rend `(ecrit, message)`.

    Trois issues, et la troisieme est la plus importante :

      * le fichier n'existe pas -> on l'ecrit, et on le dit ;
      * le fichier existe DEJA et contient deja le serveur -> on ne touche a rien ;
      * le fichier existe et ne contient pas le serveur -> on n'ecrit PAS. On rend le
        fragment a coller, avec le fichier et le nom de la cle. Reecrire la configuration
        de quelqu'un d'autre pour lui rendre service est exactement le comportement que ce
        projet reproche aux agents.
    """
    connu = {nom: rel for nom, rel, _ in DIALECTES}
    if dialecte not in connu:
        raise ValueError(f"dialecte inconnu : {dialecte}")

    rel = connu[dialecte]
    if rel is None:
        return False, _contenu(dialecte)

    chemin = racine / rel
    if chemin.exists():
        texte = chemin.read_text(encoding="utf-8", errors="replace")
        # Le serveur est-il deja branche ? On cherche le nom, pas une chaine exacte : une
        # config reformatee a la main reste une config branchee.
        deja = f'"{NOM_SERVEUR}"' in texte
        return False, (
            f"{rel} existe deja et contient deja `{NOM_SERVEUR}` : rien a faire."
            if deja
            else (
                f"{rel} existe deja : NON MODIFIE.\n"
                f"Ajouter sous la cle `mcp` de ce fichier :\n\n{_contenu(dialecte)}"
            )
        )
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(_contenu(dialecte), encoding="utf-8")
    return True, f"{rel} cree — le serveur `{NOM_SERVEUR}` est branche."


def prouver_branchement(commande: Sequence[str] = _COMMANDE, delai: float = 20.0) -> str:
    """Demarre le serveur MCP et lui parle vraiment (initialize + tools/list).

    Pourquoi ce n'est pas une precaution theorique : les fragments ci-dessus nomment
    `python3 -m jio.mcp_server`. Si `jio` a ete installe dans un environnement virtuel qui
    n'est pas active, cette commande EXISTE et ne trouve RIEN — la configuration est
    correcte, la branche ne l'est pas, et rien ne le dit avant la premiere mission. On
    lance donc reellement le serveur, on compte les outils qu'il annonce, et on rapporte
    la sortie d'erreur sinon.

    Rend un texte a afficher ; ne lève jamais : un diagnostic qui plante ne diagnostique
    rien.
    """
    import json
    import subprocess
    import sys

    requetes = (
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}),
    )
    try:
        processus = subprocess.run(
            list(commande),
            input="\n".join(requetes) + "\n",
            capture_output=True, text=True, timeout=delai, check=False,
        )
    except FileNotFoundError:
        return (
            f"  ECHEC : `{commande[0]}` est INTROUVABLE sur cette machine.\n"
            "  C'est exactement le defaut que cette sonde existe pour attraper : une\n"
            "  configuration correcte qui ne branche rien."
        )
    except subprocess.TimeoutExpired:
        return f"  ECHEC : le serveur n'a pas repondu en {delai:.0f}s (lancement bloque)."

    outils: list[str] = []
    serveur = ""
    for ligne in processus.stdout.splitlines():
        ligne = ligne.strip()
        if not ligne.startswith("{"):
            continue
        try:
            reponse = json.loads(ligne)
        except json.JSONDecodeError:
            continue
        resultat = reponse.get("result") or {}
        if "serverInfo" in resultat:
            serveur = str(resultat["serverInfo"].get("version", ""))
        for outil in resultat.get("tools", []):
            outils.append(str(outil.get("name", "?")))

    if not outils:
        detail = (processus.stderr or processus.stdout or "").strip().splitlines()
        return (
            f"  ECHEC : `{' '.join(commande)}` ne sert AUCUN outil.\n"
            + "\n".join(f"    {ligne[:160]}" for ligne in detail[-5:])
        )

    return (
        f"  `{' '.join(commande)}` sert {len(outils)} outil(s) [version {serveur}] :\n"
        + "\n".join(f"    - {nom}" for nom in outils)
        + f"\n  (interpreteur de cette sonde : {sys.executable})"
    )
