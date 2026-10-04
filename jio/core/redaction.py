"""Redaction prudente des exports de traces.

Les journaux JIO restent intacts et hash-chaînés. Cette couche ne transforme que
les copies destinées à être partagées (HTML, OpenTelemetry, jeux d'évaluation) :
clés de secret connues, identifiants usuels, adresses e-mail et numéros de
 téléphone reconnaissables sont masqués par défaut. Ce n'est pas un détecteur
universel de données personnelles ; tout export reste à relire avant diffusion.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

# Après normalisation, ces marqueurs couvrent les noms les plus répandus sans
# confondre les compteurs `input_tokens` / `output_tokens` avec des identifiants.
_SENSITIVE_MARKERS = (
    "apikey",
    "accesstoken",
    "refreshtoken",
    "idtoken",
    "authtoken",
    "clienttoken",
    "sessiontoken",
    "bearertoken",
    "clientsecret",
    "secret",
    "password",
    "passwd",
    "credential",
    "authorization",
    "cookie",
    "privatekey",
    "sshkey",
    "email",
    "phone",
    "telephone",
    "mobile",
    "socialsecurity",
    "nationalid",
    "passport",
    "dateofbirth",
    "creditcard",
    "cardnumber",
    "iban",
)
_SENSITIVE_EXACT = {"token", "email", "phone", "mobile", "dob", "ssn", "iban"}

_KEY_VALUE_RE = re.compile(
    r"(?ix)"
    r"((?:[\"']?)(?:[a-z0-9_.-]*(?:api[_-]?key|access[_-]?token|"
    r"refresh[_-]?token|id[_-]?token|auth[_-]?token|client[_-]?token|"
    r"session[_-]?token|bearer[_-]?token|client[_-]?secret|secret|"
    r"password|passwd|credential|authorization|cookie|private[_-]?key|"
    r"ssh[_-]?key|email|phone|telephone|mobile|ssn|dob|date[_-]?of[_-]?birth|"
    r"national[_-]?id|passport|credit[_-]?card|card[_-]?number|iban)"
    r"[a-z0-9_.-]*)(?:[\"']?)\s*[:=]\s*)"
    r"(?:\"[^\"]*\"|'[^']*'|[^\s,;&]+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*")
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----.*?"
    r"-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----",
    re.DOTALL,
)
_TOKEN_RE = re.compile(
    r"(?i)\b(?:"
    r"(?:sk|rk)-[a-z0-9_-]{16,}|"
    r"(?:gh[pousr]_[A-Za-z0-9]{20,})|"
    r"github_pat_[A-Za-z0-9_]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{16,}|"
    r"AIza[0-9A-Za-z_-]{30,}|"
    r"AKIA[0-9A-Z]{16}"
    r")\b"
)
_JWT_RE = re.compile(r"\b[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{8,}\b")
_EMAIL_RE = re.compile(
    r"(?i)\b[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+\b"
)
_PHONE_RE = re.compile(r"(?<![\w])\+?[0-9][0-9 ().-]{7,}[0-9](?![\w])")


def is_sensitive_key(key: object) -> bool:
    """Indique si un nom de champ suggère un secret ou une donnée personnelle."""
    normalised = re.sub(r"[^a-z0-9]", "", str(key).casefold())
    return normalised in _SENSITIVE_EXACT or any(
        marker in normalised for marker in _SENSITIVE_MARKERS
    )


def redact_text(text: str) -> str:
    """Masque les motifs reconnaissables dans un texte libre."""
    value = _PRIVATE_KEY_RE.sub(REDACTED, text)
    value = _KEY_VALUE_RE.sub(lambda match: f'{match.group(1)}"{REDACTED}"', value)
    value = _BEARER_RE.sub(f"Bearer {REDACTED}", value)
    value = _TOKEN_RE.sub(REDACTED, value)
    value = _JWT_RE.sub(REDACTED, value)
    value = _EMAIL_RE.sub(REDACTED, value)

    def masque_telephone(match: re.Match[str]) -> str:
        digits = sum(character.isdigit() for character in match.group(0))
        return REDACTED if 10 <= digits <= 15 else match.group(0)

    return _PHONE_RE.sub(masque_telephone, value)


def redact_data(value: Any, *, key: object | None = None) -> Any:
    """Renvoie une copie récursivement expurgée sans modifier la donnée source."""
    if key is not None and is_sensitive_key(key):
        return REDACTED
    if isinstance(value, Mapping):
        return {str(name): redact_data(item, key=name) for name, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_data(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


__all__ = ["REDACTED", "is_sensitive_key", "redact_data", "redact_text"]
