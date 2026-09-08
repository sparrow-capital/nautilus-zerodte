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

## D8 - The operator kill switch is a latched trip file that flattens without stopping the node
**2026-09-08**

**Decision.** The operator emergency stop is a per-trader sentinel file at
`<runs>/halt/<trader_id>.trip`, written atomically (temp file in the same directory, then
`os.replace`) by `nautilus-zerodte halt`, and observed two ways: a `HaltActor` polling it on an
engine-clock timer, and a one-shot `Path.exists()` in every strategy's `on_start`. Observation
latches `self._halted` on each strategy - assigned `True` in exactly one place and `False` in
exactly one place, `__init__`, forever. The latch closes intake at the OPERATIONAL gate and at
both submit funnels, drops any intent sitting with the selector, and then flattens.

The flatten is NautilusTrader's `Strategy.market_exit()` for the non-spread instruments PLUS our
own combo-first close sequence over an `OrderFilled`-sourced exposure record, with short-leg-first
leg-by-leg as the bounded fallback (D11, D12, D13). Flatness is verified against BOTH
`Cache.orders_open/orders_inflight/positions_open(strategy_id=...)` AND
`Portfolio.is_completely_flat()`, and journalled as `FLATTEN_COMPLETE {flat: true}` or, on any
residual or disagreement between the two sources, `{flat: false}` at ERROR. The CLI blocks on the
resulting `HALT_ACK` and exits 0 only on a confirmed-flat acknowledgement, 3 on
acknowledged-but-not-flat, 4 on silence.

The trip does NOT stop the node, does NOT set `TradingState`, and does NOT retry beyond NT's own
bounded `market_exit_max_attempts` loop. Resuming requires `halt-clear` from a separate process
AND a node restart: clearing the file cannot un-halt a running node, because the in-process latch
has no setter.

**Why.** Three transports cross the CLI/node process boundary: a file, an OS signal, or NT's
Redis-backed external message bus. NT already claims SIGTERM/SIGINT/SIGABRT on the live loop
(system/kernel.py:566-572) and a signal carries no payload; Redis is a new hard dependency (hard
rule 10) whose availability correlates with the incident it exists to end. A local file plus a
bounded `stat` is the smallest thing that works.

The property that decides it is durability rather than simplicity. A signal is an event: if
nobody was listening at that instant it never happened. A trip file is state, so a node that is
down when the operator trips it halts the moment it starts, before it can touch the market.

Node shutdown is excluded from the trip because `_on_shutdown_system` sets backtest FORCE_STOP
synchronously (system/kernel.py:632-634) and FORCE_STOP breaks the run loop
(backtest/engine.pyx:1668) before `_process_and_settle_venues` and `_flush_accumulator_events`
(engine.pyx:1750-1763): a trip that shuts down cannot settle its own closing orders in backtest,
and in live it kills the supervisor while residuals may remain. `TradingState` is excluded because
HALTED denies every `SubmitOrder` including the flatten's own closes (risk/engine.pyx:1136-1148),
and REDUCING denies only BUY-when-net-long and SELL-when-net-short without ever reading
`reduce_only` (risk/engine.pyx:1149-1179), which blocks nothing on the fresh option legs a 0DTE
structure opens. The strategy-side `on_start` check exists because `Trader._start`
(trading/trader.py:254-264) starts every actor before any strategy, so an actor publish at its own
`on_start` reaches zero subscribers and the first poll republish arrives after the strategy has
already entered.

**AMENDED BEFORE COMMITTING.** The design as drafted on 2026-09-05 said the flatten was entirely
NT's. That was true of the draft and is not true of the design: `market_exit()` builds its
instrument set from `cache.positions_open()` plus open and in-flight orders
(trading/strategy.pyx:1780-1794), and NT creates no `Position` at all for a spread fill
(execution/engine.pyx:1653; `docs/concepts/positions.md:445` states it), so a filled Deribit combo
contributes nothing to that set. Shipping the draft would have produced a flatten that reports
completion with the position still on. The combo path is ours; everything else in the draft
stands.

**Reversal condition.** Any of three observations. (1) We take a msgbus-database dependency for
another reason, at which point the trip file is deleted and the CLI publishes on an external
stream - `ShutdownSystem` and `TradingStateChanged` are already on NT's externally-serializable
type list (serialization/base.pyx:235-275). (2) A load test shows the poll's `os.stat` in the p99
order-path latency tail, at which point the transport moves to SIGUSR1 registered with
`loop.add_signal_handler` plus a pidfile. (3) NautilusTrader ships a `SetTradingState` command
message and a HALTED variant that permits reduce-only orders, at which point the engine-level halt
replaces the strategy latch as the primary control and the latch becomes belt-and-braces.

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

---

## D10 - `dry_run` means "do not submit"; live submission is gated by three opt-ins
**2026-09-06**

