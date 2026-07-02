from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite
from typing import Any, Protocol


@dataclass(frozen=True)
class SpreadStructure:
    """Venue-neutral selected spread structure ready for order submission."""

    spread_instrument_id: str
    low_strike: float
    high_strike: float
    edge_after_cost_bps: float
    liquidity_score: float
    leg_instrument_ids: tuple[str, ...] = ()
    rationale: dict[str, Any] = field(default_factory=dict)


class StructureSelector(Protocol):
    """Select a vertical spread structure from an option chain snapshot."""

    def select_from_chain(
        self,
        option_chain_slice,
        *,
        strike_width: int,
        min_edge_after_cost_bps: float,
        min_liquidity_score: float,
    ) -> SpreadStructure | None: ...


@dataclass(frozen=True)
class QuoteSpreadLiquidity:
    mid: float
    spread_bps: float
    liquidity_score: float


def quote_spread_liquidity(
    *,
    bid: float | None,
    ask: float | None,
    fallback_mid: float | None = None,
    invalid_spread_bps: float = 100.0,
    invalid_liquidity_score: float = 0.0,
) -> QuoteSpreadLiquidity:
    """
    Compute mid, spread (bps), and a [0..1] liquidity score.

    Behavior is intentionally conservative: invalid/missing prices yield
    spread_bps=100.0 and liquidity_score=0.0 (matching existing callers).
    """
    bid_v = float(bid or 0.0)
    ask_v = float(ask or 0.0)

    if bid_v > 0.0 and ask_v > 0.0 and isfinite(bid_v) and isfinite(ask_v):
        mid = (bid_v + ask_v) / 2.0
        spread_bps = ((ask_v - bid_v) / mid) * 10_000.0 if mid > 0.0 else 100.0
        liquidity = 1.0 - spread_bps / 100.0
        return QuoteSpreadLiquidity(
            mid=mid,
            spread_bps=spread_bps,
            liquidity_score=max(0.0, min(1.0, liquidity)),
        )

    mid = float(fallback_mid or 0.0)
    return QuoteSpreadLiquidity(
        mid=mid,
        spread_bps=float(invalid_spread_bps),
        liquidity_score=float(invalid_liquidity_score),
    )


def strike_price(strike: float):
    """Shared strike -> Nautilus Price helper (venue-neutral)."""
    from nautilus_trader.model.data import nautilus_pyo3

    return nautilus_pyo3.Price.from_str(f"{float(strike):.2f}")
