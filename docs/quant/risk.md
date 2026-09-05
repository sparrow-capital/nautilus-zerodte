# Risk and guardrails

Loss limiting is a feature with acceptance criteria, not a hope. Read this before touching
`configs/risk/`, the greek gate, position sizing, or anything that limits loss.

---

## 1. Required guardrails (T12)

Every row needs a test that **trips** it. A limit with no test does not exist.

| Guardrail | Enforced where | The test must show |
| --- | --- | --- |
| Per-trade maximum loss | Strategy FSM exit, gate sizing | A losing path exits at the cap |
| Daily loss limit, then flat and halt | Risk actor | Trading stops for the session on breach |
| Consecutive-loss circuit breaker | Risk actor | Breaker trips and requires manual reset |
| Net greek caps (delta, gamma, vega) | Greek gate | An intent that would breach is rejected |
| Concentration cap per strike and per expiry | Diversification | Over-cap intent rejected |
| **Margin utilisation ceiling** | Risk actor | Halt above threshold before liquidation risk |
| Data staleness halt | Gate context | Stale snapshot rejects rather than trades |
| Reconciliation mismatch halt | Node startup and reconnect | Mismatch halts and journals; never auto-corrects |
| Max orders and notional per minute | Adapter or risk actor | Rate breach rejects and journals |
| Kill switch (file, signal, or CLI) | Node | Flattens and stops within one bar |

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
