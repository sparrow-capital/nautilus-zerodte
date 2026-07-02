from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import UUID

from dataclasses import dataclass

from nautilus_zerodte.models.enums import GateStage
from nautilus_zerodte.models.journal import JournalEntry

_REPORT_GATE_STAGES = {
    GateStage.EDGE,
    GateStage.LIQUIDITY,
    GateStage.REGIME,
    GateStage.SESSION,
    GateStage.GREEK,
    GateStage.OPERATIONAL,
    GateStage.RISK_ENGINE,
}

_SUMMARY_GATE_STAGES = {
    GateStage.EDGE,
    GateStage.LIQUIDITY,
    GateStage.REGIME,
    GateStage.SESSION,
    GateStage.GREEK,
    GateStage.OPERATIONAL,
}


@dataclass(frozen=True, slots=True)
class GateRejectionReport:
    by_stage: dict[str, int]
    by_rule: dict[str, int]

    @property
    def total(self) -> int:
        return sum(self.by_stage.values())


@dataclass(frozen=True, slots=True)
class JournalOverview:
    stage_counts: dict[str, int]
    gate_rejections: dict[str, int]
    strategies: frozenset[str]
    last_entries: tuple[JournalEntry, ...]

    @property
    def total(self) -> int:
        return sum(self.stage_counts.values())


def gate_rejection_report(entries: list[JournalEntry]) -> GateRejectionReport:
    """Aggregate gate rejections and order denials by stage and breached rule."""
    by_stage: dict[str, int] = {}
    by_rule: dict[str, int] = {}

    for entry in entries:
        if entry.stage not in _REPORT_GATE_STAGES:
            continue
        if entry.payload.get("event") not in {"GATE_REJECT", "ORDER_DENIED"}:
            continue
        by_stage[entry.stage.value] = by_stage.get(entry.stage.value, 0) + 1
        for rule in entry.payload.get("breached_rules", []):
            by_rule[str(rule)] = by_rule.get(str(rule), 0) + 1

    return GateRejectionReport(by_stage=by_stage, by_rule=by_rule)


def journal_overview(entries: list[JournalEntry]) -> JournalOverview:
    """Summarize journal entries by stage, gate rejections, and recent tail."""
    stage_counts: dict[str, int] = {}
    gate_rejections: dict[str, int] = {}
    strategies: set[str] = set()

    for entry in entries:
        stage_counts[entry.stage.value] = stage_counts.get(entry.stage.value, 0) + 1
        if entry.strategy_id:
            strategies.add(entry.strategy_id)
        if entry.stage in _SUMMARY_GATE_STAGES and entry.payload.get("event") == "GATE_REJECT":
            gate_rejections[entry.stage.value] = gate_rejections.get(entry.stage.value, 0) + 1

    return JournalOverview(
        stage_counts=stage_counts,
        gate_rejections=gate_rejections,
        strategies=frozenset(strategies),
        last_entries=tuple(entries[-10:]),
    )


class Journal:
    """Append-only audit log with in-memory index and JSONL persistence."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._entries: list[JournalEntry] = []

    @property
    def entries(self) -> list[JournalEntry]:
        return list(self._entries)

    def record(
        self,
        stage: GateStage,
        ref_id: UUID | None = None,
        payload: dict[str, Any] | None = None,
        *,
        strategy_id: str | None = None,
        level: str = "INFO",
    ) -> JournalEntry:
        entry = JournalEntry(
            stage=stage,
            ref_id=ref_id,
            strategy_id=strategy_id,
            level=level,
            payload=payload or {},
        )
        self._entries.append(entry)
        self._append_jsonl(entry)
        return entry

    def _append_jsonl(self, entry: JournalEntry) -> None:
        line = entry.model_dump(mode="json")
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(line, default=str) + "\n")

    @classmethod
    def load(cls, path: Path | str) -> list[JournalEntry]:
        journal_path = Path(path)
        if not journal_path.exists():
            return []
        entries: list[JournalEntry] = []
        with journal_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                entries.append(JournalEntry.model_validate_json(line))
        return entries

    def summary(self) -> dict[str, Any]:
        stage_counts: dict[str, int] = {}
        for entry in self._entries:
            stage_counts[entry.stage.value] = stage_counts.get(entry.stage.value, 0) + 1
        return {
            "total": len(self._entries),
            "stage_counts": stage_counts,
            "last_entries": [e.model_dump(mode="json") for e in self._entries[-10:]],
        }
