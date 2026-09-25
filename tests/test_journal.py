"""Tests du journal hash-chaine — la colonne vertebrale d'integrite."""

from __future__ import annotations


from jio.core.journal import GENESIS, Journal
from jio.core.types import TrustLevel


def test_journal_starts_at_genesis():
    j = Journal()
    assert j.head == GENESIS
    assert len(j) == 0


def test_journal_chains_hashes():
    j = Journal()
    a = j.append("mission", {"id": "m1"})
    b = j.append("stage", {"name": "spec"})
    assert a.prev_hash == GENESIS
    assert b.prev_hash == a.digest
    assert j.head == b.digest
    ok, bad = j.verify_chain()
    assert ok and bad is None


def test_journal_detects_tampering():
    """Modifier un payload apres coup DOIT casser la chaine."""
    j = Journal()
    j.append("witness", {"rule": "R-001", "ok": True})
    j.append("verdict", {"status": "delivered"})
    assert j.verify_chain()[0]

    # Falsification : on reecrit la preuve d'un echec en succes.
    events = list(j)
    object.__setattr__(events[0], "payload", {"rule": "R-001", "ok": False})

    ok, bad = j.verify_chain()
    assert not ok
    assert bad == 0


def test_journal_replay_roundtrip():
    j = Journal()
    for i in range(5):
        j.append("step", {"i": i})
    clone = Journal.from_jsonl(j.to_jsonl())
    assert len(clone) == len(j)
    assert clone.head == j.head
    assert clone.verify_chain()[0]


def test_journal_records_trust_level():
    j = Journal()
    j.append("read", {"path": "README.md"}, trust=TrustLevel.EXTERNAL)
    assert list(j)[0].trust is TrustLevel.EXTERNAL
    assert "external" in j.to_jsonl()


def test_journal_summary_counts_kinds():
    j = Journal()
    j.append("a")
    j.append("a")
    j.append("b")
    s = j.summary()
    assert s["events"] == 3
    assert s["kinds"] == {"a": 2, "b": 1}
    assert s["chain_ok"] is True


def test_journal_persists_to_disk(tmp_path):
    path = tmp_path / "journal.jsonl"
    j = Journal(path=path)
    j.append("mission", {"x": 1})
    assert path.exists()
    assert "\"x\": 1" in path.read_text(encoding="utf-8")
    reloaded = Journal.from_jsonl(path.read_text(encoding="utf-8"))
    assert reloaded.verify_chain()[0]
