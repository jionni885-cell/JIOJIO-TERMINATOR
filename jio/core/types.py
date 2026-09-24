"""Types du domaine JIO.

Tout le systeme parle ce vocabulaire. Les types sont immuables par defaut :
une decision prise une fois ne peut pas etre reecrite en silence.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence


# --------------------------------------------------------------------------- #
# Niveaux de confiance
# --------------------------------------------------------------------------- #


class TrustLevel(str, Enum):
    """Niveau de confiance d'un contenu (L1 — securite architecturale).

    Le contenu EXTERNAL est traite comme HOSTILE par defaut : tout ce qui vient
    d'un depot, d'un fichier, d'un outil ou du web est une surface d'injection.
    """

    SYSTEM = "system"      # regles du systeme, jamais influencees de l'exterieur
    USER = "user"          # instruction de l'utilisateur
    EXTERNAL = "external"  # contenu non fiable : depot, outil, web, document


class Verdict(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    ABSTAIN = "abstain"
    ERROR = "error"


class Severity(str, Enum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def rank(self) -> int:
        return _SEVERITY_RANK[self]


_SEVERITY_RANK = {
    Severity.INFO: 0,
    Severity.LOW: 1,
    Severity.MEDIUM: 2,
    Severity.HIGH: 3,
    Severity.CRITICAL: 4,
}


class MissionStatus(str, Enum):
    """Etat final. `ABSTAINED` est un resultat de premiere classe, pas un echec."""

    DELIVERED = "delivered"
    DELIVERED_WITH_RESERVATION = "delivered_with_reservation"
    ABSTAINED = "abstained"
    FAILED = "failed"


class RuleKind(str, Enum):
    """Nature d'une regle de specification (SPEC grounding)."""

    PROPERTY = "property"      # invariant qui doit toujours tenir
    TEST = "test"              # un test executables
    BOUNDARY = "boundary"      # cas limite / entree invalide
    CONTRACT = "contract"      # pre/postcondition
    SECURITY = "security"      # interdiction explicite
    #: Regle de suspicion : son echec ne prouve pas un defaut (horloge, hasard,
    #: dependance a l'environnement). Elle produit une RESERVE, jamais un rejet —
    #: un faux positif detruit la confiance dans le garde.
    ADVISORY = "advisory"


class ExploitKind(str, Enum):
    """Taxonomie des 6 exploits (Reward Hacking Benchmark, ICML 2026)."""

    LEAKAGE = "leakage"                  # lecture de metadonnees/grader
    TAMPERING = "tampering"              # modification du verificateur ou d'un chemin protege
    SEQUENCE = "sequence"                # produit intermediaire fabrique pour sauter une etape
    PROXY_GAMING = "proxy_gaming"        # sortie minimale qui satisfait un parseur naif
    SPECIAL_CASING = "special_casing"    # code taille pour les tests visibles
    MEMORIZATION = "memorization"        # copie d'une solution memorisee


class Stage(str, Enum):
    """Etapes de la boucle centrale."""

    SPEC = "spec"
    GENERATE = "generate"
    PROVE = "prove"
    AUDIT = "audit"
    CONSENSUS = "consensus"
    GATE = "gate"
    INTEGRITY = "integrity"
    MEMORY = "memory"


# --------------------------------------------------------------------------- #
# Specification
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Rule:
    """Une regle elementaire, verifiable independamment.

    Regle d'or du SPEC grounding : **un test par regle enumeree**.
    Mesure : +38 pts de code correct, fausses alertes 33% -> 0%.
    """

    id: str
    statement: str
    kind: RuleKind = RuleKind.PROPERTY
    check: str | None = None          # commande ou identifiant de verification
    negative_case: str | None = None  # entree qui DOIT echouer

    def __post_init__(self) -> None:
        if not self.id or not self.statement:
            raise ValueError("Rule.id et Rule.statement sont obligatoires")


@dataclass(frozen=True)
class Spec:
    """Une mission decomposee en regles.</br>

    `under_specified` liste ce qui n'a PAS pu etre converti en regle verifiable.
    Ce champ est essentiel : il rend visible ce qu'on ne saura pas prouver.
    """

    mission: str
    rules: tuple[Rule, ...] = ()
    under_specified: tuple[str, ...] = ()
    acceptance: int = 0  # nombre de regles a satisfaire, 0 = toutes

    @property
    def required(self) -> int:
        return self.acceptance or len(self.rules)

    def rule(self, rule_id: str) -> Rule:
        for r in self.rules:
            if r.id == rule_id:
                return r
        raise KeyError(rule_id)


