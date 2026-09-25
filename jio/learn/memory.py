"""Memoire des echecs — ne jamais repayer deux fois la meme erreur.

Principe
--------
Un echec qui n'est pas enregistre sera repaye. Un echec enregistre mais sans
garde sera repaye aussi : le souvenir sans garde est un journal intime, pas une
memoire. Chaque enregistrement porte donc **obligatoirement** un garde — le test,
le controle ou la regle qui echoue desormais si l'erreur revient.

Pourquoi reutiliser le journal hash-chaine
------------------------------------------
Une memoire de ses propres erreurs est la chose la plus facile a reecrire
discretement. En la stockant dans le meme journal append-only verifie par chaine
de hachage que le reste du systeme, une reecriture devient detectable. La memoire
devient une piece a conviction, pas une narration.

Rappel avant action
-------------------
`recall()` classe les souvenirs par recouvrement de mots-cles (Jaccard pondere),
pas par plongement vectoriel : explicable, hors-ligne, et suffisant a cette
echelle. Un souvenir est un PRIOR, jamais une preuve : si le code a change, on
re-mesure.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from ..core.journal import Journal

__all__ = ["FailureRecord", "FailureMemory", "fingerprint"]

_WORD = re.compile(r"[a-z0-9_]{3,}")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


def fingerprint(objective: str, symptom: str = "") -> str:
    """Empreinte stable d'un echec : objectif normalise + nature du symptome."""
    basis = " ".join(sorted(_tokens(objective))) + "|" + " ".join(sorted(_tokens(symptom))[:12])
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class FailureRecord:
    """Un echec paye, sa cause, et le garde qui l'empeche de revenir."""

    fingerprint: str
    symptom: str            # ce qui a ete observe
    root_cause: str         # la cause REELLE, pas le symptome
    wrong_fix: str          # ce qui a ete tente et n'a pas marche
    correct_fix: str        # ce qui a marche
    guard: str              # le controle qui echoue si l'erreur revient
    objective: str = ""
    mission_id: str = ""
    seq: int = 0

    def as_block(self) -> str:
        return (
            f"- SYMPTOM: {self.symptom}\n"
            f"  CAUSE: {self.root_cause}\n"
            f"  WRONG FIX (do not repeat): {self.wrong_fix or 'n/a'}\n"
            f"  RIGHT FIX: {self.correct_fix}\n"
            f"  GUARD: {self.guard}"
        )


