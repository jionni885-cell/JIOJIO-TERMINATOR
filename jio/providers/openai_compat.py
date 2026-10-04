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
from . import base as _base
from .base import Completion, Message, borner, extraire_texte


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
                # Lecture BORNEE : un serveur (ou un proxy) hostile peut streamer sans fin.
                # On refuse au lieu de tout charger — une reponse tronquee ne serait pas du
                # JSON valide, et la lire quand meme reviendrait a accepter n'importe quoi.
                # `_base.MAX_REPONSE` et non une copie importee : le plafond doit exister
                # a UN seul endroit. La premiere version l'importait par valeur ici et le
                # lisait dynamiquement dans `borner` — deux valeurs pour une meme regle,
                # et un test qui croyait l'avoir baissee sans rien changer.
                plafond = _base.MAX_REPONSE * 8
                brut = resp.read(plafond + 1)
                if len(brut) > plafond:
                    raise ProviderError(
                        f"reponse de {self.name} au-dela de {plafond} octets : "
                        "refusee plutot que chargee en memoire"
                    )
                raw = json.loads(brut.decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:  # pragma: no cover
            detail = exc.read().decode("utf-8", "replace")[:400]
            raise ProviderError(f"HTTP {exc.code} sur {self.name}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:  # pragma: no cover
            raise ProviderError(f"reseau indisponible pour {self.name}: {exc}") from exc
        except json.JSONDecodeError as exc:  # pragma: no cover
            raise ProviderError(f"reponse non-JSON de {self.name}") from exc

        if not isinstance(raw, dict):
            raise ProviderError(f"reponse inattendue de {self.name}: {type(raw).__name__}")
        choices = raw.get("choices") or []
        if not choices:
            raise ProviderError(f"reponse vide de {self.name}: {str(raw)[:300]}")
        premier = choices[0] if isinstance(choices[0], dict) else {}
        message = premier.get("message") if isinstance(premier.get("message"), dict) else {}
        text = extraire_texte(message.get("content"))
        text, tronque = borner(text)
        if not text.strip():
            # Une reponse vide n'est pas un artefact : la laisser passer ferait echouer les
            # regles en aval sans que personne ne sache pourquoi. On le dit ici.
            raison = premier.get("finish_reason", "?")
            raise ProviderError(
                f"{self.name} a repondu une chaine vide (finish_reason={raison})"
            )
        usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
        meta: dict[str, object] = {"tronque": True} if tronque else {}
        return Completion(
            text=text,
            model=raw.get("model", self.model),
            provider=self.name,
            prompt_tokens=int(usage.get("prompt_tokens", 0)),
            completion_tokens=int(usage.get("completion_tokens", 0)),
            stop_reason=premier.get("finish_reason", "stop"),
            metadata=meta,
        )


__all__ = ["OpenAiCompatProvider"]
