# Execution: fills, costs, and settlement

How a modelled trade becomes a modelled fill, and why the defaults are unflattering on purpose.

Read this before touching `costs/`, the backtest fee or fill model, or any edge calculation.

---

## 1. The fill model (T9)

**In 0DTE options the fill model is the single largest manufacturer of fake edge.** The quoted
spread on OTM strikes is routinely a large fraction of premium, displayed size is small, and a
resting order fills precisely in the states where you wish it had not. A backtest that gets the
signal right and the fill model wrong will look excellent and lose money.

Rules:

1. **Cross the spread.** Aggressive fills at the far touch. Mid-price fills are forbidden.
2. **Cap at displayed size**, then apply a participation cap as a fraction of displayed size.
   Requesting more than is shown produces a partial fill, not a larger one at the same price.
3. **No maker fills in backtest without a queue-position model.** Assuming passive fills means
   assuming you were at the front of the queue and that nothing informed traded through you.
   Both assumptions are wrong in the direction that flatters you. If a maker model is added, it
   models queue position and adverse selection explicitly, or it does not ship.
4. **Walk the book for size** rather than filling the whole clip at the touch.
5. **When two modelling choices are defensible, take the worse one.** Where a parameter is
   uncertain, stress it (`docs/quant/evaluation.md` section 6).

## 2. The cost model (T7)

The fee schedule, spread cost, and slippage assumption used by the pre-trade edge gate are the
**same numbers** wired into the backtest fee model. One source, `configs/fees/`, consumed by both.
Separate constants for gate and backtest is a defect, not a convenience.

Current pre-trade form, from `costs/deribit.py`:

```
edge_after_cost_bps = edge_before_cost_bps
                    - half_spread_bps
                    - expected_slippage_bps
                    - expected_commission_bps
```

Deribit specifics that must stay in the model:

- **Fees are charged on the underlying notional, not the premium**, and are capped as a fraction
  of the option price. A naive premium-based fee model understates cost on cheap OTM options by a
  large factor, which is precisely where a 0DTE strategy spends most of its time.
- **Taker for IOC entries, maker only if a queue model exists.** `entry_liquidity` in the fee
  schedule selects the rate; it must match what the fill model actually assumed.
- **Combo and multi-leg orders are charged per leg.** A spread costs two legs, not one. Confirmed
  live on 2026-09-06 from the venue side: the `option_combo` instrument itself reports **zero
  maker and zero taker commission** while its leg instruments are fee-bearing. A cost model that
  reads the fee off the combo instrument would therefore price a spread at zero, which is
  precisely the flattering direction. Read fees from the legs, always.
- **Delivery and settlement fees** apply to positions held to expiry, which for 0DTE is the normal
  case rather than the exception.
- **The perpetual hedge leg has its own fee and its own funding**, and both belong in the edge
  calculation, not just in attribution.

Reconciliation is a regression, not a mean: `edge_realized ~ a + b * edge_predicted`, requiring
`a` near zero and `b` near one. Details and rationale in `docs/quant/attribution.md` section 4.2.

## 3. Settlement and expiry mechanics

0DTE means almost every position reaches expiry, so settlement is the normal path and must be
modelled correctly.

- **Options settle against a time-averaged index print at expiry, not the last quote.** Confirm
  the current Deribit specification for the averaging window and encode it; marking an expiring
  position at last traded or last quoted price misprices every single expiry in the backtest.
- **Deribit BTC and ETH options expire at 08:00 UTC.** `configs/session/crypto_deribit.yaml` and
  the `market_close_utc` field carry this. It is a venue fact, so it lives in config, never in
  core code.
- **Pin risk is real.** A position at or near the strike at settlement has an uncertain outcome
  that a mid-price mark will not show. Model the settlement outcome, not the mark.
- **Settlement is coin-denominated.** The payout arrives in BTC and its USD value depends on the
  settlement print, which is the same cross term described in
  `docs/quant/attribution.md` section 3.
- **The blackout window before expiry** (`blackout_minutes_before_close`) exists because
  liquidity thins and spreads widen into settlement. It is a risk control, not a convenience, and
  changing it is a decision that belongs in `docs/decisions.md`.

## 3.5 Closing a combo, and what the venue and the engine will not do for you

Added 2026-09-06 from Deribit combo research. **All of this describes constraints on a path that
is not built.** The redesign lives in H3 of `docs/killswitch_plan.md`, the decisions are D11 to
D13, and the operator kill switch remains NOT IMPLEMENTED (`docs/quant/risk.md` section 1).