@dataclass
class FailureMemory:
    """Journal append-only des echecs, avec rappel par similarite de mots-cles."""

    path: Path | None = None
    journal: Journal | None = None
    _records: list[FailureRecord] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.journal is None:
            # `Journal(path=...)` OUVRE le fichier en ecriture : il ne relit rien.
            # Sans ce chargement explicite, la memoire ecrivait bien sur disque mais
            # repartait vide a chaque processus — une memoire qui oublie n'est pas
            # une memoire. Bug trouve par le test de rappel, pas par relecture.
            #
            # Et le chargement VERIFIE la chaine de hashes : le contenu de cette
            # memoire repart dans les PROMPTS (voir `prompt_block`). Un fichier edite
            # a la main, ou ecrit par un autre programme, est donc un vecteur
            # d'injection en plus d'etre une memoire fausse. Chaine cassee -> mise en
            # quarantaine (renommage, jamais suppression) et memoire vide, en le disant.
            self.journal = Journal.load_verified(self.path)
        if self._records is None:
            self._records = self._load()

    # -- ecriture ----------------------------------------------------------- #

    def record(
        self,
        *,
        objective: str,
        symptom: str,
        root_cause: str,
        correct_fix: str,
        guard: str,
        wrong_fix: str = "",
        mission_id: str = "",
    ) -> FailureRecord:
        """Enregistre un echec. `guard` est obligatoire : sans garde, pas de memoire."""
        if not guard.strip():
            raise ValueError(
                "un echec sans garde n'est pas une memoire : precisez le controle qui "
                "echouera si l'erreur revient"
            )
        rec = FailureRecord(
            fingerprint=fingerprint(objective, symptom),
            symptom=symptom.strip(),
            root_cause=root_cause.strip(),
            wrong_fix=wrong_fix.strip(),
            correct_fix=correct_fix.strip(),
            guard=guard.strip(),
            objective=objective,
            mission_id=mission_id,
        )
        event = self.journal.append("failure", {
            "fingerprint": rec.fingerprint,
            "symptom": rec.symptom,
            "root_cause": rec.root_cause,
            "wrong_fix": rec.wrong_fix,
            "correct_fix": rec.correct_fix,
            "guard": rec.guard,
            "objective": objective,
            "mission_id": mission_id,
        })
        rec = FailureRecord(**{**rec.__dict__, "seq": event.seq})
        self._records.append(rec)
        return rec

    # -- lecture ------------------------------------------------------------ #

    def recall(self, objective: str, *, limit: int = 3, min_score: float = 0.08) -> list[
        FailureRecord
    ]:
        """Souvenirs pertinents pour un objectif, du plus proche au plus lointain."""
        want = _tokens(objective)
        if not want:
            return []
        scored: list[tuple[float, int, FailureRecord]] = []
        for rec in self._records:
            have = _tokens(f"{rec.objective} {rec.symptom} {rec.root_cause}")
            if not have:
                continue
            inter = len(want & have)
            if not inter:
                continue
            score = inter / len(want | have)
            if score >= min_score:
                scored.append((score, rec.seq, rec))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [rec for _, _, rec in scored[:limit]]

    def prompt_block(self, objective: str, *, limit: int = 3) -> str:
        """Bloc a injecter dans un prompt de generation.

        Un souvenir est un PRIOR, pas une preuve : le bloc le dit explicitement,
        sinon le modele traitera d'anciennes conclusions comme des faits actuels.
        """
        found = self.recall(objective, limit=limit)
        if not found:
            return ""
        lines = [
            "PAST FAILURES ON SIMILAR TASKS (priors, not proofs — re-measure before relying):"
        ]
        lines += [rec.as_block() for rec in found]
        return "\n".join(lines)

    @property
    def size(self) -> int:
        return len(self._records)

    @property
    def head(self) -> str:
        return self.journal.head

    def verify(self) -> tuple[bool, int]:
        """Verifie la chaine d'integrite de la memoire (aucune reecriture discrete).

        `verify_chain()` renvoie `(False, seq)` en cas de rupture et `(True, None)`
        quand tout est sain : convertir `None` en entier levait une TypeError, ce
        qui faisait planter le rapport sur une memoire *valide*.
        """
        ok, bad = self.journal.verify_chain()
        return bool(ok), int(bad) if bad is not None else -1

    def _load(self) -> list[FailureRecord]:
        out: list[FailureRecord] = []
        for event in self.journal:
            if event.kind != "failure":
                continue
            payload = dict(event.payload)
            out.append(
                FailureRecord(
                    fingerprint=str(payload.get("fingerprint", "")),
                    symptom=str(payload.get("symptom", "")),
                    root_cause=str(payload.get("root_cause", "")),
                    wrong_fix=str(payload.get("wrong_fix", "")),
                    correct_fix=str(payload.get("correct_fix", "")),
                    guard=str(payload.get("guard", "")),
                    objective=str(payload.get("objective", "")),
                    mission_id=str(payload.get("mission_id", "")),
                    seq=event.seq,
                )
            )
        return out

    def report(self) -> str:
        ok, bad = self.verify()
        lines = [
            f"memoire : {self.size} echec(s) enregistre(s)",
            f"integrite : {'chaine valide' if ok else f'CHAINE CASSEE @ {bad}'}",
            f"tete : {self.head}",
        ]
        if self.size:
            lines.append("")
            lines.append("5 derniers echecs retenus :")
            for rec in self._records[-5:]:
                lines.append(f"  [{rec.seq}] {rec.symptom[:78]}")
                lines.append(f"        garde : {rec.guard[:70]}")
        else:
            lines.append("")
            lines.append(
                "Aucun echec enregistre. Une memoire vide est un etat legitime au debut :"
            )
            lines.append("le systeme n'invente pas de mises en garde qu'il n'a pas payees.")
        return "\n".join(lines)
