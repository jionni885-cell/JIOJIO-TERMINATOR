"""Journal d'evenements append-only, hash-chaine, rejouable.

C'est la colonne vertebrale du systeme :

* **Append-only** : on n'ecrase jamais une decision.
* **Hash-chaine** : chaque entree lie le hash de la precedente — toute
  alteration est detectable.
* **Rejouable** : le `IntegrityMonitor` rejoue le journal avec des regles
  deterministes pour classer les exploits (Reward Hacking Benchmark).

Le journal est la source de verite, jamais le transcript du modele.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from .types import TrustLevel, canonical, digest_of, now

GENESIS = "0" * 32


@dataclass(frozen=True)
class Event:
    """Une entree du journal."""

    seq: int
    ts: float
    kind: str
    payload: Mapping[str, Any]
    trust: TrustLevel
    prev_hash: str
    digest: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "ts": self.ts,
            "kind": self.kind,
            "trust": self.trust.value,
            "payload": dict(self.payload),
            "prev": self.prev_hash,
            "digest": self.digest,
        }


def _compute_digest(
    seq: int, ts: float, kind: str, payload: Mapping[str, Any],
    trust: TrustLevel, prev_hash: str,
) -> str:
    return digest_of(seq, round(ts, 6), kind, payload, trust.value, prev_hash)


class Journal:
    """Journal append-only en memoire, capable de miroiter sur disque."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self._events: list[Event] = []
        self.path = Path(path) if path is not None else None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- ecriture ---------------------------------------------------------- #

    def append(
        self,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        *,
        trust: TrustLevel = TrustLevel.SYSTEM,
    ) -> Event:
        seq = len(self._events)
        ts = now()
        body: Mapping[str, Any] = dict(payload or {})
        prev = self._events[-1].digest if self._events else GENESIS
        ev = Event(
            seq=seq,
            ts=ts,
            kind=kind,
            payload=body,
            trust=trust,
            prev_hash=prev,
            digest=_compute_digest(seq, ts, kind, body, trust, prev),
        )
        self._events.append(ev)
        if self.path is not None:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(ev.as_dict(), ensure_ascii=False, default=str))
                fh.write("\n")
        return ev

    # -- lecture ----------------------------------------------------------- #

    def __len__(self) -> int:
        return len(self._events)

    def __iter__(self) -> Iterator[Event]:
        return iter(self._events)

    def events(self, *kinds: str) -> tuple[Event, ...]:
        if not kinds:
            return tuple(self._events)
        wanted = set(kinds)
        return tuple(e for e in self._events if e.kind in wanted)

    def last(self) -> Event | None:
        return self._events[-1] if self._events else None

    @property
    def head(self) -> str:
        return self._events[-1].digest if self._events else GENESIS

    # -- integrite --------------------------------------------------------- #

    def verify_chain(self) -> tuple[bool, int | None]:
        """Verifie la chaine de hashes.

        Retourne ``(True, None)`` si tout est coherent, sinon
        ``(False, index_de_la_premiere_entree_invalide)``.
        """
        prev = GENESIS
        for idx, ev in enumerate(self._events):
            if ev.seq != idx or ev.prev_hash != prev:
                return False, idx
            expected = _compute_digest(
                ev.seq, round(ev.ts, 6), ev.kind, ev.payload, ev.trust, ev.prev_hash
            )
            if expected != ev.digest:
                return False, idx
            prev = ev.digest
        return True, None

    def replay(self) -> "Journal":
        """Reconstruit un journal neuf a partir des evenements, puis verifie.

        Detecte toute falsification : si un `payload` a ete modifie apres coup,
        la chaine casse et `verify_chain()` le signale.
        """
        clone = Journal()
        for ev in self._events:
            clone._events.append(ev)  # noqa: SLF001 — copie fidele volontaire
        return clone

    # -- export ------------------------------------------------------------ #

    def to_jsonl(self) -> str:
        return "\n".join(
            json.dumps(e.as_dict(), ensure_ascii=False, default=str) for e in self._events
        )

    @classmethod
    def from_jsonl(cls, text: str, path: str | os.PathLike[str] | None = None) -> "Journal":
        j = cls(path=path)
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            j._events.append(  # noqa: SLF001
                Event(
                    seq=int(raw["seq"]),
                    ts=float(raw["ts"]),
                    kind=str(raw["kind"]),
                    payload=dict(raw.get("payload", {})),
                    trust=TrustLevel(raw.get("trust", "system")),
                    prev_hash=str(raw.get("prev", GENESIS)),
                    digest=str(raw.get("digest", "")),
                )
            )
        return j

    def summary(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for ev in self._events:
            counts[ev.kind] = counts.get(ev.kind, 0) + 1
        ok, bad = self.verify_chain()
        return {
            "events": len(self._events),
            "kinds": counts,
            "chain_ok": ok,
            "first_bad": bad,
            "head": self.head,
        }


__all__ = ["Event", "Journal", "GENESIS"]
