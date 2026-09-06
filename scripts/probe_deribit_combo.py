#!/usr/bin/env python3
"""Probe how Deribit books a combo position (ZR-21).

    uv run python scripts/probe_deribit_combo.py                 # public phase, no credentials
    uv run python scripts/probe_deribit_combo.py --authenticated # adds the decisive sweep

READ-ONLY BY CONSTRUCTION. This script can only issue GETs against `public/*` and three
read-only `private/*` endpoints. There is no code path here that places, amends or cancels an
order, and none should ever be added - if you need the testnet order probe, do it by hand
through the API console so that a human is deliberately in the loop.

The public phase needs nothing and corroborates the answer. The authenticated phase is the
decisive one and needs a Deribit key with `trade:read`; it reads your own trade history and
positions and writes nothing. Credentials come from the environment, are never logged, and are
never written to disk.

Phase 3, deliberately NOT automated: if the account has never filled a combo, the sweep is
silent. Settle it on TESTNET by hand - buy 0.1 of an open combo with a distinctive `label`,
then re-run this with --testnet --authenticated. The label matters: whether the per-leg trade
inherits the parent combo order's label is itself unresolved, and it decides whether the bug
is silent non-flatten or nondeterministic legging-out.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "src"))

from nautilus_zerodte.research.combo_probe import (  # noqa: E402
    PUBLIC_API,
    TESTNET_API,
    build_public_evidence,
    interpret_positions,
    interpret_public_evidence,
    parse_legs,
    short_legs_first,
)

_TIMEOUT = 20


def _get(base: str, path: str, token: str | None = None, **params) -> dict:
    """One GET. The only network primitive in this file, and it cannot POST."""
    url = f"{base}/{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, method="GET")
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:  # noqa: S310
        return json.loads(response.read())


def _bearer(base: str) -> str | None:
    key = os.environ.get("DERIBIT_TESTNET_API_KEY" if "test." in base else "DERIBIT_API_KEY")
    secret = os.environ.get(
        "DERIBIT_TESTNET_API_SECRET" if "test." in base else "DERIBIT_API_SECRET"
    )
    if not key or not secret:
        return None
    auth = _get(
        base,
        "public/auth",
        grant_type="client_credentials",
        client_id=key,
        client_secret=secret,
        scope="session:probe trade:read",
    )
    return auth.get("result", {}).get("access_token")


def _pick_combo(base: str, currency: str, prefer: str) -> tuple[str, dict]:
    instruments = _get(base, "public/get_instruments", currency=currency, kind="option_combo")
    rows = [i for i in instruments.get("result", []) if i.get("state") == "open"]
    if not rows:
        raise SystemExit(f"no open option_combo instruments for {currency}")
    match = [i for i in rows if f"-{prefer}-" in i["instrument_name"]]
    chosen = (match or rows)[0]
    return chosen["instrument_name"], {"result": chosen}


def public_phase(base: str, currency: str, prefer: str) -> tuple[str, tuple]:
    combo_name, combo_instrument = _pick_combo(base, currency, prefer)
    details = _get(base, "public/get_combo_details", combo_id=combo_name)
    legs = parse_legs(details)
    evidence = build_public_evidence(
        combo_name=combo_name,
        combo_details=details,
        combo_ticker=_get(base, "public/ticker", instrument_name=combo_name),
        leg_tickers={
            leg.instrument_name: _get(base, "public/ticker", instrument_name=leg.instrument_name)
            for leg in legs
        },
        combo_instrument=combo_instrument,
    )
    leaning, reasons = interpret_public_evidence(evidence)

    print(f"\n=== PUBLIC PHASE - {combo_name} ===")
    print(
        f"  commissions: maker={evidence.combo_maker_commission} taker={evidence.combo_taker_commission}"
    )
    print("  legs (venue order):")
    for leg in legs:
        print(
            f"    {leg.instrument_name:32s} amount {leg.amount:+d} {'SHORT' if leg.is_short else 'long'}"
        )
    print("  unwind order (short legs first, D12):")
    for leg in short_legs_first(legs):
        print(f"    {leg.instrument_name}")
    print(f"\n  {'instrument':34s} {'open_interest':>14} {'settlement_price':>18} {'mark_iv':>10}")
    rows = [(combo_name, evidence.combo_fields)] + list(evidence.leg_fields.items())
    for name, fields in rows:
        oi = fields.get("open_interest")
        sp = fields.get("settlement_price")
        iv = fields.get("mark_iv")
        print(
            f"  {name:34s} {('ABSENT' if oi is None else oi)!s:>14} "
            f"{('ABSENT' if sp is None else sp)!s:>18} {('ABSENT' if iv is None else iv)!s:>10}"
        )
    print(f"\n  LEANING: {leaning}  (public data corroborates; it cannot settle this outright)")
    for reason in reasons:
        print(f"    - {reason}")
    return combo_name, tuple(leg.instrument_name for leg in legs)


def authenticated_phase(base: str, currency: str, combo_name: str, leg_names: tuple) -> None:
    token = _bearer(base)
    if not token:
        env = "DERIBIT_TESTNET_API_KEY/SECRET" if "test." in base else "DERIBIT_API_KEY/SECRET"
        print(f"\n=== AUTHENTICATED PHASE - SKIPPED ===\n  {env} not set. This phase is the")
        print("  decisive one; the public phase above only corroborates.")
        return

    print("\n=== AUTHENTICATED PHASE (read-only) ===")
    trades = _get(
        base,
        "private/get_user_trades_by_currency",
        token,
        currency=currency,
        kind="combo",
        count=10,
    ).get("result", {})
    combo_trades = trades.get("trades", trades if isinstance(trades, list) else [])
    print(f"  combo trades found: {len(combo_trades)}")

    unfiltered = _get(base, "private/get_positions", token, currency=currency).get("result", [])
    combo_kind = _get(
        base, "private/get_positions", token, currency=currency, kind="option_combo"
    ).get("result", [])

    print(
        f"  positions (no filter): {len(unfiltered)} -> {[p.get('instrument_name') for p in unfiltered]}"
    )
    print(f"  positions (kind=option_combo): {len(combo_kind)}")

    answer, why = interpret_positions(
        combo_name=combo_name,
        positions_unfiltered=unfiltered,
        positions_combo_kind=combo_kind,
        combo_leg_names=leg_names,
    )
    print(f"\n  ANSWER: {answer}\n  {why}")
    if answer == "combo":
        print(
            "\n  *** This overturns decisions D11-D13. Stop and re-read docs/killswitch_plan.md H3."
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--currency", default="BTC")
    parser.add_argument(
        "--prefer", default="CS", help="combo type to prefer, e.g. CS for a call spread"
    )
    parser.add_argument("--testnet", action="store_true")
    parser.add_argument(
        "--authenticated", action="store_true", help="add the decisive read-only sweep"
    )
    args = parser.parse_args()

    base = TESTNET_API if args.testnet else PUBLIC_API
    combo_name, leg_names = public_phase(base, args.currency, args.prefer)
    if args.authenticated:
        authenticated_phase(base, args.currency, combo_name, leg_names)
    else:
        print("\n  (run with --authenticated for the decisive sweep; needs a trade:read key)")


if __name__ == "__main__":
    main()
