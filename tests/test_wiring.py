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
    # Le nombre est LU dans la source, jamais recopie : un 5 ecrit a la main a fait echouer ce
    # test des qu'un outil a ete ajoute — alors que le serveur, lui, allait tres bien. Le
    # controle porte sur le PROTOCOLE (le serveur sert ce qu'il annonce), pas sur un compte.
    from jio.mcp_server import TOOLS

    servis = [outil["name"] for outil in reponses[1]["result"]["tools"]]
    assert servis == [outil["name"] for outil in TOOLS]
    assert len(servis) >= 5

def test_le_fragment_opencode_ACTIVE_le_serveur_explicitement() -> None:
    """`enabled: true` : un serveur cable mais DESACTIVE serait un cablage qui ne fait rien.

    Mesure a l'origine : `jio mutants` a montre que ce `True` pouvait devenir `False` sans
    qu'aucun test ne bouge. Le fichier aurait ete ecrit, la sonde aurait meme pu le lire,
    et aucun agent n'aurait jamais vu l'outil : le pire des deux mondes — un cablage cru
    fait qui ne sert rien.
    """
    bloc = fragment_opencode()["mcp"][NOM_SERVEUR]
    assert bloc["enabled"] is True
    assert bloc["type"] == "local"
    assert bloc["command"]
    assert bloc["environment"] == {"JIO_ROOT": "."}


def test_le_fragment_cursor_est_INDENTE_et_garde_les_accents() -> None:
    """Le JSON ecrit pour Cursor est lisible par un humain et n'echappe pas les accents.

    Mesure a l'origine : `jio mutants` a montre que `indent=2` pouvait disparaitre et que
    `ensure_ascii=False` pouvait passer a `True` sans qu'aucun test ne bouge. Le fichier
    restait valide : la perte etait invisible — un pavé d'une ligne illisible dans un
    depot, et des `\\u00e9` dans un fichier de configuration destine a etre relu a la main.
    """
    from jio.artifacts.wiring import fragment_cursor

    texte = fragment_cursor()
    assert json.loads(texte)["mcpServers"][NOM_SERVEUR]["command"] == "python3"
    assert "\n  \"mcpServers\"" in texte, "indent=2 attendu : sinon le fichier est illisible"
    assert "\\u" not in texte, "ensure_ascii=False attendu : les accents restent lisibles"
    assert texte.endswith("\n")


def test_la_taille_maximale_de_source_est_declaree_et_respectee() -> None:
    """`MAX_SOURCE = 200_000` : au-dela on REFUSE, on ne rame pas.

    Mesure a l'origine : `jio mutants` a montre que cette borne pouvait passer a 200 001
    sans qu'aucun test ne bouge. Une borne qui glisse en silence n'est plus une borne.
    """
    from jio.mcp_server import MAX_SOURCE, handle

    assert MAX_SOURCE == 200_000

    def refus(source: str) -> str:
        reponse = handle({
            "jsonrpc": "2.0", "id": 1, "method": "tools/call",
            "params": {"name": "jio_prove",
                       "arguments": {"source": source, "checks": {"R-1": "assert True"}}},
        })
        assert reponse is not None
        resultat = reponse.get("result") or {}
        contenu = resultat.get("content") or [{}]
        return str(contenu[0].get("text", ""))

    assert refus("x = 1") .startswith("REFUS : aucune regle") is False  # une regle est fournie
    assert refus("x" * (MAX_SOURCE + 1)).startswith("REFUS : source trop longue")
    # exactement a la borne : ce n'est PAS un refus de taille
    assert not refus("x" * MAX_SOURCE).startswith("REFUS : source trop longue")

def test_les_deux_requetes_de_la_sonde_ont_des_identifiants_DISTINCTS() -> None:
    """Deux requetes JSON-RPC en vol ne portent jamais le meme identifiant.

    Mesure a l'origine : `jio mutants` a montre que ce `1` pouvait devenir `2` sans qu'aucun
    test ne bouge — les deux requetes de la sonde (`initialize` puis `tools/list`) auraient
    alors porte le MEME identifiant. La sonde continuait de marcher par chance (elle lit
    toute la sortie sans apparier), mais la propriete du protocole etait tenue par accident,
    et une sonde qui n'apparie pas les reponses a ses requetes est exactement le genre
    d'outil qui annonce « tout va bien » sur la reponse d'un autre.
    """
    from jio.artifacts.wiring import ID_INITIALIZE, ID_TOOLS_LIST

    assert ID_INITIALIZE != ID_TOOLS_LIST
    assert (ID_INITIALIZE, ID_TOOLS_LIST) == (1, 2)


