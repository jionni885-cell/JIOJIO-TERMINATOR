"""Export OTLP : des spans relies, des metriques normalisees, aucun secret par defaut.

Ce que ces tests fixent :

1. chaque evenement devient un span, chaine du precedent par `parentSpanId` — c'est ce
   qui permet de lire une mission comme un arbre et pas comme une liste ;
2. le mode par defaut n'exporte AUCUN payload : seules les metadonnees sortent ;
3. quand le contenu est demande, il passe par la redaction ; `redact=False` est le seul
   chemin qui laisse passer un secret, et il doit etre explicite ;
4. les attributs suivent les conventions GenAI la ou elles s'appliquent (`gen_ai.*`),
   notamment pour le modele et les jetons ;
5. l'ecriture locale ne remplace pas un fichier existant sans le dire, et l'envoi HTTP
   exige un endpoint explicitement fourni.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jio.core.journal import Journal
from jio.telemetry.otlp import (
    OTLPExportError,
    otlp_trace_payload,
    send_otlp_http,
    write_otlp_json,
)

SECRET = "sk-live-0123456789abcdefghijklmnop"


def _journal() -> Journal:
    journal = Journal()
    journal.append("mission", {"objective": "contacter le service"})
    journal.append(
        "provider",
        {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "api_key": SECRET,
            "usage": {"input_tokens": 120, "output_tokens": 45},
        },
    )
    journal.append("witness", {"rule": "R-001", "ok": True, "exit_code": 0})
    return journal


def _spans(payload: dict) -> list[dict]:
    return payload["resourceSpans"][0]["scopeSpans"][0]["spans"]


def test_chaque_evenement_devient_un_span_relie_au_precedent() -> None:
    payload = otlp_trace_payload(_journal())
    spans = _spans(payload)

    assert len(spans) == 3
    assert [span["name"] for span in spans] == ["mission", "provider", "witness"]
    assert "parentSpanId" not in spans[0], "la racine n'a pas de parent"
    assert spans[1]["parentSpanId"] == spans[0]["spanId"]
    assert spans[2]["parentSpanId"] == spans[1]["spanId"]
    assert len({span["traceId"] for span in spans}) == 1, "une mission, une trace"
    assert all(len(span["spanId"]) == 16 and len(span["traceId"]) == 32 for span in spans)


def test_le_mode_par_defaut_n_exporte_AUCUN_payload() -> None:
    payload = otlp_trace_payload(_journal())
    texte = json.dumps(payload, ensure_ascii=False)

    assert SECRET not in texte
    assert "jio.event.payload.json" not in texte, (
        "les payloads doivent etre absents par defaut : un collecteur n'a pas a recevoir "
        "le contenu du projet sans qu'on le demande"
    )
    assert "jio.payload.redacted" in texte


def test_les_tokens_et_le_modele_suivent_les_conventions_gen_ai() -> None:
    span = _spans(otlp_trace_payload(_journal()))[1]
    attributs = {a["key"]: next(iter(a["value"].values())) for a in span["attributes"]}

    assert attributs["gen_ai.provider.name"] == "openai"
    assert attributs["gen_ai.request.model"] == "gpt-4o-mini"
    assert attributs["gen_ai.usage.input_tokens"] == "120"
    assert attributs["gen_ai.usage.output_tokens"] == "45"
    assert attributs["jio.integrity.chain_clean"] is True


def test_le_statut_d_un_temoin_echoue_est_marque_en_erreur() -> None:
    journal = Journal()
    journal.append("witness", {"rule": "R-001", "ok": False, "exit_code": 1,
                               "message": "AssertionError: 12 != 13"})
    span = _spans(otlp_trace_payload(journal))[0]

    assert span["status"]["code"] == 2
    assert "AssertionError" in span["status"]["message"]


def test_le_contenu_demande_est_redige_et_la_desactivation_est_explicite() -> None:
    journal = _journal()

    masque = json.dumps(
        otlp_trace_payload(journal, include_content=True), ensure_ascii=False
    )
    assert "jio.event.payload.json" in masque
    assert SECRET not in masque
    assert "gpt-4o-mini" in masque, "le modele n'est pas un secret"

    brut = json.dumps(
        otlp_trace_payload(journal, include_content=True, redact=False), ensure_ascii=False
    )
    assert SECRET in brut, "sans redaction, la valeur brute doit etre la — c'est le choix"


def test_un_fichier_existant_n_est_pas_remplace_sans_le_dire(tmp_path: Path) -> None:
    journal = _journal()
    cible = tmp_path / "trace.json"
    write_otlp_json(journal, cible)
    cible.write_text("conserver", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_otlp_json(journal, cible)
    assert cible.read_text(encoding="utf-8") == "conserver"

    write_otlp_json(journal, cible, overwrite=True)
    assert json.loads(cible.read_text(encoding="utf-8"))["resourceSpans"]


def test_un_lien_symbolique_est_refuse(tmp_path: Path) -> None:
    """Ecrire a travers un lien ecraserait un fichier hors de la cible demandee."""
    vrai = tmp_path / "vrai.json"
    vrai.write_text("conserver", encoding="utf-8")
    lien = tmp_path / "lien.json"
    lien.symlink_to(vrai)

    with pytest.raises(OTLPExportError):
        write_otlp_json(_journal(), lien, overwrite=True)
    assert vrai.read_text(encoding="utf-8") == "conserver"


@pytest.mark.parametrize(
    "endpoint",
    ["file:///tmp/x", "ftp://exemple.test/v1/traces", "localhost:4318", "https://"],
)
def test_un_endpoint_non_http_est_refuse(endpoint: str) -> None:
    """Un envoi ne part que vers une URL http(s) absolue, et jamais ailleurs."""
    with pytest.raises(OTLPExportError):
        send_otlp_http(_journal(), endpoint)


def test_aucun_envoi_reseau_n_a_lieu_sans_endpoint(monkeypatch, tmp_path) -> None:
    """Le CLI ne doit joindre personne : on le verifie sur le chemin reellement appele."""
    appels: list[str] = []

    def faux_urlopen(*args, **kwargs):  # substitut de test
        appels.append("reseau")
        raise AssertionError("aucun appel reseau ne devait partir")

    monkeypatch.setattr("urllib.request.urlopen", faux_urlopen)
    cible = tmp_path / "trace.json"
    write_otlp_json(_journal(), cible)
    assert appels == []


def test_le_cli_exporte_otlp_et_refuse_la_desactivation_sans_export(tmp_path, capsys) -> None:
    from jio.cli import main

    journal = Journal(path=tmp_path / ".jio" / "mission.jsonl", racine=tmp_path)
    journal.append("mission", {"objective": "exporter", "api_key": SECRET})
    cible = tmp_path / "trace-otlp.json"

    assert main(["trace", str(journal.path), "--sans-redaction"]) == 2
    capsys.readouterr()

    code = main(["trace", str(journal.path), "--otlp", str(cible)])
    sortie = capsys.readouterr().out

    assert code == 0
    assert "Export OTLP" in sortie
    assert "redaction active" in sortie
    assert SECRET not in cible.read_text(encoding="utf-8")