# --------------------------------------------------------------------------- #
# Preuves
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Witness:
    """Une preuve exécutable. Sans temoin, une affirmation n'existe pas.

    `output_hash` lie la preuve a une sortie precise : on ne peut pas la
    substituer apres coup sans casser la chaine.
    """

    rule_id: str
    command: str
    exit_code: int
    ok: bool
    stdout: str = ""
    stderr: str = ""
    duration_s: float = 0.0
    artefacts: tuple[str, ...] = ()

    @property
    def output_hash(self) -> str:
        blob = f"{self.exit_code}\x00{self.stdout}\x00{self.stderr}"
        return hashlib.sha256(blob.encode("utf-8", "replace")).hexdigest()[:16]

    def summary(self, limit: int = 400) -> str:
        out = (self.stdout or self.stderr or "").strip().replace("\n", " | ")
        if len(out) > limit:
            out = out[:limit] + "…"
        return f"[{self.rule_id}] exit={self.exit_code} ok={self.ok} {out}"


@dataclass(frozen=True)
class Claim:
    """Une affirmation atomique, avec sa provenance.

    Aucun claim ne circule sans `evidence`. Un claim sans preuve est
    traite comme FAUX par le garde fail-closed.
    """

    text: str
    evidence: tuple[str, ...] = ()
    source: str = ""
    trust: TrustLevel = TrustLevel.EXTERNAL

    @property
    def grounded(self) -> bool:
        return bool(self.evidence)

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("Claim.text vide")


