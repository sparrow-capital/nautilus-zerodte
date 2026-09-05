# Decision log

One entry per decision that a future session must not silently undo. Each carries the decision,
why, and the **reversal condition** - what would have to be observed for us to change our mind.
Newest at the bottom.

Format: **D<n> - title / Date / Decision / Why / Reversal condition.**

---

## D1 - Extend NautilusTrader, do not vendor or rewrite
**2026-09-05**

**Decision.** Stay a thin extension of NautilusTrader. Keep the extension thin: gates, strategy
FSM, cost models, journal, evaluation harness. Nothing else.

**Why.** The existing skeleton is sound and already carries gates, FSM, journal, adapters, and a
test suite. Reimplementing engine concerns is unbounded work in a domain where wrong means money.

**Reversal condition.** NautilusTrader's release cadence or API stability makes tracking upstream
more expensive than owning the equivalent code, or a needed capability is repeatedly rejected
upstream.

---

## D2 - Replace "open the holdout once" with a registered trial budget
**2026-09-05**

**Decision.** Drop the one-shot out-of-sample rule. Instead: register every trial program-wide,
deflate reported statistics by the trial count (DSR, PBO), prefer CPCV to a single holdout, and
budget holdout openings (default 10) after which the holdout retires and a new one accrues from
newly arrived data. Forward paper trading is treated as the real holdout.

**Why.** What corrupts inference is not looking at held-out data, it is failing to account for how
many times you looked. Deribit 0DTE history is finite and unrepeatable, so a one-shot rule
guarantees the program runs out of clean data, at which point people cheat quietly - which is
strictly worse than an honest accounting. A single holdout run is also one draw with no error bar;
CPCV gives a distribution and a PBO estimate.

**Reversal condition.** The trial registry proves unenforceable in practice (trials happening
outside it), in which case a cruder taboo may beat unreliable bookkeeping.

**Supersedes.** The original draft tenet in the first version of `CLAUDE.md`.

---

## D3 - Attribution gates on the sign of the residual, not its size
**2026-09-05**

**Decision.** A profitable run is blocked from adoption when the per-trade residual has a mean
significantly different from zero. A large but zero-mean residual does not block.

**Why.** The two cases have opposite implications. A signed residual is a modelling error with a
direction: you are being paid by something you do not understand, cannot size, and cannot tell
when it stops. An unsigned residual is discretisation and truncation noise from finite snapshot
intervals - a precision problem, not a correctness one. A single magnitude threshold conflates
them, rejecting good work while waving through the dangerous kind.

**Reversal condition.** The residual turns out to be dominated by a term that is signed for a
benign and fully understood reason, making the test reject correct work repeatedly.

---

## D4 - Attribution must be a path sum and must include delta, funding, and the inverse term
**2026-09-05**

**Decision.** The PnL decomposition is computed per snapshot interval and summed, and includes
delta, gamma, theta, vega, vanna, volga, charm, the Deribit inverse-contract cross term, perp
funding, commission, and slippage. Defects A1-A6 in `docs/quant/attribution.md` are the gap
between this and the current code.

**Why.** The inherited decomposition is theta plus gamma plus vega only, with greeks frozen at
fill. It has no delta term at all while the strategy deliberately carries up to 0.30 residual
delta between hedges, so the largest term is missing. For 0DTE, a two-endpoint expansion with a
frozen gamma is not an approximation, it is a different quantity. Until this is fixed the residual
test cannot be satisfied by anyone, which would make D3 a dead letter.

**Reversal condition.** Measurement shows a term is consistently negligible relative to the
residual tolerance, in which case drop that term specifically and record it here.

---

## D5 - No maker fills in backtest without a queue-position model
**2026-09-05**

**Decision.** Backtest fills cross the spread, cap at displayed size, and apply a participation
limit. Passive fills are not modelled unless a queue-position and adverse-selection model exists.

**Why.** In 0DTE options this is the largest known manufacturer of fake edge. Assuming passive
fills assumes front-of-queue and that nothing informed traded through you; both are wrong in the
flattering direction, and the resulting backtest looks excellent and loses money.

**Reversal condition.** A queue model exists, is documented, and is validated against recorded
fills from live or paper trading.

---

## D6 - Two-dimensional shock grid with no assumed skew sign, plus a margin guardrail
**2026-09-05**

**Decision.** Replace the single `spot_shock` / `vol_shock` pair with a joint spot-vol grid
calibrated to trailing realised volatility, plus a fixed catastrophic scenario that does not shrink
in calm markets. Add a margin-utilisation guardrail measured under the grid.

**Why.** `spot_shock: 0.01` is not a shock for BTC. The equity reflex "spot down implies vol up"
is unreliable in crypto, where skew flips to calls-bid in bull phases, so a one-dimensional shock
misprices the corner you actually blow up in. Separately, Deribit portfolio margin on coin-settled
products means collateral revalues with the position: a short-vol book can be directionally right
and still be liquidated, and no guardrail currently covers that at all.

**Reversal condition.** Measured joint spot-vol behaviour turns out stable enough in sign that the
grid is redundant - which would be a genuinely surprising finding and should be recorded with its
evidence.

---

## D7 - Documentation is tiered, with CLAUDE.md kept minimal
**2026-09-05**

**Decision.** `CLAUDE.md` holds only what applies on every task: tenets as one-liners, hard rules,
routing, commands. `INDEX.md` routes to on-demand files. `INTENTS.md` holds why and what success
is. Detail lives in `docs/`, with the math-heavy files grouped under `docs/quant/`. Rules never go
in `docs/implementation/`, which describes as-built mechanics and rots with the code.

**Why.** The always-loaded file is a tax on every turn, including turns that have nothing to do
with its contents. Progressive disclosure keeps the tax small while keeping the detail one hop
away. Separating rules from as-built descriptions stops rules from decaying silently when code
changes.

**Reversal condition.** The routing proves lossy in practice - sessions repeatedly miss a rule
because it was one hop away - in which case promote the specific missed rules into `CLAUDE.md`
rather than abandoning the tiering.

---

## D9 - Run artifacts resolve under ZERODTE_RUNS_DIR, with an autouse tripwire in tests
**2026-09-05**

**Decision.** `AppConfig.resolved_journal_path` resolves relative paths against
`ZERODTE_RUNS_DIR` when that variable is set, falling back to `runs/`. Precedence is explicit
argument, then the variable, then `runs/`. The read happens in the resolver in
`config/strategy.py`, not in `config/loader.py:_apply_env_overrides`. `tests/conftest.py` sets
the variable per test and adds a second autouse fixture that fails any test which writes into
the repo's own `runs/`.

**Why.** Running the suite from the repo root appended NODE_START, NODE_STOP and a WARN-level
FLATTEN_REQUEST to `runs/latest.jsonl` - the operator's real audit trail, same schema, no
provenance marker, because `JournalEntry` is frozen and carries no test flag. The env read has
to sit in the resolver because a directly constructed `AppConfig()` never passes through the
loader, and that is exactly what the tests do. The resolver is also the single chokepoint every
production caller already funnels through, so one guard there beats one per caller. The seam
alone is not enough: the strategy and actor configs default to the literal string
`runs/latest.jsonl` and never call the resolver, so the tripwire is what catches a regression
there. It is function-scoped so the failure names the offending test rather than the suite.

**Reversal condition.** `JournalEntry` grows a provenance field and every writer sets it, so a
test-written record is distinguishable from a real one - at which point the seam is still worth
keeping for tidiness but the tripwire could be relaxed to a warning.
