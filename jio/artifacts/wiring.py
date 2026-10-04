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
#: Identifiants des deux requetes JSON-RPC de la sonde. Ils doivent etre DISTINCTS : un
#: identifiant sert a apparier une reponse a SA requete, et deux requetes en vol portant le
#: meme identifiant rendent les reponses indiscernables. `jio mutants` a montre que ce `1`
#: pouvait devenir `2` en silence : deux identifiants egaux ne cassaient rien ici
#: (la sonde lit tout ce qui sort), mais c'etait une propriete tenue par accident.
ID_INITIALIZE = 1
ID_TOOLS_LIST = 2

NOM_SERVEUR = "jio"

#: L'outil est recherche comme module Python (`python3 -m jio.mcp_server`), sans dependre du
#: PATH ni d'un chemin ABSOLU DE DEPOT : un chemin de depot copie dans une configuration ne
#: survit pas au deplacement du depot.
#:
#: CE QUE CETTE LIGNE NE DISAIT PAS, et qui a ete mesure sur un projet ETRANGER : `python3`
#: resout `jio` par le DOSSIER COURANT. Dans le depot JIO — ou `jio/` est un sous-dossier —
#: la commande marche par accident ; dans un projet sans paquet `jio`, elle existe et ne sert
#: RIEN. La sonde du branchement le disait (« ne sert AUCUN outil »), mais la configuration
#: etait ecrite AVANT la sonde, donc le diagnostic arrivait apres la panne. La commande est
#: desormais RESOLUE par la sonde, et c'est la commande qui marche qui est ecrite.
_COMMANDE = ("python3", "-m", "jio.mcp_server")


def _candidats() -> list[tuple[str, ...]]:
    """Les commandes essayees, dans l'ordre : la plus portable d'abord.

    `sys.executable` vient en second parce qu'il est un chemin absolu d'INTERPRETEUR — pas de
    depot : il ne bouge pas quand le projet bouge, et il est forcement l'interpreteur qui a
    servi a lancer JIO, donc celui pour qui `jio` est importable.
    """
    import sys

    candidats: list[tuple[str, ...]] = [_COMMANDE]
    if sys.executable and sys.executable != "python3":
        candidats.append((sys.executable, "-m", "jio.mcp_server"))
    return candidats


def _parler_au_serveur(commande: Sequence[str], delai: float,
                       racine: Path | None = None) -> tuple[list[str], str, str]:
    """Demarre le serveur et lui parle vraiment. Rend (outils, version, detail d'echec)."""
    import json
    import subprocess

    requetes = (
        json.dumps({"jsonrpc": "2.0", "id": ID_INITIALIZE, "method": "initialize", "params": {}}),
        json.dumps({"jsonrpc": "2.0", "id": ID_TOOLS_LIST, "method": "tools/list", "params": {}}),
    )
    try:
        processus = subprocess.run(
            list(commande),
            input="\n".join(requetes) + "\n",
            capture_output=True, text=True, timeout=delai, check=False,
            cwd=str(racine) if racine else None,
        )
    except FileNotFoundError:
        return [], "", f"`{commande[0]}` est INTROUVABLE sur cette machine"
    except subprocess.TimeoutExpired:
        return [], "", f"le serveur n'a pas repondu en {delai:.0f}s (lancement bloque)"

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
    if outils:
        return outils, serveur, ""
    detail = (processus.stderr or processus.stdout or "").strip().splitlines()
    return [], "", "\n".join(ligne[:160] for ligne in detail[-5:])


def _prog(commande: Sequence[str] | None) -> str:
    """Le nom du programme d'une commande, pour les dialectes en TEXTE (YAML, TOML)."""
    return (commande or _COMMANDE)[0]


def _args_toml(commande: Sequence[str] | None) -> str:
    """Les arguments, au format tableau TOML/YAML — echappes pour ne pas casser la syntaxe."""
    return "[" + ", ".join(json.dumps(a) for a in (commande or _COMMANDE)[1:]) + "]"