- **A combo close is a LIMIT order, not a market order.** `private/close_position` accepts only
  `type` `limit|market`, NautilusTrader's Deribit adapter implements **no `close_position` method
  at all** (the string appears only in a rate-limit bucket), and Deribit's knowledge base states
  option combos support the limit type only. That KB sentence is **second-hand**
  (support.deribit.com returns 403 to both WebFetch and curl) and is in tension with the
  normative API reference, which excludes only the trigger types for combos
  ("stop_limit, stop_market, take_limit, take_market, and trailing_stop ... are not supported for
  option and option_combo instruments"). One of the two is wrong. We design for limit-only
  because that is the assumption that is safe if it turns out to be the wrong one, which means an
  aggressive reduce-only limit through the implied touch plus a **bounded** reprice loop - an
  unbounded reprice on a 0DTE combo is a market order with no ceiling.
- **The combo book can disappear.** Deribit deactivates low-volume combo books (soft and hard
  caps, **error 13035**) into FIX `SecurityStatus 3`, "inactive (no new orders, edits, or
  cancellations)", and the changelog says clients cannot even subscribe to a non-open instrument.
  Any close path that only knows how to trade the combo has no exit when this happens. A
  leg-by-leg fallback is mandatory, and it closes the short leg first (D12).
- **A leg-level cancel does not cancel combo orders.** `private/cancel_all_by_instrument` defaults
  `include_combos=false`. Cancel on the combo explicitly, or set the flag.
- **Load the leg instruments alongside the combos.** The adapter drops a user trade whose
  `instrument_name` is not in its instrument cache, with a warning and nothing else. Combos
  without legs means silently lost fills.
- **The instrument object does not know its own legs.** `CryptoOptionSpread` carries
  `strategy_type` and no legs, no strike and no option kind (`crypto_option_spread.pyx`). Legs come
  from `public/get_combos` or `public/get_combo_details` as `{instrument_name, amount}` with the
  sign carrying direction - verified live, a `BTC-CCOND-...` condor resolves to
  `[+1 77000-C, -1 78000-C, -1 80500-C, +1 81500-C]`. The `develop`-branch adapter also attaches
  `deribit_combo_id`, `deribit_combo_state` and `deribit_combo_legs` to the instrument's untyped
  `info` map; check the keys exist at the pinned version before depending on them.
- **Combo-level greeks exist and are not trustworthy raw.** A live `public/ticker` on
  `BTC-RRITM-11SEP26-75000_84000` returned `delta 1.77439`, `gamma -2e-05`, `vega -7.49861`,
  `theta 29.52107`, `rho 20.78882`, `mark_price 0.0059` and **`mark_iv -1.75`**. A negative
  implied volatility is proof that not every combo-level derived field is meaningful. Sum the
  legs' own greeks weighted by signed leg amount times combo size, and calibrate any combo-level
  number against a hand-computed leg sum before trusting it.
- **A combo is a fully lifecycled instrument.** Live metadata carries `expiration_timestamp`,
  `settlement_period` ("day"/"week"), `settlement_currency`, `contract_size` and `instrument_id`;
  it reaches state `delivered` and is archived under `expired=true`. What is genuinely absent is
  any settlement, delivery, exercise or expiry **process** for a combo anywhere in the spec (the
  `settlement_type` taxonomy covers futures, perpetuals and options only), and a combo ticker
  carries no `settlement_price` while its leg does. **Do not use this as an argument that the
  account holds the legs rather than the combo** - it does not support that conclusion, and a
  previous version of these docs leaned on it. The evidence that does support it is accounting and
  lifecycle: `open_interest` removed from the combo ticker as an announced breaking change and
  absent live while the leg shows 96.4, exchange-side deactivation of combo books, zero commission
  on the combo, and Deribit's `include_combos` wording locating the position at the leg. That puts
  it at **92%**, with a real residual **8%**: no normative sentence in the API reference answers
  it, and the positions-only `kind_without_spot` filter enum still lists both combo kinds.

## 4. Units, and the mistake to avoid

Deribit options are quoted in coin, settle in coin, and are struck against a USD index. The
easiest way to produce a beautiful backtest of a losing strategy is to mix the two silently.

- Settlement currency is explicit at every boundary; never inferred.
- Any conversion between coin and USD names the price it converted at and the timestamp of that
  price.
- Contract multiplier, tick size, and minimum trade amount come from the instrument, never from a
  constant in core code (`docs/venues.md`).

## 5. Stress defaults

The cost stress in the evaluation protocol runs at:

| Knob | Stressed value |
| --- | --- |
| Fees | 2x |
| Slippage | 2x |
| Fill price | One tick worse |
| Displayed size | Halved |

A candidate whose edge does not survive all four simultaneously had an edge in the cost model,
not in the market.
