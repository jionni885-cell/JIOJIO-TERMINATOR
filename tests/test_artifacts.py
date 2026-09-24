"""Tests des artefacts natifs et du serveur MCP.

Ce qui est verrouille ici :
  * une seule doctrine, plusieurs dialectes (pas de divergence entre outils) ;
  * AGENTS.md reste court (au-dela de ~150 lignes il est survole, pas lu) ;
  * le verificateur n'a jamais le droit d'ecrire (un verificateur qui peut
    modifier l'artefact qu'il juge finit par le rendre conforme) ;
  * chaque competence a une section de verification capable d'echouer ;
  * le serveur MCP respecte son contrat et confine les chemins.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from jio.artifacts import TARGETS, manifest, write_manifest
from jio.artifacts.definitions import AGENTS, SKILLS
from jio.mcp_server import TOOLS, handle

# --------------------------------------------------------------------------- #
# Manifeste
# --------------------------------------------------------------------------- #


def test_manifest_couvre_toutes_les_cibles():
    files = manifest()
    assert len(files) >= 20
    for target in TARGETS:
        assert manifest((target,)), f"cible vide : {target}"


def test_cible_inconnue_refusee():
    with pytest.raises(ValueError):
        manifest(("bidon",))


def test_agents_md_reste_court():
    """Au-dela de ~150 lignes, un fichier de contexte est survole et non lu."""
    content = manifest(("agents",))["AGENTS.md"]
    assert len(content.splitlines()) <= 150


def test_write_manifest_ecrit_vraiment(tmp_path: Path):
    written = write_manifest(tmp_path, ("claude",))
    assert written and all(p.exists() for p in written)
    assert (tmp_path / "CLAUDE.md").read_text(encoding="utf-8").startswith("#")


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #


def test_chaque_agent_opencode_a_un_frontmatter_complet():
    files = manifest(("opencode",))
    for agent in AGENTS:
        text = files[f".opencode/agents/{agent.name}.md"]
        assert text.startswith("---\n")
        header = text.split("---")[1]
        for field in ("description:", "mode:", "temperature:", "steps:", "permission:"):
            assert field in header, f"{agent.name} sans {field}"


def test_verificateur_ne_peut_pas_ecrire():
    """Garde-fou structurel : sans lui, le verificateur repare ce qu'il juge."""
    text = manifest(("opencode",))[".opencode/agents/jio-verifier.md"]
    assert "edit: deny" in text
    assert "edit: allow" not in text


def test_jio_est_un_agent_principal():
    jio = next(a for a in AGENTS if a.name == "jio")
    assert jio.mode == "primary"
    assert "DELIVERED" in jio.prompt and "ABSTAINED" in jio.prompt


# --------------------------------------------------------------------------- #
# Competences Hermes
# --------------------------------------------------------------------------- #


def test_chaque_competence_a_un_frontmatter_hermes_valide():
    files = manifest(("hermes",))
    for skill in SKILLS:
        text = files[f".hermes/skills/{skill.category}/{skill.name}/SKILL.md"]
        assert text.startswith("---\n")
        for field in ("name:", "description:", "version:", "platforms:"):
            assert field in text[:400], f"{skill.name} sans {field}"


def test_chaque_competence_decrit_quand_l_utiliser_et_comment_verifier():
    """Une competence sans section de verification capable d'echouer est decorative."""
    for skill in SKILLS:
        assert "## When to Use" in skill.body, skill.name
        assert "## Procedure" in skill.body, skill.name
        assert "## Pitfalls" in skill.body, skill.name
        assert "## Verification" in skill.body, skill.name


def test_budget_de_skills_respecte():
    """Mesure de terrain : 5 000 tokens par competence, 25 000 au total (approche
    par les caracteres : ~4 caracteres par token en anglais)."""
    total = sum(len(s.body) for s in SKILLS)
    assert total < 25_000 * 4
    assert max(len(s.body) for s in SKILLS) < 5_000 * 4


def test_noms_de_competences_uniques():
    names = [s.name for s in SKILLS]
    assert len(names) == len(set(names))


# --------------------------------------------------------------------------- #
# Serveur MCP
# --------------------------------------------------------------------------- #


def test_initialize_repond_conformement_au_protocole():
    out = handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert out is not None
    result = out["result"]
    assert result["protocolVersion"]
    assert result["serverInfo"]["name"] == "jio"
    assert "tools" in result["capabilities"]


def test_tools_list_expose_les_quatre_outils():
    out = handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    names = {t["name"] for t in out["result"]["tools"]}
    assert names == {t["name"] for t in TOOLS}
    assert "jio_prove" in names and "jio_audit" in names


def test_notification_ne_recoit_pas_de_reponse():
    """Sans `id`, le protocole interdit toute reponse."""
    assert handle({"jsonrpc": "2.0", "method": "tools/list"}) is None


def test_methode_inconnue_renvoie_une_erreur_jsonrpc():
    out = handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})
    assert out["error"]["code"] == -32601


def test_prove_rend_un_verdict_par_regle():
    out = handle(
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {
                "name": "jio_prove",
                "arguments": {
                    "source": "def f(n):\n    return n * 2\n",
                    "checks": {"R-1": "assert f(2) == 4", "R-2": "assert f(2) == 5"},
                },
            },
        }
    )
    text = out["result"]["content"][0]["text"]
    assert "R-1" in text and "R-2" in text
    assert "NON CONFORME" in text
    assert out["result"]["isError"] is False


def test_prove_refuse_une_preuve_sans_regle():
    out = handle(
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "jio_prove", "arguments": {"source": "x = 1", "checks": {}}},
        }
    )
    assert "REFUS" in out["result"]["content"][0]["text"]


def test_audit_confine_les_chemins():
    """Un serveur d'outils qui lit n'importe quel chemin est une vulnerabilite."""
    out = handle(
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "jio_audit", "arguments": {"path": "../../../etc/passwd"}},
        }
    )
    assert "REFUS" in out["result"]["content"][0]["text"]


def test_audit_d_un_fichier_du_depot_fonctionne():
    out = handle(
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {
                "name": "jio_audit",
                "arguments": {"path": "jio/verify/entropy.py"},
            },
        }
    )
    text = out["result"]["content"][0]["text"]
    assert "AUDIT" in text
    assert "VERDICT" in text


def test_outil_inconnu_renvoie_une_erreur_propre():
    out = handle(
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "jio_bidon", "arguments": {}},
        }
    )
    assert out.get("error", {}).get("code") == -32602


def test_contract_renvoie_la_doctrine():
    out = handle(
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "jio_contract", "arguments": {}},
        }
    )
    text = out["result"]["content"][0]["text"]
    assert "DELIVERED" in text and "ABSTAINED" in text
