"""Contrats du rapport HTML autonome produit par `jio trace --html`."""

from __future__ import annotations

import json

from jio.cli import main
from jio.core.journal import Journal
from jio.core.types import TrustLevel
from jio.trace_html import rapport_html


def test_rapport_html_est_autonome_et_echappe_le_contenu_non_fiable() -> None:
    journal = Journal()
    journal.append(
        "mission",
        {
            "objectif": "inspecter",
            "contenu": '<img src=x onerror="alert(1)"> HTTP',
            "monde": {"sceau": "etat-a", "revision": "rev-a"},
        },
        trust=TrustLevel.EXTERNAL,
    )
    journal.append(
        "read", {"path": ".env", "monde": {"sceau": "etat-b", "revision": "rev-b"}}
    )

    html = rapport_html(journal, source="mission.jsonl")

    assert html.startswith("<!doctype html>")
    assert "CHAÎNE INTACTE" in html
    assert html.count('class="event-card"') == 2
    assert "&lt;img src=x onerror=\\&quot;alert(1)\\&quot;&gt;" in html
    assert "<img src=x" not in html
    assert "<script" not in html.lower()
    assert "https://" not in html.lower()
    assert "default-src 'none'" in html
    assert "leakage" in html
    assert "MONDE À RELIRE" in html
    assert "masqués dans cette copie" in html


def test_le_rapport_masque_par_defaut_et_laisse_choisir_le_brut(tmp_path) -> None:
    """La redaction est le defaut ; le brut reste possible, mais il est alors DIT."""
    from jio.trace_html import rapport_html

    journal = Journal()
    journal.append("provider", {"api_key": "sk-live-0123456789abcdefghijklmnop"})

    masque = rapport_html(journal, source="mission.jsonl")
    assert "sk-live-0123456789abcdefghijklmnop" not in masque
    assert "[REDACTED]" in masque
    assert "masqués dans cette copie" in masque

    brut = rapport_html(journal, source="mission.jsonl", redact=False)
    assert "sk-live-0123456789abcdefghijklmnop" in brut
    assert "vérifiez-le avant tout partage" in brut
    assert "[REDACTED]" not in brut


def test_trace_cli_exporte_filtre_et_necrase_pas_sans_confirmation(tmp_path, capsys) -> None:
    journal = Journal(path=tmp_path / ".jio" / "mission.jsonl", racine=tmp_path)
    journal.append("mission", {"objectif": "calculer"})
    journal.append("verdict", {"status": "delivered"})
    assert main(["trace", str(journal.path), "--ecraser"]) == 2
    capsys.readouterr()
    sortie = tmp_path / "rapports" / "mission.html"

    code = main([
        "trace", str(journal.path), "--kind", "mission", "--html", str(sortie)
    ])
    resultat = capsys.readouterr()
    html = sortie.read_text(encoding="utf-8")

    assert code == 0
    assert "Rapport HTML" in resultat.out
    assert "Événements dans le journal</span><strong>2" in html
    assert "Événements affichés</span><strong>1" in html
    assert html.count('class="event-card"') == 1
    assert "Filtre actif" in html

    sortie.write_text("conserver cette version", encoding="utf-8")
    code = main(["trace", str(journal.path), "--html", str(sortie)])
    assert code == 2
    assert sortie.read_text(encoding="utf-8") == "conserver cette version"

    code = main([
        "trace", str(journal.path), "--html", str(sortie), "--ecraser"
    ])
    assert code == 0
    assert "<!doctype html>" in sortie.read_text(encoding="utf-8")

    journal_original = journal.path.read_text(encoding="utf-8")
    code = main([
        "trace", str(journal.path), "--html", str(journal.path), "--ecraser"
    ])
    assert code == 2
    assert journal.path.read_text(encoding="utf-8") == journal_original


def test_trace_exporte_un_rapport_qui_signale_une_chaine_cassee(tmp_path) -> None:
    journal = Journal()
    journal.append("mission", {"objectif": "preuve"})
    journal.append("verdict", {"status": "delivered"})
    lignes = journal.to_jsonl().splitlines()
    second = json.loads(lignes[1])
    second["payload"]["status"] = "forged"
    source = tmp_path / "altered.jsonl"
    source.write_text("\n".join([lignes[0], json.dumps(second)]) + "\n", encoding="utf-8")
    sortie = tmp_path / "altered.html"

    code = main(["trace", str(source), "--html", str(sortie)])
    html = sortie.read_text(encoding="utf-8")

    assert code == 1
    assert "CHAÎNE CASSÉE" in html
    assert "position 1" in html
    assert "forged" in html
