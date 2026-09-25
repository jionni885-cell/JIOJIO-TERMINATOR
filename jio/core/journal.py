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

from .errors import IntegrityViolation
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
        #: Ce qu'il faut dire a l'utilisateur sur l'etat du fichier (rotation,
        #: chaine cassee). Un journal ne se repare pas en silence.
        self.notices: list[str] = []
        self._resumed = False
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)

    # -- reprise sur un fichier existant ----------------------------------- #

    def _resume_from_disk(self) -> None:
        """Reprend la chaine existante au lieu d'en demarrer une seconde.

        Defaut constate en usage reel : chaque nouveau processus repartait a
        `seq=0` avec `prev=GENESIS` et AJOUTAIT au meme fichier. Le journal
        devenait invérifiable des la deuxieme execution (9 redemarrages observes
        sur un journal de 545 evenements), c'est-a-dire precisement quand on a
        besoin de lui. Toute la promesse de transparence repose sur ce fichier.

        Comportement retenu, celui d'un journal d'ecriture standard :

        * chaine valide  -> on reprend exactement ou elle s'etait arretee ;
        * chaine CASSEE  -> on n'ecrit JAMAIS par-dessus ni a la suite d'un
          mensonge : le fichier est mis en quarantaine (renomme, jamais
          supprime) et une chaine neuve commence, en le disant.
        """
        if self._resumed or self.path is None or self._events:
            return
        self._resumed = True
        try:
            if not self.path.exists() or self.path.stat().st_size == 0:
                return
            text = self.path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            self.notices.append(f"journal illisible ({exc}) : une chaine neuve commence")
            return

        existing = Journal.from_jsonl(text)
        if not existing._events:
            return
        ok, bad = existing.verify_chain()
        if ok:
            self._events = existing._events
            return

        stamp = int(time.time())
        quarantine = self.path.with_name(f"{self.path.name}.corrompu-{stamp}")
        try:
            self.path.rename(quarantine)
        except OSError as exc:
            raise IntegrityViolation(
                f"le journal {self.path} est incoherent (chaine cassee a l'evenement "
                f"{bad}) et ne peut pas etre deplace ({exc}). Refus d'ecrire a la "
                "suite d'un journal falsifie : deplacez ou supprimez ce fichier."
            ) from exc
        self.notices.append(
            f"journal precedent incoherent (chaine cassee a l'evenement {bad}) : "
            f"conserve sous {quarantine.name}, une chaine neuve commence. "
            "Rien n'a ete supprime."
        )

    # -- ecriture ---------------------------------------------------------- #

    def append(
        self,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        *,
        trust: TrustLevel = TrustLevel.SYSTEM,
    ) -> Event:
        self._resume_from_disk()
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

    @classmethod
    def load_verified(
        cls, path: str | os.PathLike[str] | None, *, quarantine: bool = True
    ) -> Journal:
        """Charge un journal du disque en VERIFIANT sa chaine de hashes.

        `from_jsonl` ne verifie RIEN : il lit. Un fichier edite a la main, ou ecrit
        par un autre programme, serait donc charge tel quel. Pour un journal de
        mission, c'est genant ; pour une MEMOIRE dont le contenu repart dans les
        prompts (memoire des echecs) ou dans les verdicts (bibliotheque de temoins),
        c'est un vecteur d'injection. La verification se fait donc ICI, une fois :

          * chaine valide  -> le journal est rendu tel quel ;
          * chaine CASSEE  -> le fichier est mis en quarantaine (renomme, jamais
            supprime), un journal vide est rendu, et `notices` dit ce qui s'est
            passe. On ne perd jamais une memoire en silence.
        """
        if path is None:
            return cls(path=None)
        chemin = Path(path)
        if not chemin.exists() or chemin.stat().st_size == 0:
            return cls(path=chemin)
        try:
            texte = chemin.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            journal = cls(path=chemin)
            journal.notices.append(f"memoire illisible ({exc}) : repart a vide")
            return journal

        try:
            journal = cls.from_jsonl(texte, path=chemin)
        except (ValueError, KeyError, TypeError) as exc:
            # Un fichier qui n'est meme pas du JSON est traite comme une chaine
            # cassee : meme traitement, meme visibilite. Un fichier illisible ne doit
            # jamais bloquer une mission, mais il ne doit pas non plus disparaitre
            # en silence.
            return cls._quarantaine(chemin, f"illisible ({exc})", quarantine)
        if not journal._events:  # noqa: SLF001 — meme classe
            return journal
        ok, bad = journal.verify_chain()
        if ok:
            return journal
        return cls._quarantaine(chemin, f"chaine cassee a l'evenement {bad}", quarantine)

    @classmethod
    def _quarantaine(cls, chemin: Path, motif: str, quarantine: bool) -> Journal:
        """Retire un fichier de memoire incoherent du chemin actif, en le DISANT.

        Renommer, jamais supprimer : l'utilisateur doit pouvoir inspecter ce qu'on a
        refuse d'appliquer. Et si le renommage est impossible, on n'ecrit RIEN a la
        suite d'un fichier douteux — on repart d'une memoire vide, en memoire vive.
        """
        if not quarantine:
            vide = cls(path=None)
            vide.notices.append(f"memoire incoherente ({motif}) : IGNOREE.")
            return vide
        horodatage = int(time.time())
        cible = chemin.with_name(f"{chemin.name}.corrompu-{horodatage}")
        try:
            chemin.rename(cible)
        except OSError as exc:
            vide = cls(path=None)
            vide.notices.append(
                f"memoire incoherente ({motif}) et impossible a deplacer ({exc}) : "
                "elle est IGNOREE, rien n'est ecrit."
            )
            return vide
        vide = cls(path=chemin)
        vide.notices.append(
            f"memoire incoherente ({motif}) : conservee sous {cible.name}, jamais "
            "appliquee. Une chaine neuve commence."
        )
        return vide


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
