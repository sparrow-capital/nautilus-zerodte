# Kill switch: design and plan (NOT IMPLEMENTED)

> **STATUS: this document is a PLAN for work that does not exist yet.** Nothing here
> describes a control the code currently has. The operator kill switch is NOT implemented.
> Do not cite this file as evidence that any guardrail exists - see `docs/quant/risk.md`
> for what is actually in place, and `docs/decisions.md` for decisions taken.

Produced 2026-09-05 by a design pass that read this repo and the NautilusTrader 1.229.0
source. Task status is tracked in the table below and in git history.

## Why this exists

`nautilus-zerodte flatten` does not flatten anything. It appends one `FLATTEN_REQUEST`
line to the journal, prints, and exits 0; nothing in `src/` reads that event. An operator
who runs it during a drawdown sees success and believes they are flat. Separately, the
only flatten that is wired at all is time-triggered (SessionActor blackout) and is itself
broken: `strategies/base.py` calls `self.cancel_all_orders()` with no argument, while
NautilusTrader declares `cancel_all_orders(self, InstrumentId instrument_id, ...)` with no
default (`trading/strategy.pxd:162`). That is a hard TypeError, reached only when a
strategy is actually in a position - which no test does.

## What NautilusTrader already provides (T1)

NautilusTrader 1.229.0 (pinned at pyproject.toml:8, read from the manylinux wheel) already ships the entire flatten and the entire node stop. It ships NO way for a second process to reach a running node, and no file watcher.

WHAT NT GIVES US - use verbatim, write none of it:
1. `Strategy.market_exit()` (trading/strategy.pyx:1750-1810). Collects every instrument this strategy has open orders, inflight orders or open positions for from the cache; per instrument calls `cancel_all_orders(instrument_id)` THEN `close_all_positions(instrument_id, tags=[MARKET_EXIT], time_in_force=..., reduce_only=...)`; arms a repeating engine-clock timer running `_check_market_exit` (strategy.pyx:1826-1861) which re-reads the cache each tick, waits while orders are open or inflight, re-sends closes when positions remain with no orders, and gives up after `market_exit_max_attempts` with a WARNING naming the three residual counts. This deletes every line of retry loop, instrument enumeration and closing-order construction we would otherwise write. Confirmed by reading the body.
2. The in-progress intake denial (strategy.pyx:861-863, mirrored for order lists at 953-957): `if self._is_exiting and not order.is_reduce_only and self._market_exit_tag not in (order.tags or []): self._deny_order(order, "MARKET_EXIT_IN_PROGRESS")`. Engine-owned, second line of defence behind our latch. We write no order-blocking code for the exit window.
3. `on_market_exit()` / `post_market_exit()` / `is_exiting()` (strategy.pyx:444-465, 1813). The override points where our journal records and flatness verification belong. `post_market_exit` is called from `_finalize_market_exit` inside a try/except, so a raise in our hook cannot break the exit.
4. `StrategyConfig.manage_stop` + `market_exit_interval_ms` + `market_exit_max_attempts` + `market_exit_time_in_force` + `market_exit_reduce_only` (trading/config.py:94-98). `BaseZeroDteStrategyConfig` already subclasses `StrategyConfig` (strategies/base.py:36), so these are accepted today with zero new schema. Verified `Strategy.stop()` (strategy.pyx:404-422): with `manage_stop=True` it sets `_pending_stop`, runs `market_exit()` only if not already exiting, and defers `Actor.stop` to `_finalize_market_exit`; with `manage_stop=False` it calls `_cancel_market_exit()` and ABORTS an exit already in flight.
5. `Clock.set_timer` / `set_time_alert` / `cancel_timer` / `timer_names` (common/component.pyx:419-562) on the engine clock - TestClock in backtest, LiveClock in live, no code difference. Repo precedent at actors/selector.py:81-89.
6. `Cache.orders_open / orders_inflight / positions_open(venue, instrument_id, strategy_id)` and `Portfolio.is_completely_flat()` - the authoritative "is anything still open" surface, and the same one `_check_market_exit` uses internally.
7. `MessageBus.publish` dispatching subscriber handlers synchronously and inline (common/component.pyx:2832-2834). This is what makes the ordering guarantee a total order rather than a hope.
8. `Component.shutdown_system(reason)` (common/component.pyx:2163) plus the kernel handler (system/kernel.py:613-641), and NT's SIGTERM/SIGINT/SIGABRT handlers (system/kernel.py:566-572). Phase 2 only, and only after flat is confirmed - see the exclusions.
9. `BacktestNode.build()` + `get_engine(run_config_id)` + `BacktestEngine.add_actor` - the seam the failure-injection test uses to inject a real trip file mid-run on the engine clock.

WHAT WE MUST WRITE, and why NT does not have it:
1. The trip-file transport (~60 lines in `models/halt.py`, no NT import). NT has no file watcher and no out-of-process control channel other than the optional Redis external message bus (live/node.py:338-378). A case-insensitive grep for kill_switch / killswitch / emergency / panic across every .py/.pyx/.pxd/.pyi in the wheel hits only Rust FFI doc comments about Rust panics.
2. `HaltActor` (~90 lines) - the poll, the once-only trip, the republish, the ack collection. NT gives the timer and the bus; nothing observes external state.
3. The LATCH (~10 lines in the strategy). NT's `_is_exiting` clears itself in `_cancel_market_exit` (strategy.pyx:1878), so it expires exactly when re-entry becomes possible again. Ours must outlive the exit and have no setter.
4. The flatness VERIFICATION and its journal records (~25 lines). `ExecutionEngine.check_residuals()` and `Cache.check_residuals()` (cache/cache.pyx:798-823) only log WARNINGs and return a bool. Nothing in NT turns "am I flat" into a durable, operator-readable fact.
5. The CLI acknowledgement loop and exit codes (~90 lines). Entirely outside the engine.

WHAT WE MUST NOT USE, with the verified reason:
- `RiskEngine.set_trading_state(TradingState.HALTED)` at trip time. HALTED denies every SubmitOrder (risk/engine.pyx:1136-1148) and `close_position` submits an ordinary SubmitOrder through the risk engine (strategy.pyx:1417). Halt-then-flatten denies the flatten's own closing orders: the operator gets a clean-looking halt and keeps the position, which is strictly worse than no kill switch.
- `TradingState.REDUCING` at any time. Verified at risk/engine.pyx:1149-1179: it denies BUY only when `is_net_long(instrument)` and SELL only when `is_net_short(instrument)`, and never reads `reduce_only`. On a fresh 0DTE leg both are False and the order passes. Describing it as "no new risk" would be a false control.
- `Component.shutdown_system` as part of the trip. `_on_shutdown_system` sets `set_backtest_force_stop(True)` synchronously (kernel.py:632-634); FORCE_STOP breaks the backtest run loop (engine.pyx:1668) and then returns BEFORE `_process_and_settle_venues` and `_flush_accumulator_events` (engine.pyx:1750-1763). The closing orders never settle. This single fact is why the flatten-and-stop design is rejected.
- `Actor.run_in_executor` / `queue_for_executor` to move the file stat off the callback. The kernel registers the ThreadPoolExecutor only outside BACKTEST and only when a loop was passed (system/kernel.py:275-280, 1254-1262); with no executor NT runs the function INLINE with no warning (common/actor.pyx:1064-1067). "Offload it" silently becomes "block the backtest loop", and the two environments diverge - a T4 smell hiding inside a T6 non-fix.
- `Actor.publish_signal` / `subscribe_signal` for the halt payload. Values are restricted to int/float/str (actor.pyx:2963), so a token plus reason plus source does not fit, and it is a data topic that the streaming capture would persist into the catalog.

## Ordering on trip

THE TRIP SEQUENCE. Every step from H1 to S6 executes inside ONE engine callback, with no awaits, because `MessageBus.publish` dispatches subscriber handlers synchronously and inline (common/component.pyx:2832-2834). That is what makes the ordering guarantee a total-order property rather than a hope.

HALT ACTOR - `_trip(source)`, reached identically from the `on_start` pre-check (source "startup"), the poll timer (source "file"), or a republish:

  H1. Read the trip file ONCE. If the read raises or the JSON will not parse, synthesise a TripRecord with reason "trip_file_unreadable" / "unparseable_trip_file" and PROCEED. A control file we cannot read is not a reason to keep trading (T5).
  H2. `self._halted = True` on the actor. Never assigned False anywhere in the module.
  H3. Journal `HALT_TRIP` at WARN: {token, reason, source, engine_ts_ns: self.clock.timestamp_ns()}. The engine timestamp is carried explicitly because `JournalEntry.ts` is `datetime.now` (models/journal.py:18) and is not an engine-time anchor.
  H4. `self.msgbus.publish(HALT_TOPIC, HaltSnapshot(token, reason, source))`. Every strategy's `_on_halt` runs to completion before this line returns.
  H5. Arm the ack-timeout `clock.set_time_alert` at `halt.ack_timeout_secs`.
  H6. On every subsequent poll tick while halted: republish the SAME snapshot, never a halted=False one, and perform NO file read. Steady-state disk cost after the trip is zero.
  H7. NOTHING ELSE. In particular, `shutdown_system` is NOT called here.

EACH STRATEGY - `_on_halt(msg)` -> `_latch_halt(reason, token, source)`, synchronous, called from H4:

  S0. `if self._halted: return`. Idempotent, so the H6 republish is a cheap no-op.
  S1. `self._halted = True; self._halt_token = ...; self._halt_reason = ...`. THE FIRST EXECUTABLE STATEMENT. It goes before the journal write because `Journal.record` does a synchronous open-append-close (journal/service.py:124-128) and can raise on a full disk or a permissions failure. A design that journals first has an unlatched strategy sitting behind a throwing call.
  S2. `self._pending_intent = None`. Drops an intent already queued with the selector.
  S3. Journal `HALT_LATCHED` at WARN: {token, reason, source, state_at_latch, had_pending_intent, active_intent_id}.
  S4. `if self.is_exiting(): journal HALT_EXIT_ALREADY_RUNNING; return`. NT warns and no-ops on a second `market_exit()` (strategy.pyx:1768-1770); calling it again would produce a log line we would mistake for progress.
  S5. `try: self.flatten_positions(reason=f"operator_halt:{reason}")`
      `except Exception as e: journal HALT_EXIT_FAILED at ERROR; publish HaltAck(flat=False); return`. Fail closed: still latched, still no intake, and the ack explicitly says NOT flat so the CLI exits 3.