# --------------------------------------------------------------------------- #
# Artefacts et candidats
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Artifact:
    """Un livrable proposé par un agent."""

    id: str
    content: str
    kind: str = "text"          # text | code | patch | report
    path: str | None = None
    agent: str = ""
    model: str = ""
    provider: str = ""
    attempt: int = 1
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def digest(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8", "replace")).hexdigest()[:16]


@dataclass(frozen=True)
class FailureFeedback:
    """Retour d'echec STRUCTURE (Levier 5 du harness — +5 a 10 pts).

    Un echec n'est jamais renvoye comme du texte brut : chaque champ aide
    l'agent a se corriger precisement.
    """

    stage: Stage
    rule_id: str | None = None
    command: str = ""
    exit_code: int | None = None
    assertion: str = ""
    file: str | None = None
    line: int | None = None
    message: str = ""
    repeated: bool = False  # ce meme echec s'est deja produit

    def render(self) -> str:
        parts = [f"stage={self.stage.value}"]
        if self.rule_id:
            parts.append(f"rule={self.rule_id}")
        if self.command:
            parts.append(f"cmd={self.command}")
        if self.exit_code is not None:
            parts.append(f"exit={self.exit_code}")
        if self.file:
            loc = self.file + (f":{self.line}" if self.line else "")
            parts.append(f"at={loc}")
        if self.assertion:
            parts.append(f"assert={self.assertion}")
        if self.message:
            parts.append(f"msg={self.message}")
        if self.repeated:
            parts.append("NOTE=erreur identique deja rencontree — change d'approche")
        return " | ".join(parts)


# --------------------------------------------------------------------------- #
# Votes, consensus, audit
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Vote:
    """Vote d'un agent. Les votes sont secrets les uns des autres.

    Interdiction de la pression sociale : « Conformity Breaks Conformal
    Prediction » montre que la conformite fait chuter la couverture de 90% a 74%.
    """

    agent: str
    decision: Verdict
    confidence: float = 0.5
    rationale: str = ""
    rule_id: str | None = None
    model: str = ""
    provider: str = ""

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("Vote.confidence doit etre dans [0, 1]")


@dataclass(frozen=True)
class Finding:
    """Constat d'audit."""

    agent: str
    severity: Severity
    message: str
    rule_id: str | None = None
    evidence: str = ""
    counterexample: str | None = None

    @property
    def blocking(self) -> bool:
        return self.severity.rank >= Severity.HIGH.rank


@dataclass(frozen=True)
class Blame:
    """Attribution d'un echec au premier pas fautif.

    Localisation par recherche binaire de prefixe en O(log T), puis
    distinction tentative-de-reparation / pas-aligne-sur-l-echec.
    """

    agent: str
    step: int
    message: str
    is_repair_attempt: bool = False


@dataclass(frozen=True)
class Verdict_:
    """Resultat agrege d'un tour de boucle."""

    stage: Stage
    verdict: Verdict
    witnesses: tuple[Witness, ...] = ()
    findings: tuple[Finding, ...] = ()
    votes: tuple[Vote, ...] = ()
    consensus_reached: bool = False
    dissent: tuple[str, ...] = ()
    confidence: float = 0.0

    @property
    def blocked(self) -> bool:
        return any(f.blocking for f in self.findings)


# --------------------------------------------------------------------------- #
# Integrite
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Exploit:
    """Un exploit detecte dans le journal (rejeu deterministe)."""

    kind: ExploitKind
    step: int
    detail: str
    evidence: str = ""
    confidence: float = 0.6


@dataclass(frozen=True)
class IntegrityReport:
    exploits: tuple[Exploit, ...] = ()
    replay_digest: str = ""
    steps: int = 0

    @property
    def clean(self) -> bool:
        return not self.exploits

    @property
    def worst(self) -> Severity:
        if not self.exploits:
            return Severity.INFO
        if any(e.kind in _CRITICAL_EXPLOITS for e in self.exploits):
            return Severity.CRITICAL
        return Severity.HIGH


_CRITICAL_EXPLOITS = frozenset(
    {ExploitKind.TAMPERING, ExploitKind.LEAKAGE, ExploitKind.SEQUENCE}
)


# --------------------------------------------------------------------------- #
# Mission
# --------------------------------------------------------------------------- #


@dataclass
class Mission:
    """Une mission soumise au systeme."""

    objective: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    workspace: str = "."
    deadline_s: float | None = None
    risk: Severity = Severity.MEDIUM
    alpha: float = 0.05          # risque d'erreur accepte (ConformalGate)
    max_rounds: int = 5
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise ValueError("Mission.objective vide")
        if not 0.0 < self.alpha < 1.0:
            raise ValueError("Mission.alpha doit etre dans ]0, 1[")


@dataclass(frozen=True)
class MissionReport:
    """Resultat final d'une mission. C'est le contrat de sortie."""

    mission_id: str
    objective: str
    status: MissionStatus
    subject: str = ""                 # l'artefact final
    spec: Spec | None = None
    rounds: int = 0
    witnesses: tuple[Witness, ...] = ()
    findings: tuple[Finding, ...] = ()
    votes: tuple[Vote, ...] = ()
    blames: tuple[Blame, ...] = ()
    integrity: IntegrityReport = field(default_factory=IntegrityReport)
    abstention_reason: str = ""
    journal_digest: str = ""
    duration_s: float = 0.0
    usage: Mapping[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> int:
        return sum(1 for w in self.witnesses if w.ok)

    @property
    def total_checks(self) -> int:
        return len(self.witnesses)

    def to_json(self) -> str:
        return json.dumps(_report_to_dict(self), ensure_ascii=False, indent=2, default=str)


def _report_to_dict(r: MissionReport) -> dict[str, Any]:
    spec = r.spec
    return {
        "mission_id": r.mission_id,
        "objective": r.objective,
        "status": r.status.value,
        "subject": r.subject[:2000],
        "rounds": r.rounds,
        "witnesses": [
            {
                "rule": w.rule_id,
                "command": w.command,
                "exit_code": w.exit_code,
                "ok": w.ok,
                "hash": w.output_hash,
            }
            for w in r.witnesses
        ],
        "findings": [
            {
                "agent": f.agent,
                "severity": f.severity.value,
                "message": f.message,
                "rule": f.rule_id,
                "counterexample": f.counterexample,
            }
            for f in r.findings
        ],
        "votes": [
            {
                "agent": v.agent,
                "decision": v.decision.value,
                "confidence": v.confidence,
                "reason": v.rationale,
            }
            for v in r.votes
        ],
        "blames": [
            {"agent": b.agent, "step": b.step, "message": b.message,
             "repair_attempt": b.is_repair_attempt}
            for b in r.blames
        ],
        "integrity": {
            "clean": r.integrity.clean,
            "steps": r.integrity.steps,
            "exploits": [
                {
                    "kind": e.kind.value,
                    "step": e.step,
                    "detail": e.detail,
                    "confidence": e.confidence,
                }
                for e in r.integrity.exploits
            ],
        },
        "spec": {
            "rules": [
                {"id": x.id, "statement": x.statement, "kind": x.kind.value}
                for x in (spec.rules if spec else ())
            ],
            "under_specified": list(spec.under_specified) if spec else [],
        },
        "abstention_reason": r.abstention_reason,
        "journal_digest": r.journal_digest,
        "duration_s": round(r.duration_s, 3),
        "checks_passed": r.passed,
        "checks_total": r.total_checks,
        "usage": dict(r.usage),
    }


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #


def now() -> float:
    return time.time()


def canonical(obj: Any) -> str:
    """Serialisation canonique — indispensable pour des hashes stables."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def digest_of(*parts: Any) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(canonical(p).encode("utf-8", "replace"))
        h.update(b"\x1f")
    return h.hexdigest()


def as_sequence(value: Sequence[Any] | None) -> tuple[Any, ...]:
    return tuple(value) if value is not None else ()
