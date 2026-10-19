"""Portable, privacy-conscious receipts for verified JIO missions.

A receipt is an export of selected journal facts, not a certificate of truth or
an identity signature. It refuses broken source journals, avoids exporting raw
prompts/code/vote rationales by default, and carries hashes so accidental edits
can be detected later.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections import defaultdict
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from ..core.journal import Event, Journal

SCHEMA_VERSION = 1
_HASH = re.compile(r"^[0-9a-f]{64}$")


class ReceiptError(ValueError):
    """A receipt cannot be produced safely from the supplied source."""


def _canonical(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical(value)).hexdigest()


def _payloads(events: tuple[Event, ...], kind: str) -> list[dict[str, Any]]:
    return [dict(event.payload) for event in events if event.kind == kind]


def _count(value: object, default: int = 0) -> int:
    return (
        value
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
        else default
    )


def build_receipt(
    journal_text: str | bytes,
    *,
    source_name: str = "journal.jsonl",
    include_objective: bool = False,
) -> dict[str, Any]:
    """Build a redacted receipt for the last mission in a valid hash-chained journal."""
    if isinstance(journal_text, bytes):
        source_bytes = journal_text
        try:
            decoded = journal_text.decode("utf-8")
        except UnicodeError as exc:
            raise ReceiptError(f"journal UTF-8 illisible : {exc}") from exc
    elif isinstance(journal_text, str):
        decoded = journal_text
        source_bytes = journal_text.encode("utf-8")
    else:
        raise ReceiptError("journal attendu en texte UTF-8 ou en octets")
    try:
        journal = Journal.from_jsonl(decoded)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ReceiptError(f"journal illisible : {exc}") from exc
    if not len(journal):
        raise ReceiptError("journal vide : aucune mission a attester")
    valid, bad_index = journal.verify_chain()
    if not valid:
        raise ReceiptError(f"chaine du journal cassee a l'evenement {bad_index}")

    events = tuple(journal)
    mission_indexes = [i for i, event in enumerate(events) if event.kind == "mission"]
    if not mission_indexes:
        raise ReceiptError("aucun evenement mission dans le journal")
    start = mission_indexes[-1]
    run = events[start:]
    mission_event = events[start]
    mission = dict(mission_event.payload)
    kinds: dict[str, int] = defaultdict(int)
    for event in run:
        kinds[event.kind] += 1

    witness_events = _payloads(run, "witness")
    by_rule: dict[str, dict[str, int]] = defaultdict(
        lambda: {"runs": 0, "passed": 0, "failed": 0}
    )
    evidence_hashes: set[str] = set()
    for witness in witness_events:
        rule = str(witness.get("rule", "unknown"))[:80]
        counts = by_rule[rule]
        counts["runs"] += 1
        counts["passed" if witness.get("ok") is True else "failed"] += 1
        digest = witness.get("hash")
        if isinstance(digest, str) and _HASH.fullmatch(digest):
            evidence_hashes.add(digest)

    spec_stage = next(
        (
            dict(event.payload)
            for event in run
            if event.kind == "stage" and dict(event.payload).get("name") == "spec"
        ),
        {},
    )
    final_stage = next(
        (
            dict(event.payload)
            for event in reversed(run)
            if event.kind == "stage" and dict(event.payload).get("name") == "generate"
        ),
        {},
    )
    reflection = next(
        (payload for payload in reversed(_payloads(run, "task_reflection"))), {}
    )
    verdict = next((p for p in reversed(_payloads(run, "verdict"))), {})
    consensus = next((p for p in reversed(_payloads(run, "consensus"))), {})
    gate = next((p for p in reversed(_payloads(run, "gate"))), {})
    integrity = next((p for p in reversed(_payloads(run, "integrity"))), {})
    mutation = next((p for p in reversed(_payloads(run, "mutation"))), {})
    route = next((p for p in reversed(_payloads(run, "route"))), {})
    candidates = _payloads(run, "candidate")

    result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "source": {
            "file": Path(source_name).name,
            "sha256": hashlib.sha256(source_bytes).hexdigest(),
            "chain_valid": True,
            "chain_head": journal.head,
            "event_count": len(events),
            "mission_event_count": len(mission_indexes),
        },
        "mission": {
            "id": str(mission.get("id", ""))[:100],
            "started_at": mission_event.ts,
            "risk": str(mission.get("risk", ""))[:40],
            "alpha": mission.get("alpha"),
            "objective_sha256": str(reflection.get("objective_sha256", ""))[:64],
        },
        "review": {
            "role_count": _count(reflection.get("role_count")),
            "reflection_version": reflection.get("reflection_version"),
            "role_plan_sha256": _digest(
                {
                    "objective_sha256": reflection.get("objective_sha256", ""),
                    "role_prompt_sha256": reflection.get("role_prompt_sha256", {}),
                }
            )
            if reflection
            else "",
        },
        "specification": {
            "rule_ids": [
                str(rule)[:80]
                for rule in spec_stage.get("rules", [])
                if isinstance(rule, str)
            ],
            "under_specified_count": len(spec_stage.get("under_specified", []))
            if isinstance(spec_stage.get("under_specified", []), list)
            else None,
        },
        "execution": {
            "rounds": max(
                0,
                1
                + max(
                    [
                        int(p.get("round", -1))
                        for p in _payloads(run, "stage")
                        if isinstance(p.get("round"), int)
                        and not isinstance(p.get("round"), bool)
                    ],
                    default=-1,
                ),
            ),
            "candidate_count": len(candidates),
            "models": sorted(
                {
                    str(p["model"])[:100]
                    for p in candidates
                    if isinstance(p.get("model"), str) and p.get("model")
                }
            ),
            "route": {
                key: route[key]
                for key in ("arm", "candidates", "rounds", "panel_size", "cost")
                if key in route
            },
            "best_artifact_sha256": str(final_stage.get("best_digest", ""))[:64],
        },
        "evidence": {
            "all_attempts": {
                "executions": len(witness_events),
                "passed": sum(1 for p in witness_events if p.get("ok") is True),
                "failed": sum(1 for p in witness_events if p.get("ok") is not True),
                "by_rule": dict(sorted(by_rule.items())),
                "output_sha256": sorted(evidence_hashes),
                "scope_note": "aggregat de tous les essais journalises, pas seulement du candidat final",
            },
            "final_artifact": {
                "rules_passed": verdict.get("passed"),
                "rules_total": verdict.get("total"),
                "ratio": verdict.get("ratio"),
            },
        },
        "consensus": {
            key: consensus[key]
            for key in (
                "decision",
                "reached",
                "agreement",
                "decorrelation",
                "panel",
                "quorum",
            )
            if key in consensus
        },
        "gate": {
            key: gate[key]
            for key in ("accepted", "confidence", "tau", "calibrated")
            if key in gate
        },
        "mutation": {
            key: mutation[key]
            for key in ("total", "killed", "score")
            if key in mutation
        },
        "integrity": {
            "clean": integrity.get("clean"),
            "steps": integrity.get("steps"),
            "exploit_count": len(integrity.get("exploits", []))
            if isinstance(integrity.get("exploits", []), list)
            else None,
        },
        "verdict": {
            "status": str(verdict.get("status", "incomplete"))[:80],
            "passed": verdict.get("passed"),
            "total": verdict.get("total"),
            "ratio": verdict.get("ratio"),
            "has_reservation_or_abstention": bool(
                verdict.get("abstention") or verdict.get("reason")
            ),
        },
        "event_counts": dict(sorted(kinds.items())),
        "limits": [
            "Le journal est integre; cela ne prouve pas la verite du resultat.",
            "Ce recu n'est pas signe : son SHA-256 detecte une modification seulement si son empreinte est conservee a part.",
            "Le recu exclut les prompts complets, le code source, les sorties de commande et les motifs libres.",
        ],
    }
    if include_objective:
        result["mission"]["objective"] = str(mission.get("objective", ""))
    result["receipt_sha256"] = _digest(result)
    return result


def verify_receipt(value: str | bytes | Mapping[str, Any]) -> tuple[bool, str]:
    """Check the receipt's canonical digest; does not authenticate its author."""
    try:
        if isinstance(value, bytes):
            document = json.loads(value.decode("utf-8"))
        elif isinstance(value, str):
            document = json.loads(value)
        else:
            document = dict(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError) as exc:
        return False, f"recu illisible : {exc}"
    if (
        not isinstance(document, dict)
        or document.get("schema_version") != SCHEMA_VERSION
    ):
        return False, "version ou format de recu non pris en charge"
    expected = document.get("receipt_sha256")
    if not isinstance(expected, str) or not _HASH.fullmatch(expected):
        return False, "empreinte du recu absente ou invalide"
    unsigned = dict(document)
    unsigned.pop("receipt_sha256", None)
    actual = _digest(unsigned)
    if actual != expected:
        return False, "empreinte du recu incorrecte"
    return True, actual


def render_markdown(receipt: Mapping[str, Any]) -> str:
    """Readable export that preserves the same privacy and evidence limits."""
    mission = receipt["mission"]
    evidence = receipt["evidence"]
    attempts = evidence["all_attempts"]
    final = evidence["final_artifact"]
    verdict = receipt["verdict"]
    lines = [
        "# Recu de verification JIO",
        "",
        f"- **Verdict :** `{verdict['status']}`",
        f"- **Candidat final :** {final['rules_passed']}/{final['rules_total']} regles passees",
        f"- **Essais journalises (tous candidats) :** {attempts['passed']} passes, {attempts['failed']} echoues",
        f"- **Regles :** {len(receipt['specification']['rule_ids'])}",
        f"- **Chaine du journal :** integre · `{receipt['source']['chain_head']}`",
        f"- **SHA-256 du recu :** `{receipt['receipt_sha256']}`",
    ]
    if mission.get("objective"):
        lines.extend(["", f"**Mission :** {mission['objective']}"])
    lines.extend(["", "## Limites", ""])
    lines.extend(f"- {limit}" for limit in receipt["limits"])
    lines.append("")
    return "\n".join(lines)


__all__ = ["ReceiptError", "build_receipt", "render_markdown", "verify_receipt"]