def commande_qui_marche(*, racine: Path | None = None,
                        delai: float = 20.0) -> tuple[tuple[str, ...], str]:
    """La commande a ECRIRE dans les configurations : la premiere qui sert des outils.

    Rend `(commande, note)`. La note est vide quand la commande par defaut suffit — c'est le
    cas dans le depot JIO, ou la configuration generee ne doit donc pas changer d'un octet.
    Elle dit, sinon, ce qui a ete essaye et pourquoi la commande par defaut a ete ecartee :
    un remplacement silencieux serait un remplacement qu'on ne peut pas auditer.

    `racine` : le projet DEPUIS LEQUEL le serveur sera lance. C'est le point de tout ce
    module, et la deuxieme version de cette fonction a du le corriger : interrogee depuis le
    depot JIO — ou `jio/` est un sous-dossier du dossier courant — `python3 -m jio.mcp_server`
    « marche », donc la sonde declarait la commande par defaut valide et ecrivait dans un
    projet ETRANGER une configuration qui n'y sert rien. Une sonde qui mesure dans un autre
    contexte que le contexte d'usage mesure autre chose que ce qu'elle pretend.
    """
    essais: list[str] = []
    for commande in _candidats():
        outils, _, detail = _parler_au_serveur(commande, delai, racine)
        if outils:
            if commande == _COMMANDE:
                return _COMMANDE, ""
            return commande, (
                f"`{' '.join(_COMMANDE)}` ne sert aucun outil ici ("
                + (detail.splitlines()[0] if detail else "aucun outil annonce")
                + f") ; la configuration ecrit donc `{' '.join(commande)}`, verifie en direct."
            )
        essais.append(f"{' '.join(commande)} ({detail.splitlines()[0] if detail else 'rien'})")
    return _COMMANDE, "aucune commande n'a servi d'outil : " + " ; ".join(essais)


def fragment_opencode(commande: Sequence[str] | None = None) -> dict[str, object]:
    """Bloc `mcp` de `opencode.json` (schema opencode.ai).

    `enabled: true` est explicite : un serveur present mais desactive serait un cablage
    qui ne fait rien, ce qui est exactement le defaut que ce module corrige.
    """
    return {
        "mcp": {
            NOM_SERVEUR: {
                "type": "local",
                "command": list(commande or _COMMANDE),
                "enabled": True,
                "environment": {"JIO_ROOT": "."},
            }
        }
    }


def fragment_hermes(commande: Sequence[str] | None = None) -> str:
    """Bloc YAML `mcp_servers` de `~/.hermes/config.yaml`.

    Rend du TEXTE : on ne peut pas fusionner un YAML sans charger puis reecrire le fichier
    de l'utilisateur, donc on n'essaie pas. L'humain colle, et JIO lui dit ou.
    """
    return (
        "# Ajouter sous la cle de premier niveau `mcp_servers` de\n"
        "# ~/.hermes/config.yaml, puis `/reload-mcp` dans une session :\n"
        "mcp_servers:\n"
        f"  {NOM_SERVEUR}:\n"
        f'    command: "{_prog(commande)}"\n'
        f"    args: {_args_toml(commande)}\n"
        "    env:\n"
        '      JIO_ROOT: "${JIO_ROOT}"\n'
    )


def fragment_codex(commande: Sequence[str] | None = None) -> str:
    """Bloc TOML `[mcp_servers.jio]` de `~/.codex/config.toml`."""
    return (
        "# Ajouter a ~/.codex/config.toml :\n"
        f"[mcp_servers.{NOM_SERVEUR}]\n"
        f'command = "{_prog(commande)}"\n'
        f"args = {_args_toml(commande)}\n"
    )