**Decision.** Split the two meanings `dry_run` carried. `dry_run` now means only "strategies
journal the intent and do not submit an order"; `build_only` is the separate concern of
constructing the node and exiting. `paper` has three named modes - OBSERVE (default: the node
runs, gates evaluate, intents are journalled, nothing is submitted), BUILD ONLY (`--dry-run`),
and LIVE (`--live`). LIVE requires all three of `allow_live: true` in the profile, the `--live`
flag, and `ZERODTE_ALLOW_LIVE=1`; any missing opt-in **refuses the run with exit code 2 and names
what is missing**, and never silently downgrades to OBSERVE. Every run prints a banner naming its
mode, venue and testnet/mainnet before anything is constructed. Hard rule 5 in `CLAUDE.md` is
amended accordingly.

**Why.** Hard rule 5 previously said "`DRY_RUN` defaults to on". That was incoherent. `dry_run`
also drives `_handle_dry_run_intent` in `strategies/base.py`, so defaulting it on would make every
backtest journal `DRY_RUN_INTENT` and simulate no fills at all - producing runs with gates passing,
zero trades and no PnL, which read as "the strategy found no edge" rather than "execution was
switched off". A silently switched-off evaluation loop is worse than a loud failure.

The rule's intent was right and was attached to the wrong flag: the dangerous default is live
submission, not backtest execution. And the rule's other half was simply unimplemented - it
promised an explicit `--live` flag that did not exist, so `paper` connected and submitted whenever
`dry_run` was false and credentials happened to be present. That is one accidental condition, not
three deliberate ones. OBSERVE also fills a real gap: `paper` previously had no mode that ran the
node without submitting, which is what paper trading means.

**Reversal condition.** If OBSERVE proves unable to connect for market data without execution
credentials on some venue, it needs a per-venue answer rather than a fourth mode. If the
three-opt-in gate is routinely satisfied by an exported shell variable plus a habitual flag, the
env var has stopped being an independent signal and should be replaced by an interactive
confirmation of the traded notional.

---

## D11 - Combo-first atomic close, with short-leg-first leg-by-leg as the fallback (reverses "leg-by-leg unconditionally")
**2026-09-06**

**Decision.** The emergency flatten attempts an **atomic close on the combo instrument first** -
one aggressive reduce-only LIMIT order priced through the implied touch, with a bounded
reprice-and-retry loop - and only on exhaustion, rejection, or an unavailable combo book falls
back to closing the legs individually, **short leg first**. Never the reverse order of
preference, and the fallback is mandatory rather than optional. The design is written up as H3 in
`docs/killswitch_plan.md`; **none of it is implemented**, and `docs/quant/risk.md` still records
the operator kill switch as NOT IMPLEMENTED.

**This reverses a previous position and the reversal is the point.** Open question 2 in
`docs/killswitch_plan.md` was answered "leg-by-leg unconditionally, because a kill switch should
be dumb", and the H3 task was written that way. That is overturned.

**Why.** **Deribit portfolio margin can wedge a sequential unwind.** Closing one leg of a hedged
pair raises the initial margin requirement on what remains, and can reject the second reduce-only
order with "Not Enough Funds". That does not merely leave the account briefly exposed - it turns a
transient naked short call into a **stuck** naked short call, at 0DTE, with the operator already
pressing the emergency stop. Portfolio margin is exactly the regime this strategy trades in, and
`docs/quant/risk.md` section 3 already records that collateral revalues with the position on
coin-settled products. That failure mode is worse in kind, not merely in degree, than the risk
the old decision was protecting against.

The old argument was real and is not dismissed: an emergency-only fallback path is the
least-tested code in the system, it runs only when something has already gone wrong, and a
kill switch that is simple is a kill switch you can reason about at 3am. It is outweighed, and the
mitigation is written into H3: the fallback is exercised by a unit test that forces the combo
close to fail, on every run, rather than only by an integration test that takes the happy path.

