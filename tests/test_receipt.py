from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from jio.core.journal import Journal
from jio.verify.receipt import (
    ReceiptError,
    build_receipt,
    render_markdown,
    verify_receipt,
)


def _journal() -> Journal:
    journal = Journal()
    journal.append(
        "mission",
        {
            "id": "m-1",
            "objective": "PRIVATE OBJECTIVE SENTINEL",
            "risk": "low",
            "alpha": 0.05,
        },
    )
    journal.append(
        "task_reflection",
        {
            "reflection_version": 1,
            "objective_sha256": "a" * 64,
            "role_count": 4,
            "agent_roles": ["brief_interpreter", "specialist_tests"],
            "role_prompt_sha256": {"specialist_tests": "b" * 64},
        },
    )
    journal.append(
        "stage",
        {"name": "spec", "rules": ["R-001", "R-002"], "under_specified": []},
    )
    journal.append(
        "candidate",
        {
            "id": "r0-c0",
            "digest": "c" * 64,
            "model": "sim-test",
            "code_tail": "PRIVATE CODE SENTINEL",
        },
    )
    journal.append(
        "witness",
        {
            "rule": "R-001",
            "ok": True,
            "hash": "d" * 64,
            "command": "PRIVATE COMMAND SENTINEL",
            "stage": "prove",
        },
    )
    journal.append(
        "witness",
        {"rule": "R-001", "ok": False, "hash": "e" * 64, "stage": "prove"},
    )
    journal.append(
        "consensus",
        {
            "decision": "pass",
            "reached": True,
            "agreement": 1.0,
            "decorrelation": 0.8,
            "panel": 4,
            "quorum": 3,
            "reason": "PRIVATE RATIONALE SENTINEL",
        },
    )
    journal.append(
        "gate", {"accepted": True, "confidence": 0.91, "tau": 0.8, "calibrated": True}
    )
    journal.append("integrity", {"clean": True, "steps": 4, "exploits": []})
    journal.append(
        "verdict",
        {
            "status": "delivered",
            "passed": 2,
            "total": 2,
            "ratio": 1.0,
            "abstention": "",
        },
    )
    return journal


def test_receipt_redacts_free_text_and_exports_minimal_evidence() -> None:
    journal = _journal()
    receipt = build_receipt(
        journal.to_jsonl(), source_name="/private/path/journal.jsonl"
    )
    encoded = json.dumps(receipt, ensure_ascii=False)

    assert receipt["source"]["chain_valid"] is True
    assert receipt["source"]["file"] == "journal.jsonl"
    assert receipt["verdict"]["status"] == "delivered"
    assert receipt["evidence"]["final_artifact"] == {
        "rules_passed": 2,
        "rules_total": 2,
        "ratio": 1.0,
    }
    assert receipt["evidence"]["all_attempts"]["passed"] == 1
    assert receipt["evidence"]["all_attempts"]["failed"] == 1
    assert receipt["evidence"]["all_attempts"]["by_rule"]["R-001"]["runs"] == 2
    for sentinel in (
        "PRIVATE OBJECTIVE SENTINEL",
        "PRIVATE CODE SENTINEL",
        "PRIVATE COMMAND SENTINEL",
        "PRIVATE RATIONALE SENTINEL",
    ):
        assert sentinel not in encoded


def test_objective_inclusion_is_explicit_opt_in() -> None:
    receipt = build_receipt(_journal().to_jsonl(), include_objective=True)
    assert receipt["mission"]["objective"] == "PRIVATE OBJECTIVE SENTINEL"


def test_receipt_hash_detects_edits_but_does_not_claim_authenticity() -> None:
    receipt = build_receipt(_journal().to_jsonl())
    valid, digest = verify_receipt(receipt)
    assert valid and digest == receipt["receipt_sha256"]

    changed = dict(receipt)
    changed["verdict"] = {**receipt["verdict"], "status": "invented"}
    valid, reason = verify_receipt(changed)
    assert not valid
    assert "empreinte" in reason


def test_broken_journal_is_refused() -> None:
    text = _journal().to_jsonl().replace("PRIVATE OBJECTIVE SENTINEL", "tampered")
    with pytest.raises(ReceiptError, match="cassee"):
        build_receipt(text)


def test_receipt_selects_only_the_last_mission() -> None:
    journal = Journal()
    journal.append("mission", {"id": "first", "objective": "first"})
    journal.append("verdict", {"status": "abstained", "passed": 0, "total": 1})
    journal.append("mission", {"id": "second", "objective": "second"})
    journal.append("verdict", {"status": "delivered", "passed": 1, "total": 1})

    receipt = build_receipt(journal.to_jsonl())
    assert receipt["mission"]["id"] == "second"
    assert receipt["event_counts"]["mission"] == 1
    assert receipt["verdict"]["status"] == "delivered"


def test_markdown_names_final_candidate_separately_from_all_attempts() -> None:
    receipt = build_receipt(_journal().to_jsonl())
    rendered = render_markdown(receipt)
    assert "2/2 regles passees" in rendered
    assert "tous candidats" in rendered


def test_receipt_rejects_empty_or_nonmission_journal() -> None:
    with pytest.raises(ReceiptError, match="vide"):
        build_receipt("")
    journal = Journal()
    journal.append("stage", {"name": "spec"})
    with pytest.raises(ReceiptError, match="aucun evenement mission"):
        build_receipt(journal.to_jsonl())


def test_source_digest_covers_exact_input_bytes() -> None:
    raw = _journal().to_jsonl().replace("\n", "\r\n").encode("utf-8")
    receipt = build_receipt(raw)
    assert receipt["source"]["sha256"] == hashlib.sha256(raw).hexdigest()


def test_cli_exports_and_verifies_receipt(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    journal_path = tmp_path / "journal.jsonl"
    receipt_path = tmp_path / "receipt.json"
    journal_path.write_text(_journal().to_jsonl(), encoding="utf-8")

    created = subprocess.run(
        [
            sys.executable,
            "-m",
            "jio",
            "receipt",
            str(journal_path),
            "--format",
            "json",
            "--output",
            str(receipt_path),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert created.returncode == 0, created.stderr
    assert (
        json.loads(receipt_path.read_text(encoding="utf-8"))["verdict"]["status"]
        == "delivered"
    )

    verified = subprocess.run(
        [sys.executable, "-m", "jio", "receipt", "--verify", str(receipt_path)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert verified.returncode == 0
    assert "VALIDE" in verified.stdout

    receipt_path.write_text(
        receipt_path.read_text(encoding="utf-8").replace(
            '"status": "delivered"', '"status": "abstained"'
        ),
        encoding="utf-8",
    )
    tampered = subprocess.run(
        [sys.executable, "-m", "jio", "receipt", "--verify", str(receipt_path)],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )
    assert tampered.returncode == 1
    assert "INVALIDE" in tampered.stdout
