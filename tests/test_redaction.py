"""Redaction : un export ne doit pas laisser fuir un secret reconnu, ni casser le journal.

Ce que ces tests fixent, et pourquoi :

1. les valeurs SOUS un champ sensible (cle, jeton, mot de passe, e-mail, telephone)
   sont remplacees, quelle que soit la casse ou l'orthographe du nom de champ ;
2. les motifs connus sont masques MEME dans du texte libre, ou le nom de champ ne dit
   rien — c'est le cas des sorties d'outil recopiees dans un payload ;
3. les metriques technique du harnais (`input_tokens`, latence, modele) SURVIVENT : une
   redaction trop large rendrait les traces inutilisables, et on finirait par la couper ;
4. l'export ne touche JAMAIS le journal source : la chaine de hachage reste verifiable.
"""

from __future__ import annotations

import pytest

from jio.core.journal import Journal
from jio.core.redaction import REDACTED, is_sensitive_key, redact_data, redact_text


@pytest.mark.parametrize(
    "cle",
    [
        "api_key",
        "apiKey",
        "API-KEY",
        "access_token",
        "refreshToken",
        "client_secret",
        "password",
        "passwd",
        "Authorization",
        "Cookie",
        "private_key",
        "email",
        "telephone",
        "mobile",
        "iban",
        "card_number",
    ],
)
def test_un_nom_de_champ_sensible_est_reconnu(cle: str) -> None:
    assert is_sensitive_key(cle), f"{cle} devrait etre reconnu comme sensible"


@pytest.mark.parametrize(
    "cle",
    ["input_tokens", "output_tokens", "duration_s", "model", "provider", "rule", "exit_code",
     "kind", "trust", "digest"],
)
def test_un_champ_technique_n_est_PAS_masque(cle: str) -> None:
    """Une redaction qui mange les metriques du harnais serait desactivee, pas utile."""
    assert not is_sensitive_key(cle), f"{cle} ne doit pas etre masque"


def test_une_valeur_sous_un_champ_sensible_est_remplacee() -> None:
    donnees = {
        "provider": "openai",
        "api_key": "sk-live-0123456789abcdefghijklmnop",
        "nested": {"refresh_token": "abc", "model": "gpt-4o-mini"},
        "usage": {"input_tokens": 120},
    }
    masque = redact_data(donnees)

    assert masque["api_key"] == REDACTED
    assert masque["nested"]["refresh_token"] == REDACTED
    assert masque["nested"]["model"] == "gpt-4o-mini"
    assert masque["usage"]["input_tokens"] == 120
    assert donnees["api_key"] == "sk-live-0123456789abcdefghijklmnop", "la source ne bouge pas"


def test_un_jeton_dans_du_TEXTE_LIBRE_est_masque_meme_sans_nom_de_champ() -> None:
    """`message` ne dit pas qu'il contient un secret : le motif doit suffire."""
    texte = (
        "appel refuse: Authorization: Bearer sk-live-0123456789abcdefghijklmnop "
        "puis gh_token ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    )
    masque = redact_text(texte)

    assert "sk-live-0123456789abcdefghijklmnop" not in masque
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789" not in masque
    assert REDACTED in masque


def test_une_adresse_email_et_un_telephone_sont_masques() -> None:
    masque = redact_text("ecrire a alice.dupont@example.com ou au +33 6 12 34 56 78")

    assert "alice.dupont@example.com" not in masque
    assert "+33 6 12 34 56 78" not in masque


def test_un_nombre_technique_n_est_pas_pris_pour_un_telephone() -> None:
    """`120`, `5400`, `3.14` ne sont pas des numeros : les masquer detruirait la preuve."""
    assert redact_text("tokens 120 · duree 5400 · ratio 3.14") == (
        "tokens 120 · duree 5400 · ratio 3.14"
    )


def test_une_cle_privee_complete_est_masquee() -> None:
    texte = "-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBg\n-----END PRIVATE KEY-----"
    assert "MIIEvQIBADANBg" not in redact_text(texte)


def test_l_export_html_ne_modifie_PAS_le_journal_source() -> None:
    """La redaction est une couche d'export : le journal doit rester verifiable tel quel."""
    from jio.trace_html import rapport_html

    journal = Journal()
    journal.append("provider", {"api_key": "sk-live-0123456789abcdefghijklmnop"})
    avant = journal.to_jsonl()

    html = rapport_html(journal, source="mission.jsonl")

    assert "sk-live-0123456789abcdefghijklmnop" not in html
    assert journal.to_jsonl() == avant
    assert journal.verify_chain() == (True, None)
    assert "sk-live-0123456789abcdefghijklmnop" in journal.to_jsonl(), (
        "le journal, lui, garde la valeur : c'est la copie partagee qui est masquee"
    )