INSIDE `flatten_positions` -> `market_exit()`, NT then, per instrument it holds orders or positions for: `cancel_all_orders(instrument_id)` THEN `close_all_positions(instrument_id, tags=[MARKET_EXIT], reduce_only=True)`. Cancel-before-close is NT's own loop ordering (strategy.pyx:1797-1799), not ours - we do not assert on it, because asserting on someone else's implementation tells us nothing about our code.

  S6. `on_market_exit()` override, called by NT at the start: journal `FLATTEN_START` with the instrument set and the three cache counts.
  S7. `post_market_exit()` override, called by NT on completion OR on max-attempts give-up:
        residual_open      = len(cache.orders_open(None, None, self.id))
        residual_inflight  = len(cache.orders_inflight(None, None, self.id))
        residual_positions = len(cache.positions_open(None, None, self.id))
        portfolio_flat     = self.portfolio.is_completely_flat()
      All three zero AND portfolio_flat -> journal `FLATTEN_COMPLETE {flat: true, counts}` at INFO, publish HaltAck(flat=True).
      Otherwise -> journal `FLATTEN_COMPLETE {flat: false, counts}` at ERROR, publish HaltAck(flat=False). NO re-arm: NT already retried `market_exit_max_attempts` times and gave up. Escalation is a human.
  S8. `on_order_filled`, first guard: if `self._halted`, journal `HALT_LATE_FILL` at WARN and do NOT transition out of the halted path. Separately (and independent of halt), the EXITING -> FLAT transition now requires the cache to report zero open positions and zero open/inflight orders for this strategy; a partial fill on a multi-leg exit journals `PARTIAL_EXIT_FILL` and stays EXITING.

HALT ACTOR - on all expected acks in, or on the H5 timeout:
  H8. Journal `HALT_ACK` at INFO if every ack has flat true, else at ERROR: {token, flat, timed_out, per_strategy: {id: {flat, counts}}}. This is the single record the CLI blocks on.
  H9. (PHASE 2, config `shutdown_after_flat`, default false) if and only if every ack is flat: `self.shutdown_system(f"operator halt {token}")`.

WHY EACH STEP SITS WHERE IT DOES

- Latch before journal (S1 before S3): the journal is disk I/O on the order path and can raise. Every other ordering leaves intake open behind a throwing call.
- Intake closed before any order leaves (S1 before S5): closing orders and opening orders travel the same `submit_order` path. If intake were still open the flatten could race a fresh entry admitted on the same tick, and the run could end non-flat while the journal shows a completed flatten. NT's own MARKET_EXIT_IN_PROGRESS denial covers the exit window; our latch covers everything after it, which is where NT's protection expires (`_cancel_market_exit` clears `_is_exiting` at strategy.pyx:1878).
- Drop the pending intent (S2) AND guard `_on_intent_approved` separately: `SelectorActor` batches on a 100ms time alert (actors/selector.py:81-91) and `_on_intent_approved` (base.py:255-264) checks only strategy_id, FSM state and intent_id - it never reads any halt state. Today that produces a brand-new entry order roughly 100ms after the operator hits the switch. Two lines, deliberately redundant: the property must be readable at the exact site where an intent becomes an order.
- Verify in `post_market_exit`, never in `on_market_exit` and never after calling `market_exit()`: "flat" is a fact about the cache and the portfolio, not a consequence of having sent orders. Both sources must agree, because `market_exit` and the cache queries are strategy_id-scoped and only the portfolio surfaces exposure no strategy owns.
- No shutdown at the trip (H7): VERIFIED FATAL otherwise. `_on_shutdown_system` sets `set_backtest_force_stop(True)` synchronously (system/kernel.py:632-634); FORCE_STOP breaks the run loop (backtest/engine.pyx:1668) and returns before `_process_and_settle_venues` and `_flush_accumulator_events` (engine.pyx:1750-1763). The closing orders never settle. In live it is less catastrophic but still stops the supervisor while residuals may remain.
- No `TradingState` at the trip: HALTED denies the flatten's own closing SubmitOrders (risk/engine.pyx:1136-1148); REDUCING is directional-only and never reads `reduce_only` (risk/engine.pyx:1149-1179), so on fresh 0DTE legs it blocks nothing.
- Startup: the strategy checks the file itself in `on_start`, and does not rely on the actor's publish. `Trader._start` (trading/trader.py:254-264) starts EVERY actor before ANY strategy, so an actor publish at its own `on_start` reaches zero subscribers, and the first poll republish (H6) arrives `poll_secs` later - by which time the plumbing strategy has already entered (first fill lands by roughly engine tick 2). One `exists()` before any data removes the race entirely.

THE PROPERTY THIS BUYS, stated exactly: zero journal entries whose event is in {ORDER_SUBMIT, GREEK_PASSED} and zero FSM_TRANSITION to PendingEntry at any index greater than the index of HALT_LATCHED, in `Journal.load` append order. That is a total-order property of a synchronous single-threaded message bus, and it is checkable from the journal exactly as the journal exists today. It is NOT a latency claim.

## Task plan

| ID | Title | Size | Status |
| --- | --- | --- | --- |
| H0 | Runs-dir env seam and the tests/ tripwire (stops pytest writing the operational audit trail) | medium | DONE e9900ca |
| H1 | Journal.load tolerates a torn trailing line | small | DONE deec460 |
| H2 | Truth-first documentation correction: risk.md, decisions D8, and the stale state diagram | small | not started |
| H3 | Route flatten through NT market_exit, verify flat, and stop asserting flatness from the first fill | large | not started |
| H4 | Halt trip-file service, bus contract and config (no NT import, no behaviour yet) | medium | not started |
| H5 | Strategy halt latch, intake guards, and the startup pre-check | large | not started |
| H6 | HaltActor: poll, trip, republish, aggregate acks (and prove it does not shut the node down) | medium | not started |
| H7 | Operator CLI: halt blocks and its exit code means something (the reported defect) | medium | not started |
| H8 | Failure-injection integration tests, the anti-vacuity control, CI, and the final risk.md row | large | not started |
| H9 | manage_stop in the paper and live profiles only, as its own commit | small | not started |
| H2.5 | Record the unverified Deribit combo-position assumption as a blocking precondition for H3 | small | not started |

**H2.5 was added 2026-09-06 by Akash** after review. `strategies/reference.py:150-167`
trades the Deribit combo as ONE instrument (the vertical is already atomic); the perp hedge
is a second instrument. NT's `market_exit` iterates a `cdef set[InstrumentId]`, so unwind
order is nondeterministic. It is UNVERIFIED whether Deribit reports a combo fill as one
position on the combo or decomposes it into two leg positions. If it decomposes, closing
the long leg first leaves a NAKED SHORT CALL - unbounded loss. Settle this on testnet
(open a combo, inspect `cache.positions_open()`, record one-vs-two) BEFORE H3 lands.

### H0 - Runs-dir env seam and the tests/ tripwire (stops pytest writing the operational audit trail)  [DONE e9900ca]

**Why.** Running `pytest` from the repo root today appends NODE_START, NODE_STOP and a WARN-level FLATTEN_REQUEST into `runs/latest.jsonl` - byte-indistinguishable from a real paper session, because `JournalEntry` is frozen and carries no provenance field. This must land FIRST, before any halt work, because the trip file lives under `runs/` too: a stray trip file written by pytest into the operator's real `runs/halt/` would kill their next live session at startup, which is strictly worse than the journal pollution it inherits.

**Files.** `src/nautilus_zerodte/config/strategy.py`, `tests/conftest.py`, `tests/unit/test_config.py`, `tests/unit/test_cli.py`, `.env.example`, `CLAUDE.md`, `docs/decisions.md`, `INDEX.md`

**Detail.** Extract a private `_resolve_under_runs(path_str: str, runs_dir: Path | None) -> Path` from the body of `resolved_journal_path` (config/strategy.py:106-114), keeping the absolute-path early return and the leading-"runs"-segment strip byte-identical, and change only the base: `base = runs_dir or Path(os.environ.get("ZERODTE_RUNS_DIR") or "runs")`. Precedence is explicit argument > env var > "runs", so with the variable unset the behaviour is byte-identical to today. This is the ONE chokepoint all six production callers already funnel through (cli/main.py:81 and :182, node/factory.py:53/:72/:93, node/wiring/actors.py:32) - one guard there is a smaller diff than one per caller. The env read goes in the resolver, NOT in `config/loader.py:_apply_env_overrides`, because a directly constructed `AppConfig()` (tests/unit/test_factory.py:19) bypasses the loader entirely; add a documentation-only mirror in `_apply_env_overrides` if you want the symmetry.

Create `tests/conftest.py` - there is none anywhere in the repo. Two autouse fixtures, both FUNCTION-scoped: (1) `monkeypatch.setenv("ZERODTE_RUNS_DIR", str(tmp_path / "runs"))`; (2) a tripwire that snapshots the repo's own `runs/` directory (existence, plus `{name: (size, st_mtime_ns)}`) before and after each test and asserts it unchanged, with the failure message naming the offending test. Function scope over session scope deliberately: a session-scoped tripwire tells you the suite dirtied `runs/` but not which test did it.

Explicitly REJECTED, with reasons that must go in a comment so nobody re-proposes them: `monkeypatch.chdir(tmp_path)` breaks the eight tests that pass repo-relative profile paths to `load_config` (test_config.py:11,26,34,50 and test_config_wiring.py:26,35,43,53) with a failure that reads like a config bug; monkeypatching `resolved_journal_path` turns its own three tests at test_config.py:77-91 into assertions about the patch; a test-only profile in `configs/profiles/` can only hold a relative path (same problem, relocated) or an uncommittable absolute one, and drops a fake profile where `paper -c` can pick it up.

The three tests at tests/unit/test_config.py:77-91 pin the resolver's own behaviour and one asserts the bare default - each needs `monkeypatch.delenv("ZERODTE_RUNS_DIR", raising=False)` or the autouse fixture silently turns them into checks about the fixture. Delete the `patch.dict("os.environ", {}, clear=False)` wrapper at tests/unit/test_cli.py:54: it isolates nothing while reading exactly like isolation.