Three secondary facts constrain the shape and are worth recording because they are easy to get
wrong. The atomic close cannot be a market order: `private/close_position` accepts only `type`
`limit|market`, NT's Deribit adapter implements **no `close_position` method at all** (the string
appears only in a rate-limit bucket), and Deribit's knowledge base says option combos support the
limit type only - a claim that is **second-hand** (support.deribit.com returns 403) and in tension
with the normative reference, which excludes only the trigger types
("stop_limit, stop_market, take_limit, take_market, and trailing_stop ... are not supported for
option and option_combo instruments") for combos. We design for limit-only because it is the
assumption that is safe if it is wrong. The retry loop is bounded because an unbounded reprice on
a 0DTE combo is a market order with no ceiling. And the combo close can vanish without warning:
Deribit deactivates low-volume combo books (**error 13035**) into FIX `SecurityStatus 3`,
"inactive (no new orders, edits, or cancellations)", which is why the fallback cannot be optional.

**Reversal condition.** Any of three observations. (1) The testnet probe in H3.5 shows Deribit
rejects `reduce_only` on an `option_combo` order, or that combo books for 0DTE strikes are
routinely too illiquid for an aggressive limit to fill inside the retry budget - at which point
the combo attempt becomes a wasted round trip during an emergency and leg-by-leg becomes the
primary path again, with the margin hazard handled by holding explicit margin headroom instead.
(2) The portfolio-margin wedge fails to reproduce on testnet when one leg of a filled combo is
closed - the "Not Enough Funds" rejection is documented for hedged pairs generally, is
second-hand, and has never been observed on a combo specifically, so it is the load-bearing claim
here and the one most worth falsifying. (3) NautilusTrader's Deribit adapter gains per-leg fill
synthesis and a working `close_position` (upstream issue #4329), at which point the whole
sequence collapses into NT's own `market_exit` and this entry is deleted rather than reversed.

---

## D12 - Short-leg-first is a hard ordering rule, and no unwind iterates a set
**2026-09-06**

**Decision.** Whenever any code path closes the legs of a structure individually, it closes the
**short leg first** - buy back the short call, then sell the long. The leg collection is an
**ordered** structure sorted short-risk-first from the signed leg amounts returned by
`public/get_combos`; a Python `set` is never iterated to decide unwind order. This applies to the
D11 fallback, to any future hedge unwind, and to anything else that legs out.

**Why.** The wrong order leaves the account **naked short a call** - unbounded loss, on a 0DTE
structure, during whatever event caused the flatten. NT's `market_exit` iterates
`for instrument_id in instruments:` over a `cdef set[InstrumentId]`
(`trading/strategy.pyx:1780-1794`), so the order is arbitrary and hash-dependent. If
reconciliation ever materialises the two Deribit leg positions - which it does if the per-leg user
trade does not inherit the parent combo order's `label`, a fact that is **NOT FOUND** in Deribit's
spec - then NT legs out in hash order and can produce that naked short by itself.

The reason this is a rule rather than an optimisation is that it is **cheap and unconditional**.
It is a sort, it costs nothing, and it makes the hazard impossible **regardless of how the venue
position question resolves** (92% two leg positions, with a real residual 8% - see H3.0 in
`docs/killswitch_plan.md`). A guarantee that does not depend on an unresolved fact is worth more
than one that does, so this lands whether or not the H3.5 probes are ever run.

**Reversal condition.** A structure appears whose short leg genuinely cannot be closed first -
for example one where the short is the illiquid leg and buying it back first reliably fails,
leaving the hedge intact but the order sitting. That is a real case for some structures and it
would need a per-structure ordering rule with its own test, not a return to arbitrary order.
Arbitrary order is never correct again.

---

## D13 - Spread exposure is tracked from OrderFilled, not read from the position cache
**2026-09-06**

**Decision.** For spread instruments, the strategy maintains its own signed per-instrument
exposure record, updated only in `on_order_filled` from the `OrderFilled` events NautilusTrader
does emit on the spread instrument. The flatten path, the flatness verification in
`post_market_exit`, and the EXITING -> FLAT transition all read that record **in addition to**
`Cache.orders_open`, `Cache.orders_inflight`, `Cache.positions_open` and
`Portfolio.is_completely_flat()`. `cache.positions_open()` is never the sole source of exposure.

**Why.** NautilusTrader 1.229.0 creates **no `Position` object at all** for a spread fill.
`CryptoOptionSpread` carries `InstrumentClass.OPTION_SPREAD`, so `Instrument.is_spread()` is true,
and the ExecutionEngine skips the position lifecycle (`execution/engine.pyx:1653`); the upstream
docs state it plainly - "Positions are not created for spread instruments"
(`docs/concepts/positions.md:445`). `market_exit()` builds its instrument set from
`cache.positions_open()` plus open and in-flight orders
(`trading/strategy.pyx:1780-1794`), so a filled combo whose orders have all completed contributes
nothing to it. `strategies/reference.py:150-167` trades the Deribit vertical as one combo
instrument, so today a filled combo plus `flatten_positions` would produce a journal that says
flat and an account that is not. NT expects the adapter to synthesise per-leg fills - Interactive
Brokers does (`_generate_leg_fill`, `-LEG-` client-order-id convention) - and the Deribit adapter
has zero occurrences of combo, leg or spread in its execution path. Upstream issue **#4329**
acknowledges the gap.

This is deliberately a small record - a dict of `InstrumentId` to signed `Decimal`, mutated in one
callback and read in three places. It is not a reimplementation of `Portfolio`, and it does not
touch the clock, a queue or a scheduler. It exists only because the engine declines to create the
object for this instrument class, which is precisely the T1 case: name the upstream capability
stood in for, and name what lets us delete the wrapper.

**Reversal condition.** The NautilusTrader Deribit adapter emits synthetic per-leg fills, or the
ExecutionEngine creates positions for spread instruments (upstream issue #4329 resolved). Either
one makes `cache.positions_open()` sufficient, at which point this record is **deleted**, not kept
as belt-and-braces - two sources of truth for exposure is its own defect. A partial reversal also
applies if the H3.5 testnet probe shows Deribit's per-leg user trades do NOT carry the parent
order's `label`: reconciliation then materialises real leg positions and the record becomes a
cross-check against them rather than the only view, which changes what `post_market_exit` should
do on a disagreement between the two.
