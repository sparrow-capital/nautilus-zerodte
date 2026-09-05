# PnL attribution (P&L explain)

Specification for decomposing realised PnL, and the tests that gate adoption. Supersedes
`docs/implementation/learning-attribution.md`, which describes what the code does today and is
known incomplete.

Read this before touching `learning/`, changing PnL decomposition, or deciding whether a
profitable run is adoptable.

---

## 1. Why this exists

Standard practice on a derivatives desk is a daily P&L explain: decompose realised PnL into terms
you understand, and escalate on the part you do not. The purpose is not accounting tidiness. It is
that **unexplained PnL is usually a modelling error that happens to be pointing your way**, and it
stops pointing your way at the least convenient moment.

For 0DTE specifically the stakes are higher, because gamma and theta are both large and both
change fast, so a decomposition that is merely approximate can be wrong by more than the edge.

---

## 2. The terms

Realised PnL over a holding period is decomposed as a **path sum**, not a two-endpoint expansion.
For each snapshot interval `i` from entry to exit, with greeks sampled at the start of the
interval:

| Term | Formula (per interval, summed over the path) | Notes |
| --- | --- | --- |
| **delta** | `delta_i * dS_i` | **Currently missing entirely.** With `hedge_delta_band: 0.30` the book deliberately carries residual delta between hedges, so this term is frequently the largest one. |
| **gamma** | `0.5 * gamma_i * dS_i^2` | Must be path-summed. A single gamma sampled at fill is meaningless for 0DTE, where gamma changes by orders of magnitude within the holding period. |
| **theta** | `theta_i * dt_i` | Time decay over the interval, not `hold_hours / 24` applied once. |
| **vega** | `vega_i * dIV_i` | Per interval, using the leg's own IV, not a book-level average. |
| **vanna** | `vanna_i * dS_i * dIV_i` | Cross term. Cheap to add and material when spot and vol move together, which in crypto they often do. |
| **volga** | `0.5 * volga_i * dIV_i^2` | Second order in vol. Matters on IV spikes. |
| **charm** | `charm_i * dS_i * dt_i` | Delta decay. Matters precisely because time to expiry is measured in hours. |
| **inverse-contract cross term** | see section 3 | Deribit options are coin-settled and coin-quoted while the underlying is USD-denominated. |
| **funding** | `funding_rate * perp_notional * dt_i` | The perpetual hedge leg pays or receives funding. A real, signed, persistent term. Currently absent. |
| **commission** | `OrderFilled.commission` | Backtest via the NT fee model, live from the venue. |
| **slippage** | `(fill_px - mid_at_submit) * signed_qty` | Kept separate from spread cost in the pre-trade edge. |

**Residual** is what is left:

```
residual = realized_pnl - sum(all terms above)
```

## 3. The inverse-contract term

Deribit options on BTC are quoted and settled in BTC while the risk is measured in USD. A PnL of
`P` BTC is worth `P * S` USD, so a move in `S` revalues the PnL itself:

```
usd_pnl = btc_pnl * S
d(usd_pnl) = S * d(btc_pnl) + btc_pnl * dS
```

The second term is **extra delta that does not appear in the option's own delta**. It is a
quanto-like effect and it is signed with the position, so it does not average out.

`costs/deribit.py` already shows awareness of the unit problem
(`theoretical_value_btc = spread_intrinsic_usd / underlying`) but the attribution does not carry
it through. Any decomposition that omits this term will show a systematic signed residual on
trending days, which is exactly the case the residual test is designed to catch.

## 4. The two tests that gate adoption

### 4.1 Signed residual test (T11)

Across trades in the run, test whether the mean residual differs significantly from zero.

- **Mean significantly non-zero: blocks adoption.** A signed residual is a modelling error with a
  direction. You are being paid by something you do not understand, which means you cannot size
  it, cannot stress it, and cannot tell when it stops.
- **Large but zero-mean: does not block.** This is discretisation and truncation noise from finite
  snapshot intervals and a truncated expansion. Widen the tolerance, note it, adopt.

**The distinction is the point.** A single "residual must be under X percent" threshold conflates
two cases with opposite implications, and in practice rejects good work while waving through the
dangerous kind.

Use the effective sample size from `docs/quant/evaluation.md` in the test, not the raw trade
count, or the test will be far too easy to pass.

### 4.2 Cost reconciliation regression (T7)

```
edge_realized_bps = a + b * edge_predicted_bps + e
```

Require intercept `a` near zero **and** slope `b` near one; report R-squared.

A slope well below one means the cost model has a **scale** error. It can cancel on average while
failing systematically on the subset the strategy actually selects for, so checking only the mean
error misses it. Report the regression, not a single number.

## 5. Known defects in the current implementation

From `learning/module.py:_decompose_greek_pnl` and
`docs/implementation/learning-attribution.md`. These are why the decomposition cannot currently
close, and why the tenet would otherwise be a rule nobody can satisfy.

| ID | Defect | Impact |
| --- | --- | --- |
| **A1** | No delta term at all. The decomposition is theta plus gamma plus vega only. | With a 0.30 delta band, residual delta PnL is frequently the dominant term. Guarantees a large signed residual. |
| **A2** | Greeks frozen at fill; `gamma * dS^2` computed once over the whole hold. | Severe truncation error for 0DTE, where gamma changes by orders of magnitude over hours. |
| **A3** | `theta * hold_hours / 24` applied once rather than integrated. | Same class of error as A2, smaller magnitude. |
| **A4** | No vanna, volga, or charm. | Cross terms are material when spot and vol move together, and charm matters at hours to expiry. |
| **A5** | No inverse-contract cross term. | Systematic signed residual on trending days. See section 3. |
| **A6** | No perpetual funding term. | Persistent signed drift in the residual proportional to hedge size and holding time. |

Fixing A1, A2, and A5 is the minimum for the residual test to be meaningful. Until then,
attribution output is diagnostic only and must not be cited as an adoption gate.

## 6. Non-goals

- **No ML calibration.** `LearningModule.calibrate()` stays a stub until the rule-based
  decomposition closes. A model fitted on a broken cost model learns the cost model.
- **No implied-vol surface fitting** for attribution purposes. Use the venue's per-leg IV and its
  timestamp; if it is stale, that is a staleness rejection (T5), not a reason to build a surface.
