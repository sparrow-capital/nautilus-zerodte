# Risk and guardrails

Loss limiting is a feature with acceptance criteria, not a hope. Read this before touching
`configs/risk/`, the greek gate, position sizing, or anything that limits loss.

---

## 1. Required guardrails (T12)

Every row needs a test that **trips** it. A limit with no test does not exist.

| Guardrail | Enforced where | The test must show | Trip test |
| --- | --- | --- | --- |
| Per-trade maximum loss | Strategy FSM exit, gate sizing | A losing path exits at the cap | NOT IMPLEMENTED |
| Daily loss limit, then flat and halt | Gate only - nothing sets the flag | Trading stops for the session on breach | NOT IMPLEMENTED |
| Consecutive-loss circuit breaker | NOT IMPLEMENTED | Breaker trips and requires manual reset | NOT IMPLEMENTED |
| Net greek caps (delta, gamma, vega) | Greek gate | An intent that would breach is rejected | `tests/unit/test_gates.py::test_check_risk_policy_wrapper` |
| Concentration cap per strike and per expiry | Declared in `models/risk.py`, unenforced | Over-cap intent rejected | NOT IMPLEMENTED |
| Margin utilisation ceiling | NOT IMPLEMENTED | Halt above threshold before liquidation risk | NOT IMPLEMENTED |
| Data staleness halt | Gate context | Stale snapshot rejects rather than trades | `tests/unit/test_gates.py::test_evaluate_operational_stale_quote` |
| Reconciliation mismatch halt | NOT IMPLEMENTED | Mismatch halts and journals; never auto-corrects | NOT IMPLEMENTED |
| Max orders and notional per minute | NOT IMPLEMENTED | Rate breach rejects and journals | NOT IMPLEMENTED |
| Operator kill switch | NOT IMPLEMENTED - see `docs/killswitch_plan.md` | No test can trip it, because there is nothing to trip | NOT IMPLEMENTED |

**Two of ten.** That is the real state, and it is now machine-checked:
`tests/unit/test_guardrail_registry.py` parses this table and fails if a row names a trip test
that does not exist, so a row cannot quietly claim coverage it does not have. The only way to
move a row off NOT IMPLEMENTED is to name a test that is really there.

**"Daily loss limit" deserves its own note**, because it looks implemented and is not.
`evaluate_operational` does reject when `context.daily_loss_breached` is true, and
`test_evaluate_operational_daily_loss` proves that. But `daily_loss_breached` is only ever
declared (`gates/context.py:27`, default `False`) and read (`gates/evaluator.py:78`) - **nothing
in `src/` ever sets it**, and `max_daily_loss` is read by nothing at all. A gate with no trigger
is not a limit. That is exactly the shape of failure this table exists to stop hiding.

**What does not exist, stated plainly.** There is no file trigger, no signal trigger and no CLI
trigger for an operator flatten. `nautilus-zerodte flatten` appends a `FLATTEN_REQUEST` line to the
journal, prints, and exits 0; nothing in `src/` reads that event. NautilusTrader does claim SIGTERM,
SIGINT and SIGABRT on the live loop and routes them to `TradingNode.stop()`, but
`StrategyConfig.manage_stop` is left at its default of `False`, so a stop flattens nothing. The
only flatten that is wired at all is time-triggered (`SessionActor` blackout), and it is itself
broken: `strategies/base.py` calls `self.cancel_all_orders()` with no argument while NautilusTrader
declares `cancel_all_orders(self, InstrumentId instrument_id, ...)` with no default
(`trading/strategy.pxd:162`), which is a hard `TypeError` on the pinned 1.229.0. It has never been
reached because it needs a strategy actually in a position, and no test puts one there.

**And the intended fix would not have worked either.** The plan was to route the flatten through
NautilusTrader's `Strategy.market_exit()`. On the Deribit combo this strategy actually trades
(`strategies/reference.py:150-167` opens the vertical as ONE combo instrument), `market_exit`
closes **nothing**. NT 1.229.0 creates no `Position` object for a spread fill -
`CryptoOptionSpread` carries `InstrumentClass.OPTION_SPREAD`, `Instrument.is_spread()` is true,
and the ExecutionEngine skips the position lifecycle (`execution/engine.pyx:1653`; the upstream
docs say "Positions are not created for spread instruments",
`docs/concepts/positions.md:445`). `market_exit` builds its instrument set from
`cache.positions_open()` plus open and in-flight orders (`trading/strategy.pyx:1780-1794`), so a
filled combo contributes nothing to it. The result would have been a flatten that reports
completion with the position still on - the same class of defect as the false row above, one
layer down. NT expects the adapter to synthesise per-leg fills (Interactive Brokers does:
`_generate_leg_fill`, `-LEG-` client-order-id convention); the Deribit adapter has zero
occurrences of combo, leg or spread in its execution path, and upstream issue #4329 acknowledges
the gap. The redesign is H3 in `docs/killswitch_plan.md` and decisions D11 to D13. **It is also
not implemented.**

Three further gaps on the same path, all unfixed as of 2026-09-06 and all recorded as tasks in
H3.4 of `docs/killswitch_plan.md`:

- **The cancel step does not reach combo orders.** `private/cancel_all_by_instrument` defaults
  `include_combos=false`, and the adapter never sets it, so a resting combo order survives a
  leg-level cancel and can re-open exposure.
- **Per-leg fills are dropped when the leg instruments are not loaded.** The adapter discards a
  user trade whose `instrument_name` is not in its instrument cache, with only a warning. Loading
  the combos without their legs means those fills vanish entirely - no position, no
  reconciliation, no flatten.