Add `ZERODTE_RUNS_DIR` to `.env.example` (name only) and one clause to the config-layering line in CLAUDE.md. Add decision D9 for the env seam.

**Tests.** 1. `test_repo_runs_dir_untouched` (the autouse tripwire itself). RED BY: revert the env fallback in `_resolve_under_runs` to `base = runs_dir or Path("runs")`, OR delete the setenv fixture. Either way tests/unit/test_cli.py:44 and :53 append three records to the repo's real runs/latest.jsonl and the tripwire fails naming them. Confirmed on disk before designing this: runs/latest.jsonl currently holds exactly NODE_START, NODE_STOP {reason: dry_run} and FLATTEN_REQUEST at 20:30:53.527/.530/.594Z - 3ms and 64ms apart, machine speed, not two commands typed by a human - with .pytest_cache/v/cache/nodeids written two seconds later and no lastfailed file, i.e. a green full-suite run.
2. `test_resolved_journal_path_uses_env_when_no_arg`: with ZERODTE_RUNS_DIR=/tmp/x, resolves to /tmp/x/latest.jsonl. RED BY: revert the same line.
3. `test_resolved_journal_path_explicit_arg_beats_env`: passing runs_dir wins over the env var. RED BY: swap the precedence order.
4. `test_resolved_journal_path_default_unchanged` (with delenv): still `Path("runs/latest.jsonl")`. Labelled in its docstring as a regression PIN, not a guardrail - it passes on both old and new code by design, and saying so is better than counting it as coverage.
5. `test_absolute_journal_path_ignores_runs_dir_and_env`: an absolute `journal.path` returns verbatim. RED BY: move the absolute-path early return below the base computation.

**Risk.** The autouse env fixture leaks into every test in the suite. If the three delenv calls in test_config.py are forgotten, those tests stop testing the default and become checks that cannot fail - which is the exact failure mode docs/testing.md:8 names. Also: `BaseZeroDteStrategyConfig.journal_path` (strategies/base.py:38), `SkeletonStrategyConfig`, `GatedSkeletonStrategyConfig` and `SelectorActorConfig` all default to the literal "runs/latest.jsonl" and never go through `resolved_journal_path`, so the seam does not cover them - the tripwire is what catches a regression there, and that limit should be stated in the conftest comment.

### H1 - Journal.load tolerates a torn trailing line  [DONE deec460]

**Why.** `Journal._append_jsonl` does one open-append-close per record (journal/service.py:124-128) and `Journal.load` parses line by line. The H7 CLI ack loop polls the journal WHILE the node is appending to it, so it will eventually read a partial final line and `JournalEntry.model_validate_json` will raise - crashing the halt command in the middle of the incident it exists to end. That would be a fresh instance of the original defect, and it must be fixed before anything depends on reading a live journal.

**Files.** `src/nautilus_zerodte/journal/service.py`, `tests/unit/test_journal.py`

**Detail.** In `Journal.load`, tolerate a malformed FINAL line only: skip it and return the entries parsed so far. A malformed INTERIOR line is real corruption and must still raise, loudly - silently skipping it would let a truncated audit trail read as a complete one. Implement by parsing all lines, and if the last one fails, retrying without it; do not blanket-wrap every line in try/except. No new dependency, no new config.

**Tests.** 1. `test_load_skips_torn_trailing_line`: write two valid JSONL records plus a truncated third (cut mid-object), assert `load` returns exactly 2 entries and does not raise. RED BY: restore the unconditional `model_validate_json` over every line - fails with a pydantic ValidationError.
2. `test_load_raises_on_malformed_interior_line`: valid, garbage, valid. Assert it raises. RED BY: blanket try/except per line - the test then sees 2 entries and no exception. This is the check that stops the fix from becoming 'silently swallow corruption'.
3. `test_load_on_empty_file_returns_empty`: unchanged behaviour pin.

**Risk.** The 'last line only' rule is subtle. If someone later reads the file with a different splitter (for example `splitlines()` on a file ending in a newline), the torn line may not be last. Keep the rule stated in a comment at the parse site.

### H2 - Truth-first documentation correction: risk.md, decisions D8, and the stale state diagram  [not started]

**Why.** docs/quant/risk.md:23 currently documents a control that does not exist in any of its three claimed forms - FILE exists nowhere in NT, CLI cannot reach the node, and SIGNAL flattens nothing because manage_stop defaults False. The doc must stop lying BEFORE any code lands, so the repo is never in a state where a doc claims something the code does not do. No code changes here, so nothing can regress.

**Files.** `docs/quant/risk.md`, `docs/decisions.md`, `docs/design/state-diagram.puml`, `tests/unit/test_docs.py`, `INDEX.md`

**Detail.** Apply EDIT 1 from the risk_md_correction field verbatim: replace the false row with the NOT IMPLEMENTED row, and add the 'What does not exist, stated plainly' paragraph after the table.

Add decision D8 (the full entry supplied in decision_entry) to docs/decisions.md, newest at the bottom, in the existing `## D<n> - title` / bold Decision / Why / Reversal condition format. Add D9 (the ZERODTE_RUNS_DIR env seam, from H0) if H0 did not already land it.

Fix docs/design/state-diagram.puml, which is already stale against the code before this work: it omits PendingApproval entirely, claims a `PendingEntry -> Flat : cancelled` transition that is not implemented, and draws `InPosition -> Flat` directly on the flatten signal when the code goes `InPosition -> Exiting -> Flat` (base.py:238, :187-191). Add PendingApproval, correct the flatten path. Do not add the Halted state yet - that lands with H5.

Create tests/unit/test_docs.py with a single narrowly scoped content test.

**Tests.** 1. `test_risk_md_makes_no_uncovered_kill_switch_claim`: read docs/quant/risk.md, locate the guardrail table, assert no row simultaneously contains 'Kill switch' and 'within one bar', and assert the operator kill switch row does not claim a signal trigger. RED BY: restore the original line 23 - fails immediately. This is a low-value check by design and its docstring must say so: it pins one specific false claim so it cannot be reintroduced, and it deliberately does NOT try to verify every row, because several rows name a 'Risk actor' that does not exist in src/ and turning them all red at once is a separate scheduling decision (see open_questions).
2. `test_state_diagram_lists_every_strategy_state`: parse the .puml for state names and assert every member of `StrategyState` appears. RED BY: revert the diagram - PendingApproval is missing and it fails. This one is genuinely useful: it makes the diagram fail the day the FSM grows a state, which is exactly how it got stale.

**Risk.** A content test over prose is brittle to rewording. Keep the assertions to the two specific substrings and the enum-name set, not to sentence shapes.

### H3 - Route flatten through NT market_exit, verify flat, and stop asserting flatness from the first fill  [not started]

**Why.** `self.cancel_all_orders()` at strategies/base.py:236 is a hard TypeError against the pinned 1.229.0 - `cancel_all_orders` declares `instrument_id` positionally with no default (trading/strategy.pxd:162, verified). It is the FIRST executable statement of the acting branch, so the session-blackout flatten raises before the EXITING transition and before `submit_exit`, on every tick, with a live position, and the exception escapes into the SessionActor's tick handler because msgbus publish is synchronous and NT re-raises from `handle_quote_tick`. Nothing in tests/ touches `flatten_positions` at all, which is why this has sat there. This task must land before the kill switch, because the kill switch calls exactly this method - wiring an operator control to a broken flatten reproduces the false confidence being fixed.

**Files.** `src/nautilus_zerodte/strategies/base.py`, `tests/unit/test_reference_strategy.py`, `tests/integration/test_session_flatten_backtest.py`, `docs/quant/risk.md`

**Detail.** Rewrite `flatten_positions(self, *, reason: str)` (base.py:227-239):
- `if self.is_exiting(): journal FLATTEN_ALREADY_RUNNING; return`. NT warns and no-ops on a second `market_exit()` (strategy.pyx:1768-1770), which would read as progress.
- If `cache.orders_open(None, None, self.id)`, `cache.orders_inflight(...)` and `cache.positions_open(...)` are all empty: journal FLATTEN_SKIPPED with the state and reason, return. The guard is now the CACHE, not the FSM state - the old FSM guard refused to act in Flat, Evaluating, PendingApproval and Exiting, three of which can hold real exposure or real in-flight intent.
- Otherwise: transition to EXITING when the state is IN_POSITION or PENDING_ENTRY (the guard now governs the LABEL, not whether the flatten happens), then `self.market_exit()`.
- Carry the T1 comment naming the upstream capability and the delete condition: 'stands in for our own cancel + close + retry loop; delete this wrapper when the FSM observes on_market_exit/post_market_exit directly'.

Add `on_market_exit()` override: journal FLATTEN_START with the instrument set and the three cache counts.

Add `post_market_exit()` override: read `orders_open`, `orders_inflight`, `positions_open` filtered by `strategy_id=self.id`, plus `self.portfolio.is_completely_flat()`. All three zero AND portfolio flat -> FLATTEN_COMPLETE `{flat: true, counts}` at INFO, and transition EXITING -> FLAT with reason 'flatten_complete'. Otherwise -> FLATTEN_COMPLETE `{flat: false, counts}` at ERROR, and do NOT transition to Flat. Both sources must agree: `market_exit` and the cache queries are strategy_id-scoped, and only the portfolio surfaces exposure no strategy owns. NO re-arm loop - NT already retried `market_exit_max_attempts` times and gave up naming its residuals.

Fix the first-fill bug at base.py:187-191: the `EXITING -> FLAT on the first OrderFilled` transition has no quantity reconciliation and never consults the cache, so a partially filled multi-leg exit reports Flat with live exposure. Gate the transition on the cache reporting zero open positions and zero open/inflight orders for this strategy; otherwise journal PARTIAL_EXIT_FILL and stay EXITING.

Fix the per-tick flood in `_manage_position` (base.py:517-520): only call `flatten_positions` when `not self.is_exiting()`. SessionActor republishes on every quote tick with no dedupe (session.py:54-55), and `Journal.record` is a synchronous open-append-close, so an unguarded call is one disk write per tick from a market-data callback.

