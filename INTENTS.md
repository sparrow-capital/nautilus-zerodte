# INTENTS

What the code cannot tell you: why this exists, what success is, and what would prove the thesis
wrong. Read this before proposing new work. Update it when the intent changes, not when the code
changes.

---

## The thesis

Deribit crypto 0DTE options are a young, retail-heavy, continuously-trading market with wide
spreads and a daily expiry cycle. The claim under test is that a **structured, gated, cost-aware
strategy can extract a repeatable edge there that survives realistic execution costs**, and that
the edge can be found and tuned by a disciplined search rather than by discretion.

The thesis is deliberately falsifiable. Most of the machinery in this repo exists to make it easy
to prove ourselves wrong cheaply, before capital is involved.

## What we are actually building

Not a strategy. A **machine for evaluating strategies**, whose output is a tuning decision with
evidence attached. The strategies are the input to that machine, not the point of it.

The loop, in one line: record real data, search a declared parameter space, deflate the result by
how hard we searched, explain the PnL, stress the costs, confirm forward on paper, then decide.

## Success criteria

A candidate is a success when all of these hold. Nothing partial counts.

1. Positive expectancy net of realistic costs, on data the search did not select for.
2. The result survives deflation by the trial count (`docs/quant/evaluation.md`).
3. PnL is explained: the residual has no significant signed component
   (`docs/quant/attribution.md`).
4. Cost prediction reconciles against realised fills: intercept near zero, slope near one.
5. Backtest and paper agree per-intent within tolerance over a live window.
6. Every guardrail has been tripped in a test, and the worst modelled case is survivable
   (`docs/quant/risk.md`).
7. Adding ETH is a config change, not a code change.

## The failure modes we most expect

Named so that a session can recognise one in progress:

- **Overfitting by accumulation.** No single sweep looks unreasonable; the program as a whole has
  tried four hundred configurations and picked the maximum. Countered by the trial registry.
- **Optimising the cost model's error.** The edge gate uses one set of assumptions and the fill
  model another; the "edge" is the gap between them. Countered by T7's regression check.
- **Unattributed PnL that happens to be positive.** A missing term in the decomposition points our
  way in-sample and the other way live. Countered by the signed-residual test.
- **Free maker fills.** Backtest assumes passive fills without queue position or adverse
  selection. This is the largest known manufacturer of fake options edge. Countered by T9.
- **A shock grid calibrated to a calm month.** 0DTE short gamma is fine until the jump.
  Countered by the fixed catastrophic scenario in the shock grid.
- **Coin-settled confusion.** PnL quoted in BTC, risk measured in USD, and the cross term dropped.
  Countered by making the inverse-contract term explicit in attribution and execution.

## Non-goals, so they stop coming up

- **No machine learning until rule-based attribution closes.** `LearningModule.calibrate()` stays
  a stub. A model fitted on a broken cost model learns the cost model.
- **No microsecond chase.** This is options structure trading, not latency arbitrage. Latency
  discipline exists because tail latency causes stale decisions and bad fills, not to win a race.
- **No live capital before the promotion checklist.** Costs reconciled over a full paper window,
  every guardrail tested and tripping, reconciliation clean across a restart, out-of-sample and
  paper parity both green. Then testnet. Then minimum size.
- **No indicator, feature, or knob without a hypothesis for why it should work.** Found by search
  alone makes it a candidate, not a feature.
- **No parallel abstraction over NautilusTrader.** If the wrapper grows its own concepts, we have
  forked the engine by accident.

## Current state (2026-09-05)

Built so far: gates, strategy FSM, journal, venue adapters, rule-based attribution,
config layering, 22 unit and 6 integration test files, CI running lint plus unit plus one backtest
smoke.

Not yet built, in rough order of what blocks what:

1. **No real recorded data.** The only catalogs are synthetic fixtures, and
   `backtest_btc.yaml` disables the edge gate to pass them. Nothing in the repo is currently
   evidence. `docs/implementation/live-catalog-capture.md` describes the intended path.
2. **No evaluation harness.** No sweep, no purged splits, no trial registry, no deflation, no
   report. This is the core deliverable and its spec is `docs/quant/evaluation.md`.
3. **Attribution is incomplete and cannot close.** Missing the delta term entirely, freezes greeks
   at fill, and omits funding and the inverse-contract cross term. Defects A1-A6 in
   `docs/quant/attribution.md`.
4. **Fill model is not pessimistic enough** for options. See `docs/quant/execution.md`.
5. **Risk shocks are calibrated for equities.** `spot_shock: 0.01` is not a shock for BTC. No
   margin or liquidation guardrail exists at all.

## Open questions

Questions a session should surface rather than silently answer:

- What is the realistic recordable history? Deribit 0DTE depth is short, which caps how much
  out-of-sample there can ever be and therefore how many trials the program can afford.
- Which structure is the first candidate: debit spreads (current reference strategy), short
  strangles, or calendar-adjacent? The risk profiles are not comparable and the guardrails differ.
- Is the perpetual hedge worth its funding cost at a 0.30 delta band, or is a wider band with no
  hedge cheaper?
- Does the IB / SPY path stay? It doubles the adapter surface. If equity 0DTE is not going to be
  traded, retiring it removes a lot of maintenance.
