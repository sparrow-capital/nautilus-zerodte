from __future__ import annotations

from datetime import UTC, datetime

from nautilus_zerodte.actors.data_types import (
    TradeIntentApprovedSnapshot,
    TradeIntentSnapshot,
    approved_snapshot_to_trade_intent,
    snapshot_to_trade_intent,
    trade_intent_to_snapshot,
)
from nautilus_zerodte.actors.regime import compute_regime_tag
from nautilus_zerodte.actors.session import (
    minutes_to_close,
    parse_close_time,
    session_allows_entry,
    session_phase_label,
)
from nautilus_zerodte.models.enums import RegimeTag


def test_session_allows_entry_outside_blackout() -> None:
    close = parse_close_time("21:00")
    now = datetime(2024, 1, 2, 14, 30, 0, tzinfo=UTC)
    assert minutes_to_close(now, close) == 390
    assert session_allows_entry(now, close, blackout_minutes_before_close=30) is True
    assert session_phase_label(True) == "NORMAL"


def test_session_blocks_entry_in_blackout() -> None:
    close = parse_close_time("14:45")
    now = datetime(2024, 1, 2, 14, 30, 0, tzinfo=UTC)
    assert minutes_to_close(now, close) == 15
    assert session_allows_entry(now, close, blackout_minutes_before_close=30) is False
    assert session_phase_label(False) == "BLACKOUT"


def test_regime_trend_on_large_move() -> None:
    tag = compute_regime_tag(
        402.5,
        open_price=400.0,
        recent_prices=[400.0, 401.0, 402.0, 402.5],
        trend_move_pct=0.005,
        chop_range_pct=0.002,
        pin_strike_proximity_pct=0.0001,
    )
    assert tag == RegimeTag.TREND


def test_regime_chop_on_tight_range() -> None:
    tag = compute_regime_tag(
        400.05,
        open_price=400.0,
        recent_prices=[400.0, 400.1, 400.05, 400.08, 400.02],
        trend_move_pct=0.05,
        chop_range_pct=0.002,
        pin_strike_proximity_pct=0.0001,
    )
    assert tag == RegimeTag.CHOP


def test_regime_zero_mid_skips_chop_without_error() -> None:
    tag = compute_regime_tag(
        0.0,
        open_price=None,
        recent_prices=[0.0, 0.0, 0.0, 0.0, 0.0],
        trend_move_pct=0.005,
        chop_range_pct=0.002,
        pin_strike_proximity_pct=0.001,
    )
    assert tag == RegimeTag.UNKNOWN


def test_trade_intent_snapshot_round_trip() -> None:
    from uuid import uuid4

    from nautilus_zerodte.models.trade_intent import TradeIntent

    intent = TradeIntent(
        intent_id=uuid4(),
        strategy_id="ref-001",
        instrument_id="SPY.NYSE",
        edge_after_cost_bps=12.5,
        liquidity_score=0.9,
        projected_greeks={"delta": 0.1},
        rationale={"notional": 5000},
    )
    snapshot = trade_intent_to_snapshot(intent)
    restored = snapshot_to_trade_intent(snapshot)
    assert restored == intent


def test_trade_intent_approved_snapshot_round_trip() -> None:
    from uuid import uuid4

    from nautilus_zerodte.models.enums import RegimeTag
    from nautilus_zerodte.models.trade_intent import TradeIntent

    intent = TradeIntent(
        intent_id=uuid4(),
        strategy_id="ref-001",
        instrument_id="SPY.NYSE",
        edge_after_cost_bps=12.5,
        regime_tag=RegimeTag.CHOP,
        projected_greeks={"vega": 1.2},
    )
    snapshot = TradeIntentSnapshot(
        intent_id=str(intent.intent_id),
        strategy_id=intent.strategy_id,
        instrument_id=intent.instrument_id,
        edge_after_cost_bps=intent.edge_after_cost_bps,
        liquidity_score=intent.liquidity_score,
        regime_tag=intent.regime_tag.value,
        projected_greeks=dict(intent.projected_greeks),
        rationale=dict(intent.rationale),
    )
    approved = TradeIntentApprovedSnapshot(
        intent_id=snapshot.intent_id,
        strategy_id=snapshot.strategy_id,
        instrument_id=snapshot.instrument_id,
        edge_after_cost_bps=snapshot.edge_after_cost_bps,
        liquidity_score=snapshot.liquidity_score,
        regime_tag=snapshot.regime_tag,
        projected_greeks=snapshot.projected_greeks,
        rationale=snapshot.rationale,
        actor_kind="HUMAN",
    )
    restored = approved_snapshot_to_trade_intent(approved)
    assert restored.intent_id == intent.intent_id
    assert restored.regime_tag == RegimeTag.CHOP
