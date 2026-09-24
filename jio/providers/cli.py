"""Adaptateur CLI externe — pilote les agents deja installes sur la machine.

Permet a JIO d'utiliser **opencode**, **Hermes Agent**, `claude`, `codex`,
`gemini` ou tout binaire compatible, sans gerer la moindre cle API :
l'authentification reste celle que l'utilisateur a deja configuree.

Exemple :
    opencode run --format json "…"
    hermes chat -q "…"
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from shlex import split as shsplit
from typing import Sequence

from ..core.errors import ProviderError
from .base import Completion, Message, render


@dataclass
class CliProvider:
    """Fournisseur adosse a un binaire en ligne de commande.

    `argv_template` doit contenir ``{prompt}`` ; il est envoye sur stdin quand
    ``use_stdin=True`` (plus sur avec des prompts longs et des caracteres speciaux).
    """

    binary: str
    argv_template: str = "{binary} run {prompt}"
    name: str = "cli"
    model: str = "cli"
    timeout: int = 300
    use_stdin: bool = False
    extra_env: dict[str, str] | None = None

    def available(self) -> bool:
        return shutil.which(self.binary) is not None

    def complete(
        self,
        messages: Sequence[Message],
        *,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        seed: int | None = None,
    ) -> Completion:
        if not self.available():
            raise ProviderError(f"binaire introuvable : {self.binary!r}")

        prompt = render(messages)
        rendered = self.argv_template.format(binary=self.binary, prompt="")
        argv = [a for a in shsplit(rendered) if a]

        if self.use_stdin or "{prompt}" not in self.argv_template:
            stdin_data = prompt
        else:
            # Le prompt est passe en argument unique, jamais concatene au shell.
            argv = []
            for token in shsplit(self.argv_template.format(binary=self.binary, prompt="@@P@@")
                                 .replace("@@P@@", "\x00")):
                argv.extend(
                    [prompt] if token == "\x00" else [t for t in token.split("\x00")]
                )
            argv = [a or prompt for a in argv if a != ""] or [self.binary, "run", prompt]
            stdin_data = ""

        try:
            proc = subprocess.run(  # noqa: S603 — argv explicite, pas de shell
                argv,
                input=stdin_data,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                env=None,
            )
        except subprocess.TimeoutExpired as exc:  # pragma: no cover
            raise ProviderError(f"{self.binary} timeout apres {self.timeout}s") from exc

        if proc.returncode != 0:
            raise ProviderError(
                f"{self.binary} exit={proc.returncode}: {proc.stderr.strip()[:400]}"
            )

        text = proc.stdout
        meta: dict[str, object] = {"cli": self.binary}
        # `opencode run --format json` emet des evenements JSON ligne a ligne.
        if text.lstrip().startswith("{"):
            parsed = _try_jsonl(text)
            if parsed is not None:
                text, meta = parsed, {"cli": self.binary, "format": "jsonl"}

        return Completion(
            text=text,
            model=self.model,
            provider=self.name,
            prompt_tokens=max(1, len(prompt) // 4),
            completion_tokens=max(1, len(text) // 4),
            metadata=meta,
        )


def _try_jsonl(text: str) -> str | None:
    """Extrait le texte utile d'une sortie JSON-ligne (opencode --format json)."""
    chunks: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            return None
        if not isinstance(obj, dict):
            return None
        for key in ("text", "content", "message"):
            val = obj.get(key)
            if isinstance(val, str) and val:
                chunks.append(val)
                break
        else:
            part = obj.get("part")
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                chunks.append(part["text"])
    return "\n".join(chunks) if chunks else None


__all__ = ["CliProvider"]
