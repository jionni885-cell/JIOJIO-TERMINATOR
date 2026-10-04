"""Export des journaux JIO vers OTLP/HTTP en JSON protobuf.

Aucune dépendance OpenTelemetry n'est requise : le format d'export est construit
avec la bibliothèque standard. Les payloads sont omis par défaut ; quand ils
sont demandés, ils passent tout de même par la politique de redaction de JIO.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
import urllib.error
import urllib.request
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from .. import __version__
from ..core.journal import Event, Journal
from ..core.redaction import redact_data, redact_text


class OTLPExportError(RuntimeError):
    """L'export local ou l'envoi OTLP n'a pas abouti."""


def _attribute(name: str, value: Any, *, redact: bool = True) -> dict[str, Any]:
    """Encode un attribut AnyValue selon la représentation JSON protobuf OTLP."""
    if isinstance(value, bool):
        encoded = {"boolValue": value}
    elif isinstance(value, int):
        encoded = {"intValue": str(value)}
    elif isinstance(value, float) and math.isfinite(value):
        encoded = {"doubleValue": value}
    elif isinstance(value, str):
        encoded = {"stringValue": redact_text(value) if redact else value}
    else:
        material = redact_data(value) if redact else value
        encoded = {"stringValue": json.dumps(material, ensure_ascii=False, default=str)}
    return {"key": name, "value": encoded}


def _trace_id(journal: Journal) -> str:
    material = f"jio:{journal.head}:{len(journal)}".encode()
    value = hashlib.sha256(material).hexdigest()[:32]
    return value if int(value, 16) else "0" * 31 + "1"


def _span_id(event: Event, index: int) -> str:
    value = hashlib.sha256(f"{event.digest}:{index}".encode("ascii", "replace")).hexdigest()[:16]
    return value if int(value, 16) else "0" * 15 + "1"


def _timestamp_ns(seconds: float) -> int:
    if not math.isfinite(seconds) or seconds < 0:
        return 0
    return int(seconds * 1_000_000_000)


def _duration(payload: Mapping[str, Any]) -> float:
    raw = payload.get("duration_s", payload.get("duration", 0.0))
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return value if math.isfinite(value) and value > 0 else 0.0


def _error_message(event: Event, *, redact: bool = True) -> str:
    for key in ("error", "message", "reason", "detail"):
        value = event.payload.get(key)
        if value:
            text = str(value)
            return (redact_text(text) if redact else text)[:512]
    return ""


def _span(event: Event, index: int, trace_id: str, previous_span_id: str | None,
          chain_clean: bool, *, include_content: bool, redact: bool = True) -> dict[str, Any]:
    span_id = _span_id(event, index)
    start_ns = _timestamp_ns(event.ts)
    duration_s = _duration(event.payload)
    end_ns = start_ns + int(duration_s * 1_000_000_000)
    payload = event.payload
    attributes: dict[str, Any] = {
        "jio.event.sequence": event.seq,
        "jio.event.kind": event.kind,
        "jio.event.trust": event.trust.value,
        "jio.event.hash": event.digest,
        "jio.integrity.chain_clean": chain_clean,
        "jio.payload.redacted": redact,
    }

    for output, names in (
        ("gen_ai.request.model", ("model", "model_name", "request_model")),
        ("gen_ai.provider.name", ("provider", "provider_name")),
        ("gen_ai.operation.name", ("operation", "operation_name")),
    ):
        value = next((payload[name] for name in names if payload.get(name) is not None), None)
        if isinstance(value, (str, int, float, bool)):
            attributes[output] = value

    usage = payload.get("usage")
    if isinstance(usage, Mapping):
        for source, target in (
            ("input_tokens", "gen_ai.usage.input_tokens"),
            ("prompt_tokens", "gen_ai.usage.input_tokens"),
            ("output_tokens", "gen_ai.usage.output_tokens"),
            ("completion_tokens", "gen_ai.usage.output_tokens"),
            ("total_tokens", "gen_ai.usage.total_tokens"),
        ):
            if source in usage and target not in attributes:
                try:
                    attributes[target] = int(usage[source])
                except (TypeError, ValueError):
                    continue

    if include_content:
        material = redact_data(dict(payload)) if redact else dict(payload)
        attributes["jio.event.payload.json"] = json.dumps(
            material, ensure_ascii=False, sort_keys=True, default=str
        )

    status_code = 0  # OTLP: UNSET
    status: dict[str, Any] = {"code": status_code}
    is_error = event.kind.casefold() in {"error", "failure", "failed", "provider_error"}
    if isinstance(payload.get("ok"), bool):
        is_error = not payload["ok"]
    if "exit_code" in payload:
        try:
            is_error = int(payload["exit_code"]) != 0
        except (TypeError, ValueError):
            pass
    if is_error:
        status = {"code": 2, "message": _error_message(event, redact=redact)}
    elif payload.get("ok") is True or payload.get("accepted") is True:
        status = {"code": 1}

    nom = redact_text(event.kind) if redact else event.kind
    span: dict[str, Any] = {
        "traceId": trace_id,
        "spanId": span_id,
        "name": nom[:128] or "jio.event",
        "kind": 1,  # INTERNAL
        "startTimeUnixNano": str(start_ns),
        "endTimeUnixNano": str(end_ns),
        "attributes": [
            _attribute(key, value, redact=redact)
            for key, value in sorted(attributes.items())
        ],
        "status": status,
    }
    if previous_span_id is not None:
        span["parentSpanId"] = previous_span_id
    return span


