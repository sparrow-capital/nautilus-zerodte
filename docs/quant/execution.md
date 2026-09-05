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
- **Combo and multi-leg orders are charged per leg.** A spread costs two legs, not one.
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