Amend the risk.md interim row's final clause: the session flatten is no longer 'itself untested and currently broken'.

Note the deliberate semantic change for the commit message (docs/testing.md item 3): the flatten now closes leg by leg with NT reduce-only MARKET orders rather than the fixed-quantity IOC combo `submit_exit` sent. `submit_exit` remains for the tp_sl path in reference.py. The old behaviour closed one instrument at a fixed `config.order_qty` regardless of the actual position, so for a vertical plus a perp hedge it would have left legs open - this is a strict improvement, and there are no existing tests to update because there were none.

**Tests.** Unit tests construct the strategy unregistered (the tests/unit/test_reference_strategy.py:17-37 pattern). NOTE: `Actor.cache` and `Actor.portfolio` are `cdef readonly` and CANNOT be assigned - shadow them with properties on a test subclass, exactly as tests/unit/test_selector_actor.py:22-28 already does for msgbus.
1. `test_flatten_calls_market_exit_not_bare_cancel_all`: with a stub cache reporting one open position, `flatten_positions` calls `market_exit` exactly once and never calls `cancel_all_orders` with zero arguments. RED BY: restore `self.cancel_all_orders()` - raises TypeError. This is the hard-rule-2 bug-fix test; watch it red on the unfixed line in the container before restoring.
2. `test_post_market_exit_does_not_claim_flat_with_residuals`, three cases: (a) all cache counts zero and `is_completely_flat()` True -> FLATTEN_COMPLETE flat:true at INFO; (b) cache reports one position -> flat:false at ERROR; (c) cache empty but `is_completely_flat()` False -> flat:false. RED BY: journal flat:true unconditionally -> (b) and (c) red. RED BY (separately): check only the cache -> (c) red. Case (c) is the one that fails any single-source implementation.
3. `test_partial_exit_fill_does_not_report_flat`: state EXITING, deliver one OrderFilled while the stub cache still reports an open position -> state stays EXITING, a PARTIAL_EXIT_FILL record exists, no FSM_TRANSITION to Flat. RED BY: restore the unconditional transition at base.py:187-191.
4. `test_flatten_on_empty_book_journals_skipped_not_complete`: empty cache -> FLATTEN_SKIPPED, no FLATTEN_START, no `market_exit` call. RED BY: drop the cache guard - a FLATTEN_START appears. This keeps 'the book was already empty' and 'we closed the book' as different observable outcomes.
5. `test_manage_position_does_not_reflatten_while_exiting`: with `is_exiting()` True, ten `_manage_position` calls produce zero new journal records. RED BY: drop the `not self.is_exiting()` guard - ten FLATTEN_ALREADY_RUNNING records appear, one disk write each.
6. INTEGRATION `test_session_blackout_flatten_actually_flattens` (new file): backtest_reference.yaml with `backtest_plumbing`, journal on tmp_path, and `market_close_utc` chosen so the blackout begins MID-RUN, computed from the catalog bounds - NOT tick one. The existing tests/integration/test_gate_backtest.py sets market_close_utc 14:45 against a fixture starting 14:30:00 with a 30-minute blackout, so that run is in blackout from the first tick and the strategy is never in a position; it proves nothing about flattening and is precisely why the TypeError was never seen. Assert on `Journal.load` APPEND order (never `entry.ts` - models/journal.py:18 is `datetime.now`): FSM_TRANSITION to InPosition at a LOWER index than FLATTEN_START, then a closing FILL, then FLATTEN_COMPLETE flat:true with all counts zero. RED BY: restore the old `flatten_positions` body - the run raises the TypeError out of the synchronous handler.

**Risk.** This changes an existing behaviour with zero prior test coverage, so there is no 'old test read and deliberately updated' - there was nothing to read. State that in the commit message rather than letting it look like the tests were always absent for a good reason. Also: `reference.py`'s one-shot latches `_exit_submitted` and `_hedge_submitted` are never reset on the return to Flat, so after one tp_sl exit that path is dead for the life of the object. Out of scope here, but it means flatten becomes the only way out and its reliability matters more than it looks - file it.

### H4 - Halt trip-file service, bus contract and config (no NT import, no behaviour yet)  [not started]

**Why.** The transport and the payload are pure data with no engine dependency, so they can land and be fully tested on any platform - including this Intel Mac, where nautilus_trader cannot be imported at all. Landing them separately means the actor and strategy tasks that follow are small and reviewable.

**Files.** `src/nautilus_zerodte/models/halt.py`, `src/nautilus_zerodte/actors/data_types.py`, `src/nautilus_zerodte/config/strategy.py`, `src/nautilus_zerodte/config/schema.py`, `configs/base.yaml`, `tests/unit/test_halt_file.py`, `.env.example`, `INDEX.md`

**Detail.** `src/nautilus_zerodte/models/halt.py` - deliberately in models/, not actors/, so the CLI can import it without pulling in an Actor and therefore without importing nautilus_trader:
- `HALT_FILE_SCHEMA = 1`; frozen pydantic `TripRecord(schema_version, token, reason, requested_at_utc, requested_by, trader_id)`.
- `trip_path(runs_dir: Path, trader_id: str) -> Path` returning `runs_dir / "halt" / f"{trader_id}.trip"`. The trader_id goes in the FILENAME, not the body: the hot poll becomes one `exists()` on a fixed path with nothing to read, nothing to parse and nothing to compare, and two nodes on one box structurally cannot cross-kill each other.
- `write_trip(path, record)`: write to `<path>.tmp` in the SAME directory, then `os.replace`. Atomic rename, so a half-written file can never be observed by the poller.
- `read_trip(path) -> TripRecord | None`: returns None ONLY when the file is absent. A present-but-unparseable file returns a TripRecord with reason 'unparseable_trip_file'; a present-but-unreadable file (OSError) returns one with reason 'trip_file_unreadable'. T5: a control file we cannot read is not a reason to keep trading.
- `clear_trip(path) -> bool`.

`actors/data_types.py`: add `HALT_TOPIC = "control.halt"` and `HALT_ACK_TOPIC = "control.halt.ack"`, plus frozen slotted `HaltSnapshot(token, reason, source)` and `HaltAckSnapshot(strategy_id, token, flat, orders_open, orders_inflight, positions_open, portfolio_flat)`. A NEW topic outside NT's `data.` prefix, not a new field on SessionPhaseSnapshot: two publishers on one topic breaks single-writer-per-state, the next SessionActor quote tick would overwrite the halt state, and `MessageBus.subscribe` supports `*` wildcards so a `data.*` subscriber would be handed a control message.

`config/strategy.py`: new `HaltConfig` next to `JournalConfig` (strategy.py, NOT venue.py - a node-level operator control is not venue knowledge, hard rule 1):
  enabled: bool = False            # base.yaml default false; true only in paper and live profiles
  poll_secs: float = 1.0           # range 0.25 to 5.0; THIS is the trip-to-first-cancel bound
  ack_timeout_secs: float = 30.0   # range 5 to 120; 3x the exit budget so a healthy exit acks first
  market_exit_interval_ms: int = 100      # NT default; range 50 to 500
  market_exit_max_attempts: int = 60      # 6.0s budget. NT's default of 100 gives 10.0s, which
                                          # exactly equals NT's default timeout_post_stop of 10.0s
  market_exit_reduce_only: bool = True    # false ONLY for a venue rejecting reduce_only on options
  timeout_post_stop_secs: float = 20.0    # NautilusKernelConfig.timeout_post_stop; range 15 to 60
  shutdown_after_flat: bool = False       # PHASE 2. Ships false with a test that it does not fire.
Add a `model_validator` raising ValueError naming both numbers when `market_exit_interval_ms * market_exit_max_attempts / 1000 >= timeout_post_stop_secs`. NT ships those two as an exact 10.0-vs-10.0 tie between the exit finishing and the exec clients disconnecting; catching it at config load is the point.
Add `AppConfig.halt` and `AppConfig.resolved_halt_trip_path(runs_dir=None) -> Path`, sharing `_resolve_under_runs` from H0 so the trip file inherits the same seam and the same tripwire.

`config/schema.py`: add HaltConfig to the imports and `__all__` - the file has zero definitions of its own and is a pure re-export facade, so anything not listed there breaks `from ...config.schema import X`.

`configs/base.yaml`: the `halt:` block with `enabled: false` and every knob commented with its range and reason (docs/testing.md definition-of-done item 5). base.yaml is the first merge layer so every profile inherits it, and the profile is deep-merged twice (loader.py:83 and :114-116) so a profile always wins. Do NOT put it in configs/risk/default.yaml, whose sibling conservative.yaml is never loaded at all.

**Tests.** 1. `test_unparseable_trip_file_is_still_a_trip`: parametrise over a corpus of malformed inputs (truncated JSON, valid JSON that is not an object, an object missing `token`, an unknown schema_version). Every one returns a TripRecord, never None and never an exception. RED BY: write the obvious implementation, `try: return TripRecord(**json.loads(text)) except Exception: return None`. The docstring must name that as the plausible-wrong answer, because returning None reads like the careful thing to do and is the fail-open one.
2. `test_read_trip_returns_none_only_when_absent`: absent -> None; present-and-empty -> a TripRecord. RED BY: treat an empty file as absent.
3. `test_trip_path_is_per_trader`: two trader ids give two different paths, and both sit under `<runs>/halt/`. RED BY: collapse to a shared `runs/halt.json` - both ids resolve to one path, so two nodes on one box cross-kill.
4. `test_write_trip_never_leaves_a_partial_target`: patch `os.replace` to raise, call `write_trip`, assert the target path does not exist. RED BY: replace the tmp-plus-replace with `path.write_text(...)`.
5. `test_halt_config_rejects_exit_budget_exceeding_post_stop`: `HaltConfig(market_exit_interval_ms=100, market_exit_max_attempts=100, timeout_post_stop_secs=10.0)` raises ValidationError naming both numbers. RED BY: delete the model_validator. Note this case is NT's own shipped default pairing.
6. `test_resolved_halt_trip_path_follows_runs_dir_seam`: honours ZERODTE_RUNS_DIR and an explicit argument, same precedence as the journal. RED BY: hardcode `Path("runs")` in `resolved_halt_trip_path` - the trip file then escapes the H0 tripwire and pytest can arm the operator's real kill switch.