def otlp_trace_payload(
    journal: Journal,
    *,
    include_content: bool = False,
    service_name: str = "jio",
    redact: bool = True,
) -> dict[str, Any]:
    """Construit un objet ExportTraceServiceRequest compatible OTLP/HTTP JSON.

    Par défaut, les payloads des événements ne sont PAS exportés : seuls le type,
    la séquence, le niveau de confiance, l'empreinte, l'état de la chaîne et les
    métriques standardisées le sont. `include_content=True` ajoute le payload en
    JSON, toujours passé par la politique de redaction sauf `redact=False`.
    """
    events = tuple(journal)
    chain_clean, _bad_index = journal.verify_chain()
    trace_id = _trace_id(journal)
    spans: list[dict[str, Any]] = []
    previous: str | None = None
    for index, event in enumerate(events):
        current = _span(
            event,
            index,
            trace_id,
            previous,
            chain_clean,
            include_content=include_content,
            redact=redact,
        )
        spans.append(current)
        previous = current["spanId"]

    return {
        "resourceSpans": [
            {
                "resource": {
                    "attributes": [
                        _attribute("service.name", service_name, redact=redact),
                        _attribute("service.version", __version__, redact=redact),
                    ]
                },
                "scopeSpans": [
                    {
                        "scope": {"name": "jio.trace", "version": __version__},
                        "spans": spans,
                    }
                ],
            }
        ]
    }


def _write_json(path: Path, text: str, *, overwrite: bool) -> None:
    if path.is_symlink():
        raise OTLPExportError(f"refus d'écrire à travers un lien symbolique : {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if overwrite:
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", prefix=f".{path.name}.", suffix=".tmp",
                dir=path.parent, delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(text)
            os.replace(temporary, path)
            temporary = None
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
        return
    with path.open("x", encoding="utf-8") as handle:
        handle.write(text)


def write_otlp_json(
    journal: Journal,
    destination: str | os.PathLike[str],
    *,
    include_content: bool = False,
    overwrite: bool = False,
    redact: bool = True,
) -> Path:
    """Écrit un export JSON sans remplacer un fichier existant par défaut."""
    path = Path(destination).expanduser()
    body = json.dumps(
        otlp_trace_payload(journal, include_content=include_content, redact=redact),
        ensure_ascii=False,
        indent=2,
    ) + "\n"
    _write_json(path, body, overwrite=overwrite)
    return path


def send_otlp_http(
    journal: Journal,
    endpoint: str,
    *,
    include_content: bool = False,
    timeout: float = 10.0,
    redact: bool = True,
) -> int:
    """POSTe l'export vers un endpoint OTLP/HTTP explicitement fourni."""
    parsed = urlsplit(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise OTLPExportError("l'endpoint OTLP doit être une URL http(s) absolue")
    if parsed.username or parsed.password or parsed.fragment:
        raise OTLPExportError("l'endpoint OTLP ne peut contenir ni identifiants ni fragment")
    body = json.dumps(
        otlp_trace_payload(journal, include_content=include_content, redact=redact),
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = int(response.status)
    except (OSError, urllib.error.URLError, TimeoutError) as exc:
        raise OTLPExportError(f"échec d'envoi OTLP : {exc}") from exc
    if not 200 <= status < 300:
        raise OTLPExportError(f"l'endpoint OTLP a répondu HTTP {status}")
    return status


__all__ = ["OTLPExportError", "otlp_trace_payload", "send_otlp_http", "write_otlp_json"]
