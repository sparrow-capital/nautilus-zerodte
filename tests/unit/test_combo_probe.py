"""Offline tests for the ZR-21 combo probe.

Every payload below is REAL, captured from Deribit's public API on 2026-09-06, so these pin the
shapes the venue actually returns rather than shapes we imagined. No network here - the probe's
fetching is a thin shell over these pure functions (docs/testing.md: no network in tests, ever).
"""

from __future__ import annotations

from nautilus_zerodte.research.combo_probe import (
    LegSpec,
    build_public_evidence,
    interpret_positions,
    interpret_public_evidence,
    parse_legs,
    short_legs_first,
)

# --- real captured payloads, BTC-CS-11SEP26-84000_86000 and its legs -----------------------

COMBO = "BTC-CS-11SEP26-84000_86000"
LONG_LEG = "BTC-11SEP26-84000-C"
SHORT_LEG = "BTC-11SEP26-86000-C"

COMBO_DETAILS = {
    "result": {
        "id": COMBO,
        "state": "active",
        "legs": [
            {"instrument_name": LONG_LEG, "amount": 1},
            {"instrument_name": SHORT_LEG, "amount": -1},
        ],
    }
}

# The combo ticker genuinely omits these keys - it does not return them as null.
COMBO_TICKER = {"result": {"mark_iv": -3.23}}
LEG_TICKERS = {
    LONG_LEG: {
        "result": {"open_interest": 1398.4, "settlement_price": 0.00283752, "mark_iv": 38.82}
    },
    SHORT_LEG: {
        "result": {"open_interest": 1503.2, "settlement_price": 0.00135292, "mark_iv": 42.05}
    },
}
COMBO_INSTRUMENT = {"result": {"maker_commission": 0.0, "taker_commission": 0.0, "state": "open"}}


def _evidence(**overrides):
    kwargs = {
        "combo_name": COMBO,
        "combo_details": COMBO_DETAILS,
        "combo_ticker": COMBO_TICKER,
        "leg_tickers": LEG_TICKERS,
        "combo_instrument": COMBO_INSTRUMENT,
    }
    kwargs.update(overrides)
    return build_public_evidence(**kwargs)


def test_parses_legs_with_direction_from_the_sign() -> None:
    legs = parse_legs(COMBO_DETAILS)
    assert legs == (LegSpec(LONG_LEG, 1), LegSpec(SHORT_LEG, -1))
    assert legs[1].is_short and not legs[0].is_short


def test_short_leg_is_unwound_first() -> None:
    """D12, and the reason the whole design exists.

    Closing the long 84000 call first leaves a naked short 86000 call - unbounded loss, in an
    emergency. This ordering must hold whatever order the venue lists legs in.
    """
    venue_order = parse_legs(COMBO_DETAILS)
    assert venue_order[0].instrument_name == LONG_LEG, "fixture no longer lists long first"

    ordered = short_legs_first(venue_order)
    assert ordered[0].instrument_name == SHORT_LEG
    assert ordered[0].is_short


def test_short_leg_first_is_stable_for_equal_signs() -> None:
    """T2: two runs must unwind in the same order, so the sort cannot be arbitrary."""
    legs = (LegSpec("A", 1), LegSpec("B", -1), LegSpec("C", -1), LegSpec("D", 1))
    assert [leg.instrument_name for leg in short_legs_first(legs)] == ["B", "C", "A", "D"]


def test_public_evidence_leans_legs_on_the_real_payloads() -> None:
    leaning, reasons = interpret_public_evidence(_evidence())
    assert leaning == "legs"
    assert any("open interest" in r for r in reasons)
    assert any("settlement price" in r for r in reasons)
    assert any("commission" in r for r in reasons)


def test_combo_with_open_interest_is_reported_as_contradicting() -> None:
    """The falsifying case must not be swallowed.

    If the combo ever reports open interest, that is evidence AGAINST the working answer, and
    reading it as anything else is the confirmation bias this probe exists to avoid.
    """
    leaning, reasons = interpret_public_evidence(
        _evidence(combo_ticker={"result": {"open_interest": 42.0}})
    )
    assert leaning == "combo"
    assert any("contradicts" in r for r in reasons)


def test_negative_mark_iv_is_surfaced_as_a_separate_finding() -> None:
    _, reasons = interpret_public_evidence(_evidence())
    assert any("negative implied volatility" in r for r in reasons)
    assert any("ZR-25" in r for r in reasons)


def test_positions_showing_legs_is_the_decisive_legs_answer() -> None:
    answer, why = interpret_positions(
        combo_name=COMBO,
        positions_unfiltered=[
            {"instrument_name": LONG_LEG, "kind": "option"},
            {"instrument_name": SHORT_LEG, "kind": "option"},
        ],
        positions_combo_kind=[],
        combo_leg_names=(LONG_LEG, SHORT_LEG),
    )
    assert answer == "legs"
    assert LONG_LEG in why


def test_positions_showing_a_combo_row_overturns_the_design() -> None:
    answer, _ = interpret_positions(
        combo_name=COMBO,
        positions_unfiltered=[{"instrument_name": COMBO, "kind": "option_combo"}],
        positions_combo_kind=[{"instrument_name": COMBO, "kind": "option_combo"}],
        combo_leg_names=(LONG_LEG, SHORT_LEG),
    )
    assert answer == "combo"


def test_empty_positions_is_inconclusive_not_confirmation() -> None:
    """Silence is not evidence. An account that never traded the combo proves nothing."""
    answer, why = interpret_positions(
        combo_name=COMBO,
        positions_unfiltered=[{"instrument_name": "BTC-PERPETUAL", "kind": "future"}],
        positions_combo_kind=[],
        combo_leg_names=(LONG_LEG, SHORT_LEG),
    )
    assert answer == "inconclusive"
    assert "proves nothing" in why
