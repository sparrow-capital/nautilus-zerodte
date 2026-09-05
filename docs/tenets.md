# Tenets in full

The one-line versions are in `CLAUDE.md`. This file gives each tenet its reason, what it forbids,
and how it is enforced. A tenet without enforcement is a preference.

Format: **what it says / why / what it forbids / how it is enforced.**

---

## T1 Extend, do not fork the engine

NautilusTrader owns the event loop, message bus, clock, order and position state, matching,
greeks, catalog, and venue connectivity.

**Why.** Every capability we reimplement is one we have to keep correct forever, in a domain where
"correct" means money. NautilusTrader has more eyes on it than this project ever will.

**Forbids.** Writing a scheduler, queue, clock, matching engine, order book, greeks library, or
persistence format. Wrapping an upstream class without saying why.

**Enforced by.** Review. Every wrapper carries a comment naming the upstream capability it stands
in for and the condition under which it gets deleted.

---

## T2 Deterministic, and robust beyond determinism

Same inputs produce the same outputs, byte for byte, on every machine. **And** a conclusion that
does not survive bootstrap resampling is not a conclusion.

**Why.** Determinism makes a result reproducible. It does not make it true. Both halves are
needed: without the first you cannot debug, without the second you are reporting noise with high
precision.

**Forbids.** Wall-clock reads, unseeded randomness, dependence on set or dict iteration order,
float accumulation whose order varies with scheduling, parallel reductions without a fixed
combine order. Also forbids reporting a point estimate with no interval.

**Enforced by.** A CI job that runs the golden backtest twice and diffs the journal. Reported
metrics carry a bootstrap interval (`docs/quant/evaluation.md`).

---

## T3 One clock

Strategy, actor, and gate code reads time from the engine clock only.

**Why.** This is the single rule that makes backtest and live the same program. A stray
`datetime.now()` produces code that behaves differently in replay, and the difference shows up as
an unexplained parity failure weeks later.

**Forbids.** `datetime.now()`, `datetime.utcnow()`, `time.time()`, `time.monotonic()`,
`asyncio.get_event_loop().time()` anywhere outside `node/adapters/`.

**Enforced by.** A grep check in CI over `src/` excluding `node/adapters/`. Tests use the engine
test clock and never sleep on wall time.

---

## T4 One strategy object across backtest, paper, and live

**Why.** Two code paths means two behaviours, and the one you tested is not the one that trades.

**Forbids.** `if backtest:`, mode flags, environment sniffing, or venue detection inside
`strategies/`, `gates/`, or `actors/`. Adapters and config are the only components allowed to
know where they are running.

**Enforced by.** Grep check in CI for mode-ish identifiers in those three packages. A parity test
runs the same window through backtest and paper and compares per-intent
(`docs/testing.md`).

**Corollary.** If a behaviour passes in backtest and fails in paper, the bug is in the adapter or
the cost model. Do not patch it in strategy code.

---

## T5 Fail closed

Missing greeks, a stale quote, an unknown instrument, an unparseable message, or an exception
inside a gate: every one is a rejection.

**Why.** In a system that can lose money autonomously, the default answer to a question you
cannot answer is no.

**Forbids.** Bare `except: pass` on any path that can reach an order. Default values that stand
in for missing market data. A gate that returns "allow" on error.

**Enforced by.** Failure-injection tests (`docs/testing.md`) covering each fault class. Gate
evaluation wraps every gate and converts an exception into a journaled rejection.

---

## T6 Never block the order path

The hot path allocates little, never touches disk or network synchronously, never takes a
contended lock, and never runs research code.

**Why.** A blocked event loop is not slow, it is wrong: quotes queue, decisions go stale, and the
system trades on a picture of the market that no longer exists.

**Forbids.** Parquet reads, dataframes, process or thread pools, model fitting, plotting, and
synchronous HTTP anywhere reachable from a strategy or actor callback. Process pools belong in
`research/` (see the docstring in `research/offline.py`).

**Enforced by.** Load test with a latency budget per stage (`docs/engineering.md`). Review flags
any import of a heavy library inside `strategies/`, `gates/`, or `actors/`.

---

## T7 Costs are first-class, identical everywhere, and reconciled by regression

The fee schedule, spread cost, and slippage assumption used by the pre-trade edge gate are the
same numbers wired into the backtest fee model and reconciled against live fills.

**Why.** An optimiser fed by a wrong cost model optimises the cost model's error. In options,
where cost is a large fraction of gross edge, this is the most likely way to produce a beautiful
backtest of a losing strategy.

