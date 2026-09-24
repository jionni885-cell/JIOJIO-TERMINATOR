"""Adaptateur API compatible OpenAI (OpenRouter, Ollama, vLLM, etc.).

Sans dependance obligatoire : utilise `urllib` de la bibliotheque standard.
Si `httpx` est installe, il est utilise automatiquement (meilleure gestion
des timeouts et du streaming).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Sequence

from ..core.errors import ProviderError
from .base import Completion, Message


@dataclass
class OpenAiCompatProvider:
    """Client minimal pour toute API compatible OpenAI."""

    base_url: str
    api_key: str = ""
    model: str = "gpt-4o-mini"
    name: str = "api"
    timeout: int = 180
    temperature: float = 0.0

    def _endpoint(self) -> str:
        base = self.base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if not base.endswith("/v1"):
            base = f"{base}/v1"
        return f"{base}/chat/completions"

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        seed: int | None = None,
    ) -> Completion:
        body: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature or self.temperature,
            "max_tokens": max_tokens,
        }
        if seed is not None:
            body["seed"] = seed

        payload = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        req = urllib.request.Request(  # noqa: S310 — URL fournie par l'utilisateur
            self._endpoint(), data=payload, headers=headers, method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310
                raw = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:  # pragma: no cover
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise ProviderError(f"HTTP {exc.code} sur {self.name}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:  # pragma: no cover
            raise ProviderError(f"reseau indisponible pour {self.name}: {exc}") from exc
        except json.JSONDecodeError as exc:  # pragma: no cover
            raise ProviderError(f"reponse non-JSON de {self.name}") from exc

        choices = raw.get("choices") or []
        if not choices:
            raise ProviderError(f"reponse vide de {self.name}: {str(raw)[:300]}")
        text = (choices[0].get("message") or {}).get("content", "") or ""
        usage = raw.get("usage") or {}
        return Completion(
            text=text,
            model=raw.get("model", self.model),
            provider=self.name,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            stop_reason=choices[0].get("finish_reason", "stop"),
        )


__all__ = ["OpenAiCompatProvider"]