def test_le_fragment_cursor_lance_la_MEME_commande_que_le_serveur() -> None:
    """`list(_COMMANDE[1:])` : le fragment Cursor lance le module, pas autre chose.

    Mesure a l'origine : `jio mutants` a montre que ce `[1:]` pouvait devenir `[2:]` sans
    qu'aucun test ne bouge. Le fichier de configuration aurait alors annonce `python3 <args
    sans -m>` : une commande qui ne lance rien, ecrite dans le fichier que Cursor lit
    vraiment — le cablage mort que tout ce module existe pour empecher.
    """
    from jio.artifacts.wiring import fragment_cursor

    config = json.loads(fragment_cursor())["mcpServers"][NOM_SERVEUR]
    assert config["args"] == list(_COMMANDE[1:])
    assert config["args"] and config["args"][0] == "-m"
    assert config["command"] == _COMMANDE[0]


# --------------------------------------------------------------------------- #
# `jio mcp` : un chemin qui sort en 0 sans rien produire n'est pas un succes
# --------------------------------------------------------------------------- #


def test_jio_mcp_dans_un_TERMINAL_montre_ce_qu_il_sert_au_lieu_de_bloquer(monkeypatch, capsys):
    """Un humain qui tape `jio mcp` ne doit pas voir une commande muette qui attend.

    `jio mcp` sans argument LANCE un serveur JSON-RPC sur son entree standard. Dans un terminal,
    il n'y a personne pour envoyer du JSON : la commande attendait indéfiniment, puis rendait 0
    sans un mot. Un chemin qui sort en 0 sans rien produire est indistinguable d'un succes —
    c'est exactement ce que ce depot refuse partout ailleurs.

    Comportement retenu : quand l'entree standard est un TERMINAL, `jio mcp` montre ce que le
    serveur sert (la meme chose que `--list`) et DIT pourquoi il ne demarre pas ici.
    """
    import io
    import sys as _sys

    from jio.cli import main

    class _Terminal(io.StringIO):
        def isatty(self) -> bool:            # noqa: D102 — ce que le vrai terminal repond
            return True

    monkeypatch.setattr(_sys, "stdin", _Terminal(""))
    code = main(["mcp"])

    assert code == 0
    sortie = capsys.readouterr().out
    assert "SERVEUR MCP JIO" in sortie
    assert "demarre un SERVEUR" in sortie
    assert "jio mcp --prove" in sortie
    # Les outils exposes sont LISTES, pas resumés : c'est cette liste qui dit a l'utilisateur
    # ce qu'il vient de cabler.
    from jio.mcp_server import TOOLS

    for outil in TOOLS:
        assert outil["name"] in sortie, outil["name"]


def test_une_session_MCP_sans_aucun_message_le_DIT_sur_la_sortie_d_erreur(monkeypatch, capsys):
    """Zero message traite n'est pas « tout s'est bien passe » : c'est un silence, et il se dit.

    Mesure a l'origine : `jio mcp < /dev/null` sortait en 0 avec une sortie VIDE. Un client mal
    configure — celui qui ouvre le serveur sans jamais lui parler — obtenait exactement la meme
    chose qu'un client a qui tout a ete repondu. La sortie d'erreur n'est pas le canal du
    protocole : y ecrire ne peut pas corrompre un echange en cours.
    """
    import io
    import sys as _sys

    from jio.mcp_server import main as mcp_main

    monkeypatch.setattr(_sys, "stdin", io.StringIO(""))
    assert mcp_main() == 0
    capture = capsys.readouterr()
    assert capture.out == "", "rien ne doit sortir sur le canal du protocole"
    assert "aucun message recu" in capture.err
    assert "jio mcp --prove" in capture.err


def test_une_session_MCP_avec_un_message_ne_dit_RIEN_sur_la_sortie_d_erreur(monkeypatch, capsys):
    """Le bruit ne doit apparaitre que dans le cas vide : sinon il pollue un vrai client.

    C'est l'autre bord du test precedent, et il compte autant : un avertissement emis a chaque
    session ferait ignorer l'avertissement qui compte.
    """
    import io
    import json as _json
    import sys as _sys

    from jio.mcp_server import main as mcp_main

    requete = _json.dumps({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
    monkeypatch.setattr(_sys, "stdin", io.StringIO(requete + "\n"))
    assert mcp_main() == 0
    capture = capsys.readouterr()
    assert "aucun message recu" not in capture.err
    assert "tools" in capture.out
