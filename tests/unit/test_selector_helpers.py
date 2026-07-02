from __future__ import annotations

import inspect

from nautilus_zerodte.strategies.reference import ReferenceZeroDteStrategy
from nautilus_zerodte.strategies.selectors.base import quote_spread_liquidity


def test_quote_spread_liquidity_valid_prices() -> None:
    metrics = quote_spread_liquidity(bid=10.0, ask=12.0)
    assert metrics.mid == 11.0
    assert metrics.spread_bps == ((12.0 - 10.0) / 11.0) * 10_000
    assert 0.0 <= metrics.liquidity_score <= 1.0


def test_quote_spread_liquidity_invalid_defaults() -> None:
    metrics = quote_spread_liquidity(bid=0.0, ask=0.0, fallback_mid=123.0)
    assert metrics.mid == 123.0
    assert metrics.spread_bps == 100.0
    assert metrics.liquidity_score == 0.0


def test_quote_spread_liquidity_invalid_override() -> None:
    metrics = quote_spread_liquidity(
        bid=0.0,
        ask=0.0,
        fallback_mid=50.0,
        invalid_spread_bps=0.0,
        invalid_liquidity_score=1.0,
    )
    assert metrics.mid == 50.0
    assert metrics.spread_bps == 0.0
    assert metrics.liquidity_score == 1.0


def test_reference_strategy_does_not_import_deribit_private_strike_helper() -> None:
    source = inspect.getsource(ReferenceZeroDteStrategy._context_from_selection)
    assert "selectors.deribit" not in source
