"""Le cablage du serveur MCP : la difference entre « ecrit » et « branche ».

Le serveur existait, etait teste, et restait **injoignable** depuis opencode et Hermes :
`.mcp.json` est le dialecte de Claude Code, opencode lit `opencode.json` sous la cle `mcp`
avec `type: "local"` et un tableau `command`, Hermes lit `~/.hermes/config.yaml` sous la
cle `mcp_servers`. Les deux formats sont ceux documentes par les outils, pas une
interpretation.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from jio.artifacts.wiring import (
    DIALECTES,
    NOM_SERVEUR,
    _COMMANDE,
    brancher,
    fragment_hermes,
    fragment_opencode,
    fragments,
    prouver_branchement,
)

REPO = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------- #
# 1. Les fragments : conformes au format de CHAQUE outil
# --------------------------------------------------------------------------- #


def test_le_fragment_opencode_respecte_le_schema_documente() -> None:
    """opencode : `mcp.<nom>` avec `type: "local"` et un TABLEAU `command`."""
    bloc = fragment_opencode()["mcp"][NOM_SERVEUR]

    assert bloc["type"] == "local"
    assert isinstance(bloc["command"], list), "opencode exige un tableau, pas une chaine"
    assert bloc["command"] == list(_COMMANDE)
    assert bloc["enabled"] is True, "un serveur desactive est un cablage qui ne fait rien"


def test_le_fragment_hermes_est_du_yaml_sous_la_bonne_cle() -> None:
    """Hermes : `mcp_servers:` (et non `mcp`), command et args separes."""
    texte = fragment_hermes()

    assert "mcp_servers:" in texte
    assert NOM_SERVEUR in texte
    assert 'command: "python3"' in texte
    assert 'args: ["-m", "jio.mcp_server"]' in texte


def test_tous_les_dialectes_emettent_la_meme_commande() -> None:
    """Une seule source pour la commande : sinon les outils divergeraient en silence."""
    for nom, texte in fragments().items():
        assert "jio.mcp_server" in texte, f"{nom} ne lance pas le serveur JIO"


def test_les_dialectes_declares_sont_tous_emissibles() -> None:
    """`DIALECTES` sert a l'aide et au routage : une entree sans fragment serait un 500."""
    emis = fragments()
    for nom, _, description in DIALECTES:
        assert nom in emis, f"{nom} est annonce mais ne s'emet pas ({description})"


# --------------------------------------------------------------------------- #
# 2. On ne modifie JAMAIS la configuration de l'utilisateur
# --------------------------------------------------------------------------- #


def test_une_racine_vierge_est_cablee(tmp_path: Path) -> None:
    ecrit, message = brancher(tmp_path, "opencode")

    assert ecrit is True
    assert "cree" in message
    config = json.loads((tmp_path / "opencode.json").read_text(encoding="utf-8"))
    assert config["mcp"][NOM_SERVEUR]["command"] == list(_COMMANDE)


def test_un_fichier_deja_cable_nest_pas_reecrit(tmp_path: Path) -> None:
    """Deuxieme execution : rien a faire, et le dire."""
    brancher(tmp_path, "opencode")
    contenu = (tmp_path / "opencode.json").read_text(encoding="utf-8")
    (tmp_path / "opencode.json").write_text(
        contenu.replace('"enabled": true', '"enabled": true').replace(
            "  }\n}", '  },\n  "theme": "sombre"\n}'
        ),
        encoding="utf-8",
    )
    retouche = (tmp_path / "opencode.json").read_text(encoding="utf-8")

    ecrit, message = brancher(tmp_path, "opencode")

    assert ecrit is False
    assert "rien a faire" in message
    assert (tmp_path / "opencode.json").read_text(encoding="utf-8") == retouche, (
        "une config deja cablée ne doit pas etre reecrite : l'utilisateur y met ses reglages"
    )


def test_une_config_existante_sans_jio_est_LAISSEE_INTACTE(tmp_path: Path) -> None:
    """Le cas qui compte : l'utilisateur a deja ses serveurs MCP.

    On ne fusionne pas en silence — on rend le fragment a coller. Reecrire la
    configuration de quelqu'un d'autre pour lui rendre service est exactement le
    comportement que ce projet reproche aux agents.
    """
    originel = '{\n  "mcp": { "autre": { "type": "local", "command": ["x"] } }\n}\n'
    (tmp_path / "opencode.json").write_text(originel, encoding="utf-8")

    ecrit, message = brancher(tmp_path, "opencode")

    assert ecrit is False
    assert "NON MODIFIE" in message
    assert NOM_SERVEUR in message, "le fragment doit etre affiche, pas seulement refuse"
    assert (tmp_path / "opencode.json").read_text(encoding="utf-8") == originel


def test_hermes_necrit_aucun_fichier_mais_rend_le_fragment(tmp_path: Path) -> None:
    """Hermes : la config est un YAML de l'utilisateur, on n'y touche pas."""
    ecrit, message = brancher(tmp_path, "hermes")

    assert ecrit is False
    assert "mcp_servers" in message
    assert list(tmp_path.iterdir()) == [], "aucun fichier ne doit apparaitre"


def test_un_dialecte_inconnu_leve() -> None:
    with pytest.raises(ValueError):
        brancher(Path("."), "outil-imaginaire")


# --------------------------------------------------------------------------- #
# 3. La preuve du branchement : une config peut exister et ne rien cabler
# --------------------------------------------------------------------------- #


def test_la_sonde_compte_les_outils_du_serveur() -> None:
    """`prouver_branchement` parle vraiment au serveur (initialize + tools/list).

    Un test qui se contente de verifier que la commande existe passerait alors que rien
    ne fonctionne : c'est le defaut vise.
    """
    if not (REPO / "jio" / "mcp_server.py").is_file():
        pytest.skip("serveur absent")
    rapport = prouver_branchement((sys.executable, "-m", "jio.mcp_server"), delai=30.0)

    assert "ECHEC" not in rapport, rapport
    for outil in ("jio_prove", "jio_audit", "jio_contract", "jio_claims", "jio_skills"):
        assert outil in rapport, rapport


def test_la_sonde_detecte_une_commande_qui_ne_sert_rien() -> None:
    """Le cas reel : `python3` existe, mais `jio` n'y est pas installe."""
    rapport = prouver_branchement((sys.executable, "-c", "pass"), delai=30.0)

    assert "ECHEC" in rapport
    assert "AUCUN outil" in rapport


def test_la_sonde_ne_plante_jamais() -> None:
    """Un diagnostic qui plante ne diagnostique rien."""
    rapport = prouver_branchement(("/binaire/qui/nexiste/pas",), delai=5.0)

    assert "ECHEC" in rapport
    assert "INTROUVABLE" in rapport


def test_le_serveur_repond_au_protocole_utilise_par_la_sonde() -> None:
    """Verrouille le transport : deux requetes JSON-RPC sur stdin, deux reponses."""
    requetes = (
        '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}\n'
        '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}\n'
    )
    resultat = subprocess.run(
        [sys.executable, "-m", "jio.mcp_server"],
        input=requetes, capture_output=True, text=True, timeout=60, check=False,
        cwd=REPO,
    )
    reponses = [json.loads(l) for l in resultat.stdout.splitlines() if l.strip()]
    assert [r["id"] for r in reponses] == [1, 2]
    assert reponses[0]["result"]["serverInfo"]["name"] == "jio"
    assert len(reponses[1]["result"]["tools"]) == 5
