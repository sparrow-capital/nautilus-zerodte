from __future__ import annotations

import json
from pathlib import Path

from nautilus_zerodte.journal.service import Journal, gate_rejection_report, journal_overview
from nautilus_zerodte.models.enums import GateStage


def test_journal_record_and_persist(tmp_path: Path) -> None:
    journal_path = tmp_path / "test.jsonl"
    journal = Journal(journal_path)
    journal.record(
        GateStage.LIFECYCLE,
        payload={"event": "NODE_START"},
    )
    journal.record(
        GateStage.LIFECYCLE,
        payload={"event": "STRATEGY_START"},
        strategy_id="skeleton-001",
    )
    assert len(journal.entries) == 2
    assert journal_path.exists()

    loaded = Journal.load(journal_path)
    assert len(loaded) == 2
    assert loaded[1].strategy_id == "skeleton-001"


def test_journal_summary(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "test.jsonl")
    journal.record(GateStage.LIFECYCLE, payload={"event": "NODE_START"})
    journal.record(GateStage.SESSION, payload={"passed": False})
    summary = journal.summary()
    assert summary["total"] == 2
    assert summary["stage_counts"]["LIFECYCLE"] == 1
    assert summary["stage_counts"]["SESSION"] == 1


def test_journal_jsonl_is_valid_json(tmp_path: Path) -> None:
    journal_path = tmp_path / "test.jsonl"
    journal = Journal(journal_path)
    journal.record(GateStage.LIFECYCLE, payload={"event": "NODE_START"})
    with journal_path.open() as handle:
        line = handle.readline()
    parsed = json.loads(line)
    assert parsed["stage"] == "LIFECYCLE"
    assert parsed["payload"]["event"] == "NODE_START"


def test_gate_rejection_report_aggregates(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "report.jsonl")
    journal.record(
        GateStage.EDGE,
        payload={"event": "GATE_REJECT", "breached_rules": ["min_edge", "min_liquidity"]},
    )
    journal.record(
        GateStage.RISK_ENGINE,
        payload={"event": "ORDER_DENIED", "breached_rules": ["max_delta"]},
    )
    journal.record(GateStage.LIFECYCLE, payload={"event": "NODE_START"})

    report = gate_rejection_report(Journal.load(journal.path))
    assert report.total == 2
    assert report.by_stage["EDGE"] == 1
    assert report.by_stage["RISK_ENGINE"] == 1
    assert report.by_rule["min_edge"] == 1
    assert report.by_rule["max_delta"] == 1


def test_journal_overview_aggregates(tmp_path: Path) -> None:
    journal = Journal(tmp_path / "summary.jsonl")
    journal.record(GateStage.LIFECYCLE, payload={"event": "NODE_START"}, strategy_id="a")
    journal.record(GateStage.EDGE, payload={"event": "GATE_REJECT"}, strategy_id="a")

    overview = journal_overview(Journal.load(journal.path))
    assert overview.total == 2
    assert overview.strategies == frozenset({"a"})
    assert overview.gate_rejections["EDGE"] == 1
    assert len(overview.last_entries) == 2
