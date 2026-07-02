from __future__ import annotations

from uuid import uuid4

from nautilus_zerodte.actors.data_types import (
    TRADE_INTENT_APPROVED_TOPIC,
    TRADE_INTENT_REJECTED_TOPIC,
)
from nautilus_zerodte.actors.selector import SelectorActor, SelectorActorConfig
from nautilus_zerodte.models.trade_intent import TradeIntent


class _FakeMsgBus:
    def __init__(self) -> None:
        self.published: list[tuple[str, object]] = []

    def publish(self, topic: str, msg: object) -> None:
        self.published.append((topic, msg))


class _TestSelectorActor(SelectorActor):
    def __init__(self, config: SelectorActorConfig, *, msgbus: _FakeMsgBus) -> None:
        super().__init__(config)
        self._test_msgbus = msgbus

    @property  # type: ignore[override]
    def msgbus(self) -> _FakeMsgBus:  # type: ignore[override]
        return self._test_msgbus


def _intent(*, strategy_id: str, instrument_id: str, edge: float) -> TradeIntent:
    return TradeIntent(
        intent_id=uuid4(),
        strategy_id=strategy_id,
        instrument_id=instrument_id,
        edge_after_cost_bps=edge,
        liquidity_score=0.9,
    )


def test_selector_actor_finalize_publishes_approved_and_rejected(tmp_path) -> None:
    fake_bus = _FakeMsgBus()
    actor = _TestSelectorActor(
        SelectorActorConfig(
            journal_path=str(tmp_path / "journal.jsonl"),
            diversification={"top_n": 2, "max_per_instrument": 1, "max_per_strategy": 1.0},
            approval={"human_edge_bps_threshold": 9999.0, "human_notional_threshold": 9999.0},
        ),
        msgbus=fake_bus,
    )

    # Force one reject (max_per_instrument=1) and one approval.
    actor._buffer = [
        _intent(strategy_id="a", instrument_id="SPY-1", edge=10.0),
        _intent(strategy_id="b", instrument_id="SPY-1", edge=20.0),
    ]
    routed = actor.finalize()
    assert len(routed) == 1

    topics = [t for (t, _msg) in fake_bus.published]
    assert TRADE_INTENT_REJECTED_TOPIC in topics
    assert TRADE_INTENT_APPROVED_TOPIC in topics
