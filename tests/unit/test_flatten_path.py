"""The flatten path - the code that closes a live position, and has never executed (ZR-36).

`flatten_positions` is reachable exactly one way today: `SessionActor` publishes
`flatten_signal` at session blackout and `strategies/base.py:_on_session_phase` calls it. It
raises `TypeError` the moment it runs, because `self.cancel_all_orders()` is called with no
argument while NautilusTrader 1.229.0 declares
`cancel_all_orders(self, InstrumentId instrument_id, ...)` with no default
(`trading/strategy.pxd:162`).

Nobody noticed because the function early-returns FLATTEN_SKIPPED unless the strategy is
IN_POSITION or PENDING_ENTRY, and no test had ever put one there. The guard hid the bug: the
suite exercised the path that returns, never the path that acts.

These tests put a strategy in a position on purpose. The first is `xfail(strict=True)` rather
than an assertion that the bug exists - a characterisation test asserting `pytest.raises(
TypeError)` would enshrine broken behaviour as expected. Strict xfail instead **fails when the
bug is fixed**, forcing whoever fixes it to delete the marker and state what the call should
pass. See `docs/killswitch_plan.md` H3: what `instrument_id` to pass is exactly the unresolved
combo-versus-legs question, so the fix belongs with that design, not here.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from nautilus_zerodte.journal.service import Journal
from nautilus_zerodte.models.enums import StrategyState
from nautilus_zerodte.strategies.reference import (
    ReferenceZeroDteStrategy,
    ReferenceZeroDteStrategyConfig,
)


def _strategy(tmp_path: Path) -> ReferenceZeroDteStrategy:
    """An unregistered strategy - enough to drive the FSM without an engine."""
    return ReferenceZeroDteStrategy(
        ReferenceZeroDteStrategyConfig(
            journal_path=str(tmp_path / "journal.jsonl"),
            backtest_plumbing=True,
            dry_run=True,
        )
    )


@pytest.mark.xfail(
    strict=True,
    reason=(
        "ZR-36: flatten_positions calls self.cancel_all_orders() with no instrument_id, "
        "which NT 1.229.0 requires positionally. Remove this marker when the fix lands and "
        "assert what the call passes instead."
    ),
)
def test_flatten_positions_runs_when_in_position(tmp_path: Path) -> None:
    """The one path that closes a live position. It raises today.

    Deliberately does NOT set `_active_intent_id`, so `submit_exit` is never reached and the
    only thing under test is the cancel. If this test starts passing, the flatten path executes
    for the first time and the strict marker will say so loudly.
    """
    strategy = _strategy(tmp_path)
    strategy._state = StrategyState.IN_POSITION

    strategy.flatten_positions(reason="session_blackout")


def test_flatten_is_skipped_and_journalled_when_flat(tmp_path: Path) -> None:
    """The guard that hid the bug - assert it, so it stays a guard and not an accident.

    A strategy that is FLAT must journal FLATTEN_SKIPPED with its state and reason and return
    without touching the venue. This is the branch the suite has always taken; pinning it means
    a future change cannot quietly make the early return unreachable and route every caller
    into the raising path.
    """
    journal_path = tmp_path / "journal.jsonl"
    strategy = _strategy(tmp_path)
    assert strategy._state is StrategyState.FLAT

    strategy.flatten_positions(reason="session_blackout")

    entries = Journal.load(journal_path)
    skipped = [e for e in entries if e.payload.get("event") == "FLATTEN_SKIPPED"]
    assert len(skipped) == 1, f"expected exactly one FLATTEN_SKIPPED, got {len(skipped)}"
    assert skipped[0].payload["state"] == StrategyState.FLAT.value
    assert skipped[0].payload["reason"] == "session_blackout"


def test_only_in_position_and_pending_entry_reach_the_venue(tmp_path: Path) -> None:
    """Pin which states act and which return - the boundary the bug hides behind.

    IN_POSITION and PENDING_ENTRY must reach `cancel_all_orders` (and therefore raise today);
    every other state must journal FLATTEN_SKIPPED instead. Asserted as a relation over the
    whole enum rather than a list of names, so adding a state forces a decision here rather
    than silently defaulting to "does not flatten".
    """
    acts = {StrategyState.IN_POSITION, StrategyState.PENDING_ENTRY}

    for state in StrategyState:
        strategy = _strategy(tmp_path / state.value)
        strategy._state = state
        if state in acts:
            with pytest.raises(TypeError):
                strategy.flatten_positions(reason="probe")
        else:
            strategy.flatten_positions(reason="probe")
            entries = Journal.load(Path(tmp_path / state.value) / "journal.jsonl")
            assert any(e.payload.get("event") == "FLATTEN_SKIPPED" for e in entries), (
                f"{state.value} neither acted nor journalled a skip"
            )