def fragment_claude_code(commande: Sequence[str] | None = None) -> str:
    """`claude mcp add` — la CLI ecrit la config elle-meme, on donne la commande."""
    return (
        "# Ajouter le serveur avec la CLI (elle ecrit la configuration) :\n"
        f"claude mcp add {NOM_SERVEUR} -- {' '.join(commande or _COMMANDE)}\n"
    )


def fragment_cursor(commande: Sequence[str] | None = None) -> str:
    """Bloc `mcpServers` de `.cursor/mcp.json` (ou ~/.cursor/mcp.json)."""
    return json.dumps(
        {"mcpServers": {NOM_SERVEUR: {"command": (commande or _COMMANDE)[0],
                                      "args": list((commande or _COMMANDE)[1:])}}},
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


def _contenu(dialecte: str, commande: Sequence[str] | None = None) -> str:
    """Le fragment d'un dialecte, en texte pret a coller."""
    if dialecte == "opencode":
        return json.dumps(fragment_opencode(commande), indent=2, ensure_ascii=False) + "\n"
    return {
        "hermes": fragment_hermes,
        "codex": fragment_codex,
        "claude-code": fragment_claude_code,
        "cursor": fragment_cursor,
    }[dialecte](commande)


def fragments(commande: Sequence[str] | None = None) -> dict[str, str]:
    """Tous les fragments, dans l'ordre de `DIALECTES`."""
    return {nom: _contenu(nom, commande) for nom, _, _ in DIALECTES}


def brancher(racine: Path, dialecte: str = "opencode", *,
             commande: Sequence[str] | None = None) -> tuple[bool, str]:
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
    chemin.write_text(_contenu(dialecte, commande), encoding="utf-8")
    return True, f"{rel} cree — le serveur `{NOM_SERVEUR}` est branche."


def _rapport_de_sonde(commande: Sequence[str], delai: float, note: str,
                      racine: Path | None = None) -> str:
    """Le texte de la preuve : ce que la commande sert VRAIMENT, et d'ou elle vient."""
    import sys

    outils, serveur, detail = _parler_au_serveur(commande, delai, racine)
    if not outils:
        return (
            f"  ECHEC : `{' '.join(commande)}` ne sert AUCUN outil.\n"
            + "\n".join(f"    {ligne[:160]}" for ligne in detail.splitlines()[-5:])
        )
    lignes = [
        f"  `{' '.join(commande)}` sert {len(outils)} outil(s) [version {serveur}] :",
        *(f"    - {nom}" for nom in outils),
        f"  (interpreteur de cette sonde : {sys.executable})",
    ]
    if note:
        lignes.append(f"  NOTE : {note}")
    return "\n".join(lignes)


def prouver_branchement(commande: Sequence[str] | None = None, delai: float = 20.0,
                        racine: Path | None = None) -> str:
    """Demarre le serveur MCP et lui parle vraiment (initialize + tools/list).

    Pourquoi ce n'est pas une precaution theorique : les fragments nomment
    `python3 -m jio.mcp_server`. Sur un projet SANS paquet `jio`, cette commande existe et ne
    sert RIEN — la configuration est correcte, la branche ne l'est pas, et rien ne le dit avant
    la premiere mission. On lance donc reellement le serveur, on compte les outils qu'il
    annonce, et on rapporte la sortie d'erreur sinon.

    Sans `commande`, la sonde RESOUT : elle essaie les candidats et rend la preuve de celui qui
    marche, avec la note qui dit pourquoi la commande par defaut a ete ecartee. Rendre un
    diagnostic juste sur une configuration qu'on vient d'ecrire fausse serait une drole de
    preuve.

    Rend un texte a afficher ; ne lève jamais : un diagnostic qui plante ne diagnostique rien.
    """
    if commande is None:
        resolue, note = commande_qui_marche(racine=racine, delai=delai)
        return _rapport_de_sonde(resolue, delai, note, racine)
    return _rapport_de_sonde(commande, delai, "", racine)

