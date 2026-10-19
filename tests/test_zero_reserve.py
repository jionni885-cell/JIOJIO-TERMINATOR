from types import SimpleNamespace

from jio.cli import _abstention_sans_reserve, _activer_unanimite, build_parser
from jio.core.types import MissionReport, MissionStatus


class JournalFactice:
    head = "head-initial"

    def __init__(self):
        self.events = []

    def append(self, kind, payload):
        self.events.append((kind, payload))
        self.head = "head-after-policy"


def test_zero_reserve_requires_unanimous_panel_agreement():
    engine = SimpleNamespace(consensus=SimpleNamespace(threshold=2 / 3))
    _activer_unanimite(engine)
    assert engine.consensus.threshold == 1.0


def test_zero_reserve_is_exposed_as_a_run_option():
    args = build_parser().parse_args(["run", "objectif", "--zero-reserve"])
    assert args.zero_reserve is True


def test_zero_reserve_converts_known_uncertainty_to_abstention():
    journal = JournalFactice()
    report = MissionReport(
        mission_id="mission",
        objective="objectif",
        status=MissionStatus.DELIVERED_WITH_RESERVATION,
        abstention_reason="specification partielle",
    )

    result = _abstention_sans_reserve(report, journal)

    assert result.status is MissionStatus.ABSTAINED
    assert "POLITIQUE ZERO-RESERVE" in result.abstention_reason
    assert result.journal_digest == "head-after-policy"
    assert journal.events[0][0] == "strict_proof_abstention"
    assert journal.events[0][1]["from"] == "delivered_with_reservation"


def test_zero_reserve_does_not_rewrite_clean_or_already_abstained_reports():
    journal = JournalFactice()
    clean = MissionReport("clean", "objectif", MissionStatus.DELIVERED)
    abstained = MissionReport("abstained", "objectif", MissionStatus.ABSTAINED)

    assert _abstention_sans_reserve(clean, journal) is clean
    assert _abstention_sans_reserve(abstained, journal) is abstained
    assert journal.events == []
