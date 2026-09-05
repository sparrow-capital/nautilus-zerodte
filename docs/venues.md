# Venues: containment, adding a coin, adding a venue

Deribit first, not Deribit only. Adding a coin must be a config change. Adding a venue must be an
adapter plus a cost model and nothing else.

Read this before adding a symbol or a venue, or when you find venue knowledge somewhere it does
not belong.

---

## 1. Containment (hard rule)

Venue-specific knowledge lives in exactly four places:

```
node/adapters/          connection, subscription, order translation
costs/                  fee schedules and edge math
strategies/selectors/   structure selection that depends on venue chain shape
configs/                every venue constant
```

Anywhere else it is a defect. Specifically, **no core code contains** a coin symbol, tick size,
contract multiplier, minimum trade amount, settlement currency, expiry hour, index name, or fee
rate. These come from the instrument object or from config.

Enforced by a grep check in CI over `src/` excluding those four directories.

## 2. The extensibility test

**The whole test suite runs green against ETH using only a different profile YAML.** If that
requires a code change, the abstraction is wrong and the fix is in core, not in the new profile.

Run it as part of any change that touches instrument handling.

## 3. Adding a coin

Config only:

1. New profile in `configs/profiles/`, pointing at the coin's series and perpetual hedge
   instrument.
2. Fee overlay in `configs/fees/` if the schedule differs.
3. Session overlay in `configs/session/` if the expiry hour differs.
4. Risk profile in `configs/risk/` - **shock magnitudes are per-coin.** ETH is not BTC and reusing
   BTC's grid understates or overstates depending on regime (`docs/quant/risk.md`).
5. Record a catalog for it. A profile with no data is not a supported coin.

If step 1 to 5 does not cover it, stop and fix the containment violation rather than special-casing
the coin.

## 4. Adding a venue

1. Adapter in `node/adapters/`, registered in `registry.py`.
2. Cost model in `costs/`, with the venue's actual fee basis - see the Deribit notes below for how
   wrong a naive premium-based model can be.
3. Structure selector in `strategies/selectors/` if the chain shape differs.
4. Session and fee overlays in `configs/`.
5. Contract tests replayed from **recorded frames** of that venue, committed as fixtures. No
   network in tests.

The strategy, gates, actors, journal, and evaluation harness must not change. If they do, the
venue abstraction has leaked.

## 5. Deribit specifics that keep biting

Collected because each one has a cost attached.

- **Coin-settled and coin-quoted, USD-struck.** Options are quoted and settle in the coin while
  the strike is against a USD index. This creates a cross term in PnL that is extra delta.
  See `docs/quant/attribution.md` section 3 and `docs/quant/execution.md` section 4.
- **Fees are charged on the underlying notional, not the premium**, and are capped as a fraction
  of the option price. A premium-based fee model understates cost on cheap OTM options by a large
  factor - which is where a 0DTE strategy spends most of its time.
- **Per-leg fees.** A spread is charged as two legs. Combos do not get a discount for being one
  order.
- **Delivery and settlement fees** apply to positions held to expiry. For 0DTE that is the normal
  path, not an edge case.
- **Expiry at 08:00 UTC**, settled against a time-averaged index print rather than the last quote.
  Confirm the current averaging window in the venue spec and encode it in config.
- **Portfolio margin with coin collateral.** Your margin is posted in the asset whose price moves
  with the position. See `docs/quant/risk.md` section 3.
- **Perpetual funding** on the hedge leg is a real signed PnL term in both the edge calculation
  and the attribution.
- **Testnet has different liquidity and sometimes different instrument sets.** It validates
  plumbing and authentication, never economics.

## 6. On the IB / SPY path

The upstream repo carries a secondary Interactive Brokers path for equity 0DTE
(`paper_spy.yaml`, `costs/ib.py`, `strategies/selectors/ib.py`). It doubles the adapter surface
and every containment rule above has to hold for it too.

Whether it stays is an open question in `INTENTS.md`. Until it is answered, it is maintained to
the same standard as Deribit - a half-maintained second venue is worse than none, because it makes
the abstraction look tested when it is not.
