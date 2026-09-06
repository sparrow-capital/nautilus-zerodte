"""Evidence gathering for how Deribit books a combo position (ZR-21).

The question: when an order on a combo instrument fills, does the account end up with ONE
position on the combo, or TWO positions on the individual option legs? It decides the design
of the emergency flatten - see `docs/killswitch_plan.md` H3 and decisions D11-D13.

This module is READ-ONLY BY CONSTRUCTION. It contains no code that can place, amend or cancel
an order, and it never imports an execution client. It belongs in `research/` because it is
offline diagnostic tooling and never runs on the order path (T6).

The interpretation functions below are pure and take already-fetched payloads, so the whole
decision procedure is testable without a network (`docs/testing.md`: no network in tests).

NOTE - venue containment. Hard rule 1 confines venue specifics to `node/adapters/`, `costs/`,
`strategies/selectors/` and `configs/`. This module is Deribit-specific and sits outside them.
`scripts/build_deribit_catalog_fixture.py` is already in the same position, so the rule as
written does not cover diagnostic tooling. Rather than quietly widen it, the tension is
recorded here and raised for a decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PUBLIC_API = "https://www.deribit.com/api/v2"
TESTNET_API = "https://test.deribit.com/api/v2"

# Deribit reports these per instrument. Their presence on a leg and absence on the combo is the
# core public evidence: open interest IS the count of outstanding positions in an instrument.
_EVIDENCE_FIELDS = ("open_interest", "settlement_price", "mark_iv")


@dataclass(frozen=True, slots=True)
class LegSpec:
    """One leg of a combo. `amount` carries direction: positive long, negative short."""

    instrument_name: str
    amount: int

    @property
    def is_short(self) -> bool:
        return self.amount < 0


@dataclass(frozen=True, slots=True)
class PublicEvidence:
    """What the public endpoints say about a combo versus its own legs."""

    combo_name: str
    legs: tuple[LegSpec, ...]
    combo_fields: dict[str, Any]
    leg_fields: dict[str, dict[str, Any]]
    combo_maker_commission: float | None
    combo_taker_commission: float | None

    @property
    def combo_has_open_interest(self) -> bool:
        return self.combo_fields.get("open_interest") is not None

    @property
    def legs_have_open_interest(self) -> bool:
        return bool(self.leg_fields) and all(
            f.get("open_interest") is not None for f in self.leg_fields.values()
        )

    @property
    def negative_mark_iv(self) -> float | None:
        """A negative implied vol is impossible, and marks combo greeks as untrustworthy."""
        iv = self.combo_fields.get("mark_iv")
        return iv if isinstance(iv, int | float) and iv < 0 else None


def parse_legs(combo_details: dict[str, Any]) -> tuple[LegSpec, ...]:
    """Legs from `public/get_combo_details`, preserving venue order."""
    legs = combo_details.get("result", combo_details).get("legs", [])
    return tuple(
        LegSpec(instrument_name=leg["instrument_name"], amount=int(leg["amount"])) for leg in legs
    )


def short_legs_first(legs: tuple[LegSpec, ...]) -> tuple[LegSpec, ...]:
    """Unwind order: buy back short legs before selling long ones (D12).

    Closing a long leg first can leave a naked short call - unbounded. This is a hard ordering
    rule, not an optimisation, and it is deliberately stable: legs of equal sign keep their
    venue order so an unwind is reproducible across runs (T2).
    """
    return tuple(sorted(legs, key=lambda leg: (0 if leg.is_short else 1,)))


def _fields(ticker: dict[str, Any]) -> dict[str, Any]:
    result = ticker.get("result", ticker)
    return {name: result.get(name) for name in _EVIDENCE_FIELDS}


def build_public_evidence(
    *,
    combo_name: str,
    combo_details: dict[str, Any],
    combo_ticker: dict[str, Any],
    leg_tickers: dict[str, dict[str, Any]],
    combo_instrument: dict[str, Any] | None = None,
) -> PublicEvidence:
    instrument = (combo_instrument or {}).get("result", combo_instrument or {})
    return PublicEvidence(
        combo_name=combo_name,
        legs=parse_legs(combo_details),
        combo_fields=_fields(combo_ticker),
        leg_fields={name: _fields(t) for name, t in leg_tickers.items()},
        combo_maker_commission=instrument.get("maker_commission"),
        combo_taker_commission=instrument.get("taker_commission"),
    )


def interpret_public_evidence(evidence: PublicEvidence) -> tuple[str, list[str]]:
    """Return (leaning, reasons). Public data cannot settle this outright - see the docstring.

    Leaning is "legs", "combo", or "inconclusive". Public endpoints do not expose position
    keeping directly, so this is corroboration; only the authenticated sweep is decisive.
    """
    reasons: list[str] = []
    for_legs = 0

    if evidence.legs_have_open_interest and not evidence.combo_has_open_interest:
        for_legs += 1
        reasons.append(
            "open interest is reported on every leg but not on the combo - open interest is "
            "the count of outstanding positions, so the positions are on the legs"
        )
    elif evidence.combo_has_open_interest:
        reasons.append(
            "the combo reports open interest, which would mean positions are held on it - "
            "this contradicts the expected answer and must be investigated before relying on it"
        )
        return "combo", reasons

    if evidence.combo_fields.get("settlement_price") is None and any(
        f.get("settlement_price") is not None for f in evidence.leg_fields.values()
    ):
        for_legs += 1
        reasons.append(
            "legs carry a settlement price and the combo does not - there is no settlement "
            "process for a combo"
        )

    if evidence.combo_taker_commission == 0.0 and evidence.combo_maker_commission == 0.0:
        for_legs += 1
        reasons.append(
            "the combo charges zero maker and taker commission while its legs are fee-bearing - "
            "fees are charged where the position is booked"
        )

    if (iv := evidence.negative_mark_iv) is not None:
        reasons.append(
            f"SEPARATE FINDING (ZR-25): combo mark_iv is {iv}, a negative implied volatility. "
            "Combo-level derived fields are not meaningful and must not feed a risk limit."
        )

    if for_legs == 0:
        return "inconclusive", reasons
    return "legs", reasons


def interpret_positions(
    *,
    combo_name: str,
    positions_unfiltered: list[dict[str, Any]],
    positions_combo_kind: list[dict[str, Any]],
    combo_leg_names: tuple[str, ...],
) -> tuple[str, str]:
    """The decisive test, over authenticated `private/get_positions` payloads.

    Returns (answer, why) where answer is "legs", "combo", or "inconclusive". Inconclusive is a
    real outcome: if the account has never filled a combo, the sweep is silent and proves
    nothing - which is why it must be reported rather than read as evidence for either side.
    """
    names = {p.get("instrument_name") for p in positions_unfiltered}
    legs_present = [n for n in combo_leg_names if n in names]

    if combo_name in names or any(
        p.get("kind") in {"option_combo", "future_combo"} for p in positions_combo_kind
    ):
        return (
            "combo",
            f"a position named {combo_name} (or of a combo kind) is present - the venue books "
            "the combo itself, and the flatten design must be revisited",
        )
    if legs_present:
        return (
            "legs",
            f"leg positions present ({', '.join(legs_present)}) with no combo-named row and an "
            "empty kind=option_combo response - the venue books the legs",
        )
    return (
        "inconclusive",
        "no combo-named position and no leg positions either - this account has probably never "
        "filled this combo, so the sweep proves nothing. Use the testnet probe instead.",
    )