**The test is a regression, not a mean.** Regress realised edge on predicted edge across trades:

```
edge_realized_bps = a + b * edge_predicted_bps + e
```

Require intercept `a` near zero **and** slope `b` near one, and report R-squared. A mean error of
zero with `b = 0.3` means the model has a scale error that cancels on average and will not cancel
on the subset the strategy selects for. Checking only the mean misses this entirely.

**Forbids.** Separate fee constants for gate and backtest. Adopting a result from a run whose
reconciliation is out of tolerance.

**Enforced by.** The evaluation harness computes the regression on every run and marks the run
invalid outside tolerance. Thresholds in `docs/quant/execution.md`.

---

## T8 No look-ahead, and it must be structurally impossible

Every feature is computed from data whose `ts_event` is at or before the engine's current time,
**because the engine delivered it**, not because we remembered to filter.

**Why.** Convention-based no-look-ahead fails silently and produces the most convincing wrong
results in the business.

**Forbids.** Reading the catalog directly inside a strategy or gate. Using a venue-computed mark
IV without checking its own timestamp. Cross-validation without purging and an embargo around each
split boundary, since a trade spanning a boundary leaks. Building an instrument universe from
today's listings and applying it to the past.

**Enforced by.** Review rejects catalog access from `strategies/` and `gates/`. Splits are
constructed by the harness with purge and embargo, not by hand
(`docs/quant/evaluation.md`).

---

## T9 Pessimistic execution

Backtest fills cross the spread, pay configured slippage, are capped at displayed size and a
participation limit, and **there are no maker fills without a queue-position model**.

**Why.** In 0DTE options the quoted spread on OTM strikes is routinely a large fraction of
premium, displayed size is small, and a resting order fills precisely in the states where you
wish it had not. Assuming free passive fills is the largest known source of fake options edge.

**Forbids.** Mid-price fills. Unlimited fill size. Maker fills in backtest unless a queue model
exists and is documented. Choosing the more flattering of two defensible modelling choices.

**Enforced by.** The backtest fill model, plus a test asserting that a request larger than
displayed size is partially filled. Details in `docs/quant/execution.md`.

---

## T10 Every result is deflated by the number of trials it took to find

Trials are registered across the whole program, not per sweep.

**Why.** Search finds noise by default. What corrupts inference is not looking at held-out data,
it is failing to account for how many times you looked. A taboo on looking does not fix this and
cannot survive a market where history is finite; bookkeeping does.

**Forbids.** Reporting a raw Sharpe. Counting only the configurations in the final sweep.
Re-tuning on a holdout and re-running it. Treating the count as resettable between sessions.

**Enforced by.** A trial registry that the harness appends to on every evaluation, and reported
statistics that take the count as an input (Deflated Sharpe Ratio, PBO). Full protocol and the
holdout budget in `docs/quant/evaluation.md`.

**Note on what replaced the old rule.** An earlier draft said the out-of-sample window may be
opened exactly once. That was dropped: history is finite and unrepeatable, so a one-shot holdout
guarantees the program runs out of clean data and people start cheating quietly. Registered
looks plus deflated statistics achieve the same goal honestly. See decision D2 in
`docs/decisions.md`.

---

## T11 PnL must explain

Residual is realised PnL minus the sum of explained terms. A residual whose **mean** is
significantly different from zero blocks adoption. A large **zero-mean** residual does not.

**Why.** These two cases have opposite implications and the distinction is the whole point. A
signed residual is a modelling error with a direction, which means you are being paid by something
you do not understand and cannot size. An unsigned residual is discretisation and truncation
noise, which is a precision problem, not a correctness one.

**Forbids.** Adopting a profitable run whose decomposition does not close in the mean. Treating
"large residual" as automatically disqualifying. Reporting attribution without a residual line.

**Enforced by.** A t-test on the per-trade residual mean, plus the T7 regression. Term list,
formulas, and thresholds in `docs/quant/attribution.md`.

---

## T12 Guardrails are code, and every guardrail has a test that trips it

**Why.** Loss limits that exist as intentions do not exist. *A check that cannot fail is not a
check.*

**Forbids.** A limit with no test. A guardrail that auto-resets. A breaker that can be cleared by
the same process that tripped it.

**Enforced by.** The guardrail table in `docs/quant/risk.md`, where every row names the test that
must show it tripping. CI fails if a listed guardrail has no corresponding test.