- **Raw combo greeks are not safe as risk inputs.** A live `public/ticker` on
  `BTC-RRITM-11SEP26-75000_84000` returned `mark_iv -1.75` - a negative implied volatility -
  alongside `delta 1.77439`, `vega -7.49861` and `theta 29.52107`. Sign convention, scaling and
  per-unit basis for combo-level greeks are undocumented. Greeks for a combo must be summed from
  the legs' own tickers weighted by signed leg amount, and no raw combo greek may feed a limit
  until it has been calibrated against a hand-computed leg sum.

**Whether the venue holds a combo as two leg positions is 92%, not settled.** The accounting and
lifecycle evidence for two leg positions is strong (`open_interest` removed from the combo ticker
as an announced breaking change and absent live while the leg shows 96.4; combo books deactivated
by the exchange under error 13035 into a state accepting no orders; zero maker and taker
commission on the combo while its legs are fee-bearing; Deribit's own `include_combos` wording
locating the position at the leg). The residual 8% is that **no normative sentence in Deribit's
API reference answers it either way**, and the positions-only `kind_without_spot` filter enum
still lists both combo kinds. It does not change the design above, which holds under both
answers - see H3.0.

"Within one bar", the old wording, was also unachievable as written: there are no bars anywhere in
this system - both fixture catalogs carry quote ticks and greeks only - so any real bound is a
timeout, not a bar.

**Rows above marked "Risk actor" are also unbuilt.** No risk actor exists in `src/`. The daily loss
limit, the consecutive-loss breaker, the margin ceiling and the reconciliation halt are all
specifications, not controls. This table describes the intended guardrail set; git and the tests are
the record of what is enforced today.

**Guardrails fail closed and never auto-reset.** Resuming after a breaker is a human action, by a
different process than the one that tripped it. A breaker that clears itself is a delay, not a
control.

## 2. The shock grid

`configs/risk/default.yaml` currently carries `spot_shock: 0.01` and `vol_shock: 0.10`.

**A one percent spot shock is not a shock for BTC, it is a Tuesday.** Daily realised volatility is
several times that, and hourly moves of five to fifteen percent have happened repeatedly. A 0DTE
short-gamma book is fine until the jump, so a shock grid calibrated to a calm month measures
nothing.

Three requirements:

1. **Calibrate to trailing realised**, at plus and minus one, two, and three sigma of the recent
   distribution.
2. **Plus a fixed catastrophic scenario** that does not depend on recent calm. If the shock grid
   shrinks when the market is quiet, it disappears exactly when it is most needed.
3. **Make it two-dimensional and do not assume a sign.** The equity reflex "spot down, vol up" is
   unreliable in crypto: BTC skew flips to calls-bid in bull phases, and a one-dimensional vol
   shock will systematically misprice the corner you actually blow up in. Shock spot and vol
   jointly across a grid, and report the worst cell, not the diagonal.

Report the worst cell of the grid, its loss, and whether it is survivable given account equity.
That last number is the one that decides whether the strategy can be traded at all.

## 3. Margin and liquidation

Currently absent, and it is a gap that can end the account while the strategy is right.

Deribit uses portfolio margin, and on coin-settled products **your collateral is the coin whose
price moves with your position**. A short-vol book can be directionally correct and still be
liquidated, because a spot move simultaneously increases the requirement and decreases the value
of what is posted against it.

- Simulate maintenance margin against the venue's actual formula, not a proxy.
- Guardrail on **margin utilisation** with a halt threshold well below the liquidation point.
  Utilisation is measured under the shock grid, not only at spot.
- Model the collateral revaluation explicitly. Margin in coin terms against a USD requirement is
  a second-order exposure and it is signed against a short book.
- Liquidation is modelled as a worst-case fill, not a mid-price unwind.
- **Portfolio margin can wedge a sequential unwind, and that is a risk limit, not an execution
  detail.** Closing one leg of a hedged pair raises the initial margin requirement on what
  remains, and Deribit's position-management guidance says the second reduce-only order can then
  be rejected with "Not Enough Funds". A partial unwind that cannot complete is a **stuck** naked
  short, not a briefly exposed one. Two consequences: the flatten closes the combo atomically
  where it can and legs out short-leg-first where it cannot (D11, D12), and the margin
  utilisation ceiling must leave enough headroom that a half-finished unwind still fits. The
  rejection is documented for hedged pairs generally and has **not** been observed on a combo
  specifically - it is the load-bearing claim behind D11 and the first thing the testnet probe
  should try to falsify.

## 4. Sizing

- Size from the **stressed** loss, not the expected loss. The expected case does not breach
  limits; that is what makes it the expected case.
- Kelly and its variants assume you know the distribution. You do not, and the tails here are fat
  and estimated from short history. If a fractional-Kelly rule is used, state the fraction and the
  reason, and cap it independently.
- Sizing that depends on a parameter fitted in the same sweep that chose the strategy inherits
  that sweep's overfitting. Fit sizing on the stress results, not the in-sample returns.

## 5. Reporting risk

Every report leads with risk, before return, in this order:

1. Maximum drawdown, and time to recovery
2. CVaR at 95 and 99
3. Worst single trade, worst day
4. Loss distribution, with the shape called out (skew and kurtosis)
5. Worst cell of the shock grid, and whether it is survivable
6. Margin utilisation, peak and under shock

Return comes after all of that, because that is the order in which they kill you.