**Risk.** Topic strings are not covered by hard rule 8 today (only journal event names, gate stages and transition reasons are), so `control.halt` is cheap to name now and expensive later. Fix it in this task and do not rename it afterwards. Separately, `INGESTION_PLAN_TOPIC` is published with zero subscribers - proof that a topic can be added, wired and consumed by nobody without any test failing, which is why H5's and H8's tests assert on the CONSUMER, never on the publish.

### H5 - Strategy halt latch, intake guards, and the startup pre-check  [not started]

**Why.** The latch is the primary control and the only thing that survives the exit completing - NT's own `_is_exiting` clears itself in `_cancel_market_exit`, which is exactly the moment re-entry becomes possible again. Without the latch, the FSM returns to FLAT on the exit fill and the very next quote tick re-evaluates and re-enters, roughly one tick after the operator hit the switch.

**Files.** `src/nautilus_zerodte/strategies/base.py`, `src/nautilus_zerodte/models/enums.py`, `src/nautilus_zerodte/node/wiring/strategy.py`, `tests/unit/test_reference_strategy.py`, `docs/design/state-diagram.puml`

**Detail.** `BaseZeroDteStrategyConfig` gains `halt_trip_path: str | None = None`, threaded in by `node/wiring/strategy.py` from `config.resolved_halt_trip_path()` when `config.halt.enabled`.

`__init__`: `self._halted = False`, `self._halt_token = None`, `self._halt_reason = None`. `_halted = False` appears in exactly this one place in the whole file, forever.

Add `StrategyState.HALTED = "Halted"` to models/enums.py. Additive, so safe under hard rule 8 (adding a member is additive; renaming one is breaking). Then re-read every early-return guard that is written as `!= FLAT` or `not in {A, B}` - base.py:137, :148, :194, :211, :229, :245, :258, :269 and reference.py:191, :278 - and decide deliberately which side of each test the new state falls on. Do not let it inherit a side by accident.

`on_start`: after the existing subscriptions, `self.msgbus.subscribe(topic=HALT_TOPIC, handler=self._on_halt)`; then, if `config.halt_trip_path` is set and the file exists, call `self._latch_halt(reason, token, source="startup")` BEFORE `_subscribe_market_data()`. This is the fix for a verified race: `Trader._start` (trading/trader.py:254-264) starts EVERY actor before ANY strategy, so a HaltActor publish at its own on_start reaches zero subscribers, and the actor's first poll republish arrives `poll_secs` later - by which time the plumbing strategy has entered (first fill lands by roughly engine tick 2, i.e. 200ms of engine time, against a 1.0s poll). One `exists()` before any data has no timing dependence at all. `on_stop`: unsubscribe HALT_TOPIC.

`_on_halt(msg)`: `if self._halted: return` (so the actor's republish is a cheap no-op), else `self._latch_halt(msg.reason, msg.token, source=msg.source)`.

`_latch_halt(reason, token, source)` executes the S1-S5 sequence from the ordering spec, in that exact order, with the latch as the first executable statement and the journal write second - because `Journal.record` opens a file and can raise.

Intake guards, as the FIRST statement of each: `on_option_chain`, `on_quote_tick`, `_begin_evaluation`, `_submit_approved_intent`. In `_on_intent_approved`, BEFORE the state check: `if self._halted: journal HALT_INTAKE_BLOCKED {what: "intent_approved", intent_id}; self._pending_intent = None; return`. This closes the verified ordering hole - `_on_intent_approved` (base.py:255-264) checks only strategy_id, FSM state and intent_id and never reads any halt state, and SelectorActor's approval arrives asynchronously on a 100ms batch alert (actors/selector.py:81-91). The guard in `_latch_halt` (clearing `_pending_intent`) and the guard here are BOTH kept, deliberately: two lines, and the property is then readable at the exact site where an intent becomes an order.

`_build_gate_context` (base.py:449-478): add `trading_state_active=not self._halted`. The field exists at gates/context.py:24 and `evaluate_operational` already appends the breached rule `trading_state_inactive` (gates/evaluator.py:69-70) - nothing in src/ has ever set it False, so this makes existing wiring live rather than adding a gate. Note `.cursor/plans/aggressive_repo_cleanup_7f5abe36.plan.md:72` proposes deleting the unrelated `GateContext.flatten_signal` as dead; that remains dead and is a separate call - do not confuse the two fields.

`post_market_exit` (from H3): when `self._halted`, also publish `HaltAckSnapshot` on HALT_ACK_TOPIC with the counts it already read.

`on_order_filled`, first guard: if `self._halted`, journal HALT_LATE_FILL at WARN. This is the mid-entry case - the trip cancels the working entry but a fill already at the venue can still arrive.

Update the state diagram with the terminal Halted state.

**Tests.** All unit, strategy constructed unregistered, cache/portfolio shadowed by properties on a test subclass (they are `cdef readonly`).
1. `test_halt_latch_has_no_reset_path` (STATIC): read the source of strategies/base.py and assert `_halted = False` occurs exactly once. RED BY: add any reset path anywhere. A latch's whole value is that it has no setter, and that is not expressible as a runtime assertion.
2. `test_halt_survives_a_permissive_session_snapshot`: latch, then deliver `SessionPhaseSnapshot(allows_entry=True, flatten_signal=False, ...)` and a quote tick. Assert still halted and no evaluation began. RED BY: write `self._halted = msg.halted` in `_on_halt` - the natural mirror of `self._flatten_signal = msg.flatten_signal` sitting two lines away at base.py:244.
3. `test_intent_approved_after_halt_is_refused`: selector_enabled True, drive to PENDING_APPROVAL with a `_pending_intent`, latch, then deliver the matching TradeIntentApprovedSnapshot. Assert `submit_entry` never called, no ORDER_SUBMIT record, a HALT_INTAKE_BLOCKED record present, `_pending_intent` None. RED BY: remove the guard in `_on_intent_approved` alone - an ORDER_SUBMIT appears. The test MUST set selector_enabled: written against the default config it passes while the hole stays open. This is the single most important unit test in the set.
4. `test_latch_is_set_before_the_journal_write`: patch `Journal.record` to raise on its first call; assert `_on_halt` propagates the exception AND `self._halted` is True afterwards. RED BY: move the journal call above the latch assignment - `_halted` is False and intake is open behind a throwing disk write.
5. `test_halted_gate_context_is_operationally_inactive`: `_build_gate_context(ctx).trading_state_active is False`, and `evaluate_pre_greek` returns passed False with failed_stage OPERATIONAL and 'trading_state_inactive' in breached_rules. RED BY: revert the one line in `_build_gate_context`.
6. `test_startup_with_trip_file_present_latches_before_market_data`: construct with `halt_trip_path` pointing at an existing trip file, call `on_start`, assert `_halted` True, a HALT_LATCHED record with source 'startup', and that `_subscribe_market_data` was called after the latch. RED BY: delete the on_start pre-check - it goes red while every other test stays green, which is the actors-start-before-strategies race made visible.
7. `test_halt_when_already_exiting_does_not_call_market_exit_twice`: with `is_exiting()` True, `_on_halt` journals HALT_EXIT_ALREADY_RUNNING and calls `market_exit` zero times. RED BY: drop the S4 guard - NT logs a warning and no-ops, which would read as progress.
8. `test_halt_exit_failure_still_leaves_the_strategy_latched`: make `market_exit` raise; assert `_halted` True, HALT_EXIT_FAILED at ERROR, and a HaltAck with flat False. RED BY: remove the try/except - the exception escapes and no ack is ever published, so the CLI times out to exit 4 instead of the accurate exit 3.

**Risk.** Adding a terminal FSM state touches every `!= FLAT` / `not in {...}` guard in two files. Reviewing those ten sites is the bulk of the risk in this task, not the latch itself. Also: the strategy now reads a file in `on_start`. That is one `exists()` before any data, not on the order path - but it is a second reader of the trip file and must be documented as such, because the single-writer rule is about writers, not readers.

### H6 - HaltActor: poll, trip, republish, aggregate acks (and prove it does not shut the node down)  [not started]

**Why.** The runtime observer. It is the only component that reaches out to external state, so it is the one place T6 is under pressure and the one place a mistake (shutting down at trip) is verifiably fatal.

**Files.** `src/nautilus_zerodte/actors/halt.py`, `src/nautilus_zerodte/node/wiring/actors.py`, `configs/profiles/paper_spy.yaml`, `configs/profiles/paper_btc.yaml`, `tests/unit/test_halt_actor.py`, `INDEX.md`

**Detail.** `HaltActorConfig(ActorConfig, frozen=True)`: journal_path, runs_dir, trader_id, poll_secs, ack_timeout_secs, expected_strategy_ids, shutdown_after_flat.

`HaltActor(Actor)`:
- `on_start`: subscribe HALT_ACK_TOPIC; compute `self._trip_path = trip_path(Path(runs_dir), trader_id)` once; if it exists, `self._trip(source="startup")`; then `self.clock.set_timer("halt_poll", timedelta(seconds=poll_secs), callback=self._on_poll)` - the engine clock, TestClock in backtest and LiveClock in live with no code difference, following actors/selector.py:81-89.
- `_on_poll`: `if self._halted: self._republish(); return` - NO file read once tripped, so steady-state disk cost after the trip is exactly zero, and the republish is a cheap bus publish that catches any strategy that started late. Otherwise `if self._trip_path.exists(): self._trip(source="file")`. One `exists()` on a fixed path per poll, no read, no parse, no glob, because the trader_id is in the filename.
- `_trip(source)`: exactly H1 to H5 from the ordering spec - read once (fail-closed), latch, journal HALT_TRIP at WARN carrying `engine_ts_ns=self.clock.timestamp_ns()`, publish HaltSnapshot, arm the ack-timeout `set_time_alert`. It calls `shutdown_system` NOWHERE.
- `_on_ack(msg)`: collect into `{strategy_id: ack}` against `expected_strategy_ids`; when every expected id has answered, finalise.
- `_finalise(timed_out: bool)`: journal HALT_ACK at INFO when every ack has `flat` True and not timed out, else at ERROR, with `{token, flat, timed_out, per_strategy: {...}}`. Then, ONLY if `shutdown_after_flat` and every ack is flat, `self.shutdown_system(f"operator halt {token}")` - ships defaulted false, phase 2.
- `on_stop`: cancel timers via `self.clock.timer_names`, as SelectorActor does at selector.py:54-55.

`node/wiring/actors.py`: append a conditional `ImportableActorConfig` for HaltActor when `config.halt.enabled`, following the SelectorActor (:31) and IngestionPlannerActor (:45) precedent exactly. Thread `str(config.resolved_journal_path())`, `str(config.resolved_halt_trip_path().parent.parent)` (the runs dir), `config.trader_id`, the knobs, and `expected_strategy_ids=[s.strategy_id for s in config.resolved_strategies()]`. The gate MUST stay a config flag - `actor_configs()` feeds both `build_backtest_node` (factory.py:57) and `build_trading_node` (factory.py:77), so an unguarded append puts a file-polling actor into every golden backtest (a T2 determinism break), and an `if live:` branch here would be a T4 violation.

`configs/profiles/paper_spy.yaml` and `paper_btc.yaml`: `halt: {enabled: true}`. Backtest profiles inherit `enabled: false`; the guardrail test in H8 turns it on by `model_copy`, which is config, not a mode flag.

**Tests.** Unit, with the `_FakeMsgBus` plus property-override subclass pattern from tests/unit/test_selector_actor.py:13-28.
1. `test_trip_publishes_halt_and_never_shuts_down`: record published topics in order; assert the list is exactly `[HALT_TOPIC]` and that 'commands.system.shutdown' does not appear. RED BY: add `self.shutdown_system(...)` to `_trip`. This is the guard on the verified backtest-fatal behaviour: `_on_shutdown_system` sets FORCE_STOP synchronously (kernel.py:632-634), FORCE_STOP breaks the run loop (engine.pyx:1668) and returns before `_process_and_settle_venues` and `_flush_accumulator_events` (engine.pyx:1750-1763), so the closing orders never settle.
2. `test_trip_is_once_only_and_stops_reading_the_file`: patch `read_trip` with a call counter; after the trip, ten more `_on_poll` calls read the file zero more times AND republish the same snapshot with the same token each time. RED BY: drop the `if self._halted` early return - the counter goes up, turning a performance claim into an assertion. RED BY (separately): drop the republish - a late-starting strategy would never hear the halt.
3. `test_startup_with_existing_trip_file_trips_in_on_start`: assert the publish happens during `on_start`, not on the first poll. RED BY: implement `on_start` as 'set the timer' only - which is what you write if you think of this as a watcher rather than as durable state.
4. `test_ack_timeout_journals_error_not_success`: no acks arrive, fire the timeout alert -> HALT_ACK at ERROR with `timed_out: true` and `flat: false`. RED BY: journal INFO / flat true on timeout - silence must never read as success.
5. `test_ack_aggregation_requires_every_expected_strategy`: with two expected ids and one flat ack, nothing is finalised until the second arrives or the timeout fires. RED BY: finalise on the first ack.
6. `test_shutdown_only_fires_when_every_ack_is_flat`: with `shutdown_after_flat=True`, one ack flat False -> no shutdown publish; all flat -> one shutdown publish. RED BY: shutdown on timeout, or on any ack. Ships with the config defaulted False, so this test is what stops phase 2 being wired wrongly later.
7. `test_unparseable_trip_file_still_trips_the_actor`: RED BY: `if record is None: return` treated as covering the unparseable case.

**Risk.** The file poll is disk I/O inside an engine callback and T6 forbids that flatly. One `exists()` per second on a local path, zero after the latch, from a timer callback rather than a data callback, and strictly less than the open-append-close the order path already pays per journal record - but 'smaller than an existing violation' is an argument for decision D8 with a reversal condition, not an exemption. HARD REQUIREMENT to state in the config comment and in risk.md: the trip file must live on a LOCAL filesystem. A stat on a hung NFS mount blocks the whole engine loop.

### H7 - Operator CLI: halt blocks and its exit code means something (the reported defect)  [not started]

**Why.** This is the defect. An operator types `flatten` during a live drawdown, sees exit code 0 and a reassuring message, and believes they are flat. The command loads config, appends one JSONL line, prints, and exits 0; nothing in src/ reads FLATTEN_REQUEST. Every exit code below is downstream of a cache read inside a running node, not of a file write.

**Files.** `src/nautilus_zerodte/cli/main.py`, `tests/unit/test_cli.py`, `README.md`

**Detail.** Replace the `flatten` body (cli/main.py:177-197). New command `halt`:
  --config/-c (required), --reason (required), --wait-secs (default 30.0), --token (HIDDEN, defaults to uuid4).
1. Exit 2 immediately if `config.halt.enabled` is False for that profile. No false comfort from a profile that has no switch.
2. Print BOTH resolved paths - the trip file and the journal - before doing anything, so a working-directory mismatch between the CLI and the node is visible rather than silent (the failure is fail-closed but produces exit 4 for the wrong reason, which is a bad five minutes during a drawdown).
3. Write the trip file atomically via `write_trip`; journal HALT_REQUEST at WARN carrying the token.
4. BLOCK: poll `Journal.load` every 250ms (bounded loop, `time.sleep` only) up to `--wait-secs`, looking for a HALT_ACK whose token matches.
5. Exit 0 ONLY on HALT_ACK with `flat: true`, printing 'Flat confirmed by every configured strategy'. Exit 3 on HALT_ACK with `flat: false`, naming which strategy is not flat and its residual counts, and saying to check the venue UI. Exit 4 on no ack, printing 'NO RUNNING NODE ACKNOWLEDGED THIS HALT. YOU ARE NOT FLAT.' plus the note that the trip file stays armed so the next node to start comes up halted.
The `--token` hidden option is the deterministic seam for the exit-0 test - stable where patching uuid4 at the call site is brittle.

The journal event is HALT_REQUEST, not FLATTEN_REQUEST. That is a hard-rule-8 public-API break and needs a migration note in the commit message and in README: the old FLATTEN_REQUEST meant 'nothing happened', and reusing the name would make old and new journals indistinguishable. Keep `flatten` as an alias that prints one deprecation line and calls `halt` - operators have muscle memory and a kill switch is the wrong place to make someone re-learn a name.

New `halt-status -c <profile>`: print both resolved paths, the trip file contents if present, and the last HALT_* journal records.
New `halt-clear -c <profile> --token <token> [--force]`: delete the trip file, journal HALT_CLEARED. Refuse when a HALT_ACK is newer than the last NODE_STOP (a node appears to be running) unless --force. State in the help text that clearing does NOT un-halt a running node - the in-process latch has no setter - it only allows the next node start to come up unhalted.

`paper`: pre-flight refusal. Exit non-zero, naming `halt-clear`, when a trip file exists for this trader_id. Without it an operator kills a node, restarts it, and gets a node that could trade in the window before the strategy's on_start check runs - which H5 closes, but the refusal is the outer belt.

Note for the commit message: this loop uses wall clock (`time.sleep` and a deadline), which `cli/` already does at main.py:34. See open_questions on whether `cli/` joins `node/adapters/` in T3's documented exclusion - do not widen the tenet quietly here.

**Tests.** 1. `test_halt_exits_4_when_no_node_acknowledges`: against a profile with halt enabled, `--wait-secs 0.2`, assert `exit_code == 4`, 'YOU ARE NOT FLAT' in output, and the trip file present on disk afterwards. RED BY: restore the shipped `flatten` body (load config, one journal record, one echo, implicit return) - it exits 0. THIS IS THE REGRESSION TEST FOR THE REPORTED DEFECT and it must be watched red on the unfixed command before anything else.
2. `test_halt_exit_code_distinguishes_acked_from_flat` (parametrised): pre-seed the tmp journal with HALT_ACK {token: 'pinned', flat: true} and invoke with `--token pinned` -> exit 0; re-seed with flat false -> exit 3 and the message names the non-flat strategy. RED BY: make the ack loop exit 0 on any HALT_ACK with a matching token, ignoring the `flat` field - the natural shortcut - and the second case goes red. This keeps 'the node answered' and 'the node is flat' as different outcomes.
3. `test_halt_exits_2_when_switch_disabled`: a profile with `halt.enabled: false` -> exit 2, and NO trip file is written. RED BY: delete the check - the operator gets a trip file nobody is polling and a 30-second wait ending in exit 4.
4. `test_halt_ignores_an_ack_with_a_different_token`: seed a flat HALT_ACK carrying someone else's token -> still exit 4. RED BY: match on the event name only - a stale ack from a previous halt would report success for this one.
5. `test_paper_refuses_to_start_with_a_trip_file_present`: non-zero exit and the message names `halt-clear`. RED BY: delete the pre-flight.
6. `test_halt_clear_removes_the_trip_file_and_is_idempotent`: clear -> exit 0 and file gone; clear again -> exit 0 and 'not armed'. RED BY: raise on a missing file.
7. `test_halt_reads_a_journal_being_appended_to`: seed a journal whose final line is truncated, then the matching ack - assert no crash and the correct exit code. RED BY: revert H1. This is what connects H1 to the reason it exists.
8. Rewrite `test_flatten_command_smoke` (test_cli.py:53-64): its `assert result.exit_code == 0` IS the defect, so it is deliberately replaced rather than adjusted, per docs/testing.md 'changed behaviour gets its old test read and updated deliberately'. Keep one test asserting the `flatten` alias still runs and prints the deprecation line.

**Risk.** The reverse channel is the journal file, resolved from CWD in both processes. Launch the CLI from a different directory and it times out to exit 4 while the node did in fact flatten. `halt-status` printing both paths is a mitigation, not a fix; the real fix is an absolute runs dir in the operator profiles, which cannot be committed - see open_questions.

### H8 - Failure-injection integration tests, the anti-vacuity control, CI, and the final risk.md row  [not started]

**Why.** T12: a guardrail with no test that trips it does not exist, and a guardrail test CI does not execute is the same class of defect as the doc row that started this. The final risk.md row lands in THIS commit and no earlier, so the doc never claims something the code has not been shown to do.

**Files.** `tests/integration/test_halt_backtest.py`, `.github/workflows/ci.yml`, `docs/quant/risk.md`, `INDEX.md`

**Detail.** Bypass `run_backtest` to reach the engine seam (all three NT entry points verified: backtest/node.py:241 `build()`, :138 `get_engine()`, engine.pyx `add_actor`):
  node = build_backtest_node(cfg, catalog); node.build();
  engine = node.get_engine(node.configs[0].id);
  engine.add_actor(_TripWriterActor(...)); node.run()
`_TripWriterActor` is a TEST-LOCAL NT Actor that sets one `clock.set_time_alert` and writes the REAL trip file in the callback. Real failure injection on the engine clock, deterministic, no wall-clock sleep - and it exercises the production file branch end to end rather than a config-only test hook. This is why `halt.armed_at_utc` is deliberately NOT a production knob.
The trip time is derived from the catalog bounds as `start_ns + N * step_ns`, never a literal, so rebuilding the fixture cannot silently move the trip outside the run. The SPY fixture is 100 ticks at 100ms from 2024-01-02T14:30:00Z (scripts/build_catalog_fixture.py:32, :114-121), i.e. 9.9 seconds of engine time. Profile: backtest_reference.yaml with `backtest_plumbing`, journal `model_copy`'d onto tmp_path, `halt: {enabled: true}` and `poll_secs` set to 0.1 so the poll is fast relative to the fixture.
Assert on `Journal.load` APPEND order throughout - append order is causal order for a single-process run. NEVER order by `entry.ts`: it is `datetime.now(tz=UTC)` (models/journal.py:18), i.e. wall clock inside a backtest that compresses seconds into milliseconds, and depending on it would itself be a T3 violation in the test layer.

TEST A - `test_halt_flattens_and_blocks_reentry` (the T12 guardrail test). Trip at N=40, leaving ~59 ticks of runway for NT's retry timer. Assert:
  (a) the index of `FSM_TRANSITION -> InPosition` is LESS than the index of HALT_LATCHED. Without this the test is vacuous - which is exactly the condition tests/integration/test_gate_backtest.py is in, since that run is in blackout from tick one and never holds a position.
  (b) HALT_TRIP, HALT_LATCHED, FLATTEN_START, a closing FILL, FLATTEN_COMPLETE {flat: true, all counts 0}, HALT_ACK {flat: true}, in that index order.
  (c) ZERO entries whose event is in {ORDER_SUBMIT, GREEK_PASSED} and zero FSM_TRANSITION to PendingEntry at any index greater than HALT_LATCHED.

TEST B - `test_halt_never_claims_flat_it_did_not_verify` (the failure-injection test). Trip at N=99, the LAST tick. NT's retry timer runs on the engine clock and the backtest stops advancing time once data is exhausted, so `_check_market_exit` never fires and `post_market_exit` never runs. The initial cancels and closes still go out and still settle, because `engine.end()` drains the venues. Assert HALT_TRIP, HALT_LATCHED and FLATTEN_START are present; `FLATTEN_COMPLETE` with `flat: true` is ABSENT; HALT_ACK is absent or carries `flat: false` with `timed_out: true`; and zero ORDER_SUBMIT after HALT_LATCHED. This is the only test in the whole set that asserts a reassuring record does NOT appear, and it is deterministic because it depends only on the fixture's own tick count.

TEST C - `test_position_stays_open_without_a_halt` (the anti-vacuity control). Same profile, no trip writer. Assert no closing FILL after the entry and that the last FSM_TRANSITION is to InPosition. It exists purely to go red the day something else starts closing the book at end of run - notably when H9's manage_stop lands - at which point Test A would be passing for the wrong reason and nobody would otherwise notice.

CI: change the 'Backtest integration smoke' step from the single file `tests/integration/test_backtest_smoke.py` to `uv run pytest tests/integration/ -v`. Expect this to surface latency in CI and possibly other currently-unrun failures; that is information, not a reason to scope the step back down.

risk.md: apply EDIT 2 from the risk_md_correction field - the final row naming the shipped mechanism and `tests/integration/test_halt_backtest.py`, plus the replacement 'What this guarantees' and 'Still missing' paragraphs.

**Tests.** The three tests above ARE the deliverable. Reverts, each watched red on its own in the linux/amd64 container per hard rule 2:
- Test A(c) RED BY: drop the `if self._halted: return` guard at the top of `on_quote_tick`. The FSM returns to Flat on the exit fill (base.py:187-191) and `_context_from_quote_tick` returns a context on every FLAT tick in `backtest_plumbing` mode, so an ORDER_SUBMIT appears after the halt index. The test is red in both directions, which is what makes it a check.
- Test A(b) RED BY: revert `flatten_positions` to `self.cancel_all_orders()` - the run raises the verified TypeError out of the synchronous msgbus handler.
- Test A(b) RED BY (independently): add `self.shutdown_system(...)` to `HaltActor._trip`. FORCE_STOP breaks the run loop before settlement, so the closing FILL and FLATTEN_COMPLETE never appear. Watch this one specifically: it is the flaw that sank the flatten-and-stop design.
- Test B RED BY: move the FLATTEN_COMPLETE record from `post_market_exit` into `on_market_exit`, or emit it right after calling `market_exit()`. Both look like perfectly reasonable places to journal 'we flattened', and both make the system claim flat it never verified.
- Test C RED BY: nothing today. Its docstring must say that plainly - it is a tripwire for a future change, not a guardrail test, and counting it as coverage would be dishonest.
- The CI change RED BY: revert the step to the single file and observe that all three tests above stop running while CI stays green. That observation belongs in the commit message.

**Risk.** Test A and Test B both bypass `run_backtest`, so neither carries the NODE_START/NODE_STOP records that `run_backtest` emits - assert only on strategy- and actor-level events. Test B's timing depends on the SPY fixture being 100 ticks; it is derived from the catalog bounds, but whoever next shortens that fixture must re-read this test. And none of this can be run on the development machine: nautilus-trader publishes no macOS x86_64 wheel, so every revert-to-red must happen in the linux/amd64 container from docs/testing.md:55-67.

### H9 - manage_stop in the paper and live profiles only, as its own commit  [not started]

**Why.** Today Ctrl-C or SIGTERM on a paper node disconnects with positions open and writes a WARNING nobody reads - NT already routes all three signals to `TradingNode.stop()` (system/kernel.py:566-572), but `StrategyConfig.manage_stop` defaults False and `check_residuals()` only logs. That is the SECOND false-safety path, on a control an operator is far more likely to reach for than the CLI. It lands last and alone because it moves golden-run numbers.

**Files.** `src/nautilus_zerodte/node/wiring/strategy.py`, `src/nautilus_zerodte/node/factory.py`, `configs/profiles/paper_spy.yaml`, `configs/profiles/paper_btc.yaml`, `tests/unit/test_config_wiring.py`, `docs/decisions.md`

**Detail.** In `strategy_config()` (node/wiring/strategy.py:113-117), set on `base_config` from `config.halt`: `manage_stop`, `market_exit_interval_ms`, `market_exit_max_attempts`, `market_exit_reduce_only`. These are NT's own `StrategyConfig` fields and `BaseZeroDteStrategyConfig` already subclasses `StrategyConfig` (strategies/base.py:36), so this is config only - no code, no schema change. In `build_trading_node` (node/factory.py:72-80), pass `timeout_post_stop=config.halt.timeout_post_stop_secs` to `TradingNodeConfig` (inherited from `NautilusKernelConfig`). Not on `BacktestEngineConfig` - there is no post-stop await in the backtest path.

Add `manage_stop: true` to the halt block in configs/profiles/paper_spy.yaml and paper_btc.yaml. It goes in the PROFILES, NOT in configs/base.yaml, for two verified reasons that belong in the commit message: (1) with manage_stop True, `Actor.stop` is deferred to `_finalize_market_exit` (strategy.pyx:1863-1873), which cannot run once backtest data is exhausted, so STRATEGY_STOP would silently disappear from every backtest journal - and tests/integration/test_backtest_smoke.py asserts STRATEGY_STOP is present; (2) every backtest would market-exit at end of run, moving golden numbers, which disables the golden-diff layer for exactly the commit that most needs review.

Add decision D10 recording the split and its reversal condition (NT changes `BacktestEngine.end()` so a stop-time market exit can complete, at which point manage_stop can move to base.yaml and backtests get end-of-run flattening).

The H4 validator already guarantees `market_exit_interval_ms * market_exit_max_attempts / 1000 < timeout_post_stop_secs`, which is the constraint that actually matters here: a slow venue exit must finish before the kernel disconnects the exec clients.

**Tests.** 1. `test_paper_profile_sets_manage_stop`: load configs/profiles/paper_spy.yaml, build the strategy configs, assert `manage_stop is True` and that the three market_exit knobs match the halt block. RED BY: revert the wiring lines.
2. `test_backtest_profile_does_not_set_manage_stop`: load each backtest profile, assert `manage_stop is False`. RED BY: move manage_stop into configs/base.yaml - this test goes red immediately, and in the container tests/integration/test_backtest_smoke.py's STRATEGY_STOP assertion goes red too. Two independent checks on the same mistake.
3. `test_trading_node_config_carries_timeout_post_stop`: assert the built TradingNodeConfig has `timeout_post_stop == 20.0`. RED BY: drop the factory line - the config falls back to NT's 10.0s default, which the H4 validator would then have been guarding against a number that is no longer being used.
4. Manual, and it must actually be done rather than assumed: run the paper node in the container, Ctrl-C mid-position, and confirm from the journal that FLATTEN_START and FLATTEN_COMPLETE appear before STRATEGY_STOP. Both paper profiles currently set `dry_run: true` and the dry-run branch at cli/main.py:101-106 returns before `node.build()`, so NOBODY has ever run this live lifecycle - this work is the first thing to exercise it, and docs/testing.md definition-of-done item 1 ('verified in a running node or a real backtest run, not from reading the diff') is not satisfied without it.

**Risk.** This is the only task that changes behaviour on a path nobody has ever run. Also note CLAUDE.md hard rule 5 requires three independent opt-ins for live trading including an explicit --live flag, and no such flag exists in the CLI - out of scope here, but it sits directly next to this change and should be filed.

## Deliberately deferred, with reasons

- shutdown_after_flat - firing `Component.shutdown_system` once every ack reports flat. Safe to defer: the halted node is still up, still latched, still refusing intake, and a human is already at the keyboard. Doing it early is the one outcome strictly worse than staying up (an open position with no strategy watching it), and in backtest it is verifiably fatal to the flatten itself. The config knob ships in phase 1 defaulted false with a test asserting shutdown does NOT fire on trip; only the wiring is deferred.
- RiskEngine.set_trading_state(HALTED) after flat is confirmed, via a msgbus endpoint registered in node/. Safe to defer: while the strategy latch holds and the book is flat there is nothing for it to protect. It only matters against a strategy bug that submits without running the gate pipeline. It also drags in a new module and an endpoint registered over an engine internal, which is the largest T1 argument in the piece and deserves its own decision entry and its own test (an order denied with reason "TradingState.HALTED").
- TradingState.REDUCING at trip time. Not deferred - REJECTED. Verified directional-only and it never reads reduce_only, so on the fresh legs 0DTE opens it blocks nothing. Shipping it plus a TRADING_STATE_SET journal record would manufacture the appearance of an engine-level lock that does not exist, which is the same defect class as the risk.md row that started this.
- A retry policy of our own on top of NT's. Not deferred - REJECTED as a T1 violation. NT already retries market_exit_max_attempts times at market_exit_interval_ms and then gives up naming the residuals. On residuals we journal FLATTEN_COMPLETE {flat: false} at ERROR and the CLI exits 3; escalation is a human, which is what "guardrails fail closed and never auto-reset" requires.
- Extending the Test column to all ten rows of the risk.md guardrail table. Safe to defer because it is a doc-and-test audit, not a control - but note that several rows name a "Risk actor" that does not exist anywhere in src/, so doing it honestly will turn multiple rows red at once. That is worth knowing before someone starts.
- A node-level sweep of exposure no strategy owns. `market_exit` and the cache checks are all strategy_id-scoped; NT has no trader-wide flatten helper. Safe to defer only because `portfolio.is_completely_flat()` SURFACES such exposure and forces FLATTEN_COMPLETE {flat: false} at ERROR - the operator is told, the system simply cannot close it. That limit must be stated in risk.md, not implied away.
- Venue-side cancel-on-disconnect (Deribit and IB) in node/adapters. This is the only thing that helps when the process is dead or the event loop is wedged - and the kill switch shares an event loop with the thing it is killing. Deferring it is safe only in the sense that it is a different control; it must be written down in risk.md as still missing rather than silently absent.
- Multi-node and multi-account halt. One trip file per trader_id per runs dir. Two nodes trading the same account need the operator to halt both, and nothing detects or enforces that. Safe for now because exactly one paper node is planned, unsafe the moment a second one exists.
- A tail-from-offset read in the CLI ack loop. It re-reads the whole journal every 250ms, which is quadratic in journal length over a long wait. Fine at current scale; the torn-line fix (H1) is the part that is not deferrable.

## Open questions for Akash

1. `halt.poll_secs` default. 1.0 s is the trip-to-first-cancel bound in live and on a violent 0DTE move a second is a lot of gamma; 0.25 s costs four `os.stat` calls per second inside an engine timer callback. Both are defensible. This is a risk-appetite call about how much latency the operator will accept against how much I/O we put on the loop, and it is not mine to make.
2. Multi-leg unwind semantics. NT's `market_exit` closes leg by leg with reduce-only MARKET orders; the existing `submit_exit` closes the combo. For a vertical plus a perp hedge, leg-by-leg market exits carry real legging risk, traded for certainty of getting out. Do you want `on_market_exit` to attempt a combo close first with leg-by-leg as the fallback, or is leg-by-leg unconditionally the right emergency behaviour? I have designed for leg-by-leg because a kill switch should be dumb, but this is a trading decision.
3. Should `paper` REFUSE to start when `halt.enabled` is false? Defaulting the switch off means a profile that forgets one line has no kill switch and nothing complains - the default is quietly the dangerous one. Refusing to start is safer and adds an operator surface plus an override flag. I have not put the refusal in the task list; say the word and it becomes two lines in H7.
4. Retiring `FLATTEN_REQUEST` in favour of `HALT_REQUEST` is a hard-rule-8 public-API break. Keeping the old name is worse (it meant "nothing happened", so old and new journals would be indistinguishable), but I do not know whether anything outside this repo reads that event name. If something does, the migration note is not enough.
5. Where the operator's runs directory lives in production. The CLI and the node must resolve the SAME journal path or the ack times out to exit 4 while the node did in fact flatten - exit 4 for the wrong reason during a drawdown is a bad five minutes. The real fix is an absolute runs dir in the operator profiles, which cannot be committed. Is that `ZERODTE_RUNS_DIR` exported in your shell profile, or a documented `--runs-dir` flag on every command? Pick one and I will wire it.
6. Does `halt.enabled` belong in the run manifest (docs/evidence.md)? A backtest with the HaltActor absent is arguably a different system from one with it present, and reproducibility claims should say which was run.
7. CLAUDE.md hard rule 5 says DRY_RUN defaults to on, but `AppConfig.dry_run` defaults to False (config/strategy.py:86) and loader.py only reads DRY_RUN when the variable is set and non-empty. The code fails OPEN against its own documented rule, in the same nine lines H0 touches. Is the code wrong or is the rule wrong? I have deliberately not smuggled a fix into this work.
8. T3's exclusion list. The CLI needs wall clock for `--wait-secs`, and cli/main.py:34 already reads `datetime.now(UTC)`. Either T3's documented exclusion already has an unremarked hole or `cli/` belongs in it alongside `node/adapters/`. Widening a tenet quietly inside a guardrail commit is how tenets stop meaning anything, so this wants your call and its own decision entry.
9. Whether the doc-content test in H2 should eventually cover all ten guardrail rows. Doing so will turn several rows red immediately, because rows for the daily loss limit, the consecutive-loss breaker, the margin ceiling and the reconciliation halt all name a "Risk actor" that does not exist anywhere in src/. Fixing one row while the enforcement that would have caught it stays absent means the next false row gets written the same way - but turning four rows red in one commit is a scheduling decision.

## The decision entry to add as D8 when the design is accepted

**D8 - The operator kill switch is a latched trip file that flattens without stopping the node**

**Decision.** The operator emergency stop is a per-trader sentinel file at `<runs>/halt/<trader_id>.trip`, written atomically (temp file plus `os.replace`) by `nautilus-zerodte halt` and observed two ways: a `HaltActor` polling it on an engine-clock timer, and a one-shot `Path.exists()` in every strategy's `on_start`. Observation latches `self._halted` on each strategy - assigned `True` in exactly one place and `False` in exactly one place (`__init__`), forever. The latch closes intake at the OPERATIONAL gate (`trading_state_active=False`) and at both submit funnels, drops any intent sitting with the selector, and then calls NautilusTrader's `Strategy.market_exit()`. Flatness is verified in `post_market_exit` against BOTH `Cache.orders_open/orders_inflight/positions_open(strategy_id=self.id)` AND `Portfolio.is_completely_flat()`, and journalled as `FLATTEN_COMPLETE {flat: true}` or, on any residual or disagreement, `{flat: false}` at ERROR. The CLI blocks on the resulting `HALT_ACK` record and exits 0 only on a confirmed-flat acknowledgement; 3 on acknowledged-but-not-flat; 4 on silence. The trip does NOT stop the node, does NOT set `TradingState`, and does NOT retry beyond NT's own bounded `market_exit_max_attempts` loop. Resuming requires `nautilus-zerodte halt-clear` from a separate process AND a node restart; clearing the file cannot un-halt a running node because the in-process latch has no setter.

**Why.** Three transports cross the CLI/node process boundary: a file, an OS signal, or NT's Redis-backed external message bus. NT already claims SIGTERM/SIGINT/SIGABRT on the live loop (system/kernel.py:566-572), and Redis is a new hard dependency (hard rule 10) whose availability correlates with the incident it exists to end. A local file plus a bounded `stat` is the smallest thing that works. The flatten itself is entirely NT's: `market_exit()` (trading/strategy.pyx:1750-1810) already collects instruments from the cache, cancels then closes per instrument with reduce-only tagged MARKET orders, retries on an engine-clock timer until the cache is empty, gives up with named residual counts, and denies any non-reduce-only untagged order while it runs (strategy.pyx:861-863). Writing our own would violate T1, and the hand-rolled version we have is a hard TypeError against the pinned 1.229.0 (`self.cancel_all_orders()` at strategies/base.py:236 against `instrument_id` with no default at trading/strategy.pxd:162), so the session-blackout flatten has never worked either. Node shutdown is excluded from the trip because `_on_shutdown_system` sets backtest FORCE_STOP synchronously (system/kernel.py:632-634) and FORCE_STOP breaks the run loop (backtest/engine.pyx:1668) before `_process_and_settle_venues` and `_flush_accumulator_events` (engine.pyx:1750-1763) - a trip that shuts down cannot settle its own closing orders in backtest, and in live it kills the supervisor while residuals may remain. `TradingState` is excluded because HALTED denies every SubmitOrder including the flatten's own closes (risk/engine.pyx:1136-1148), and REDUCING denies only BUY-when-net-long and SELL-when-net-short without reading `reduce_only` (risk/engine.pyx:1149-1179), which blocks nothing on the fresh option legs a 0DTE structure opens. The strategy-side `on_start` check exists because `Trader._start` (trading/trader.py:254-264) starts every actor before any strategy, so an actor publish at its own `on_start` reaches zero subscribers and the first poll republish arrives after the strategy has already entered.

**Reversal condition.** Any of three observations. (1) We take a msgbus-database dependency for another reason, at which point the trip file is deleted and the CLI publishes on an external stream - `ShutdownSystem` and `TradingStateChanged` are already on NT's externally-serializable type list (serialization/base.pyx:235-275). (2) A load test shows the poll's `os.stat` in the p99 order-path latency tail, at which point the transport moves to SIGUSR1 registered with `loop.add_signal_handler` plus a pidfile. (3) NautilusTrader ships a `SetTradingState` command message and a HALTED variant that permits reduce-only orders, at which point the engine-level halt replaces the strategy latch as the primary control and the latch becomes belt-and-braces.

