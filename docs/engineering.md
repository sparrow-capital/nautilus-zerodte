# Engineering baseline

The high-throughput, high-concurrency rules. These are written the way someone who has had a queue
back up in production writes them. They are not subject to the laziness ladder.

Read this before touching the order path, an actor, a queue, a reconnect path, or anything with a
latency or memory profile.

---

## 1. Concurrency model

- **Single writer per piece of state.** State is owned by exactly one actor or strategy. Everyone
  else reads a copy or subscribes to a message. No shared mutable objects across components, no
  module-level mutable globals, no cross-actor attribute access "just this once".
- **Messages are immutable.** Everything published on the bus is a frozen model. A consumer that
  needs a change publishes a new message.
- **No locks on the order path.** Wanting a lock means the ownership rule above is being violated.
  Fix the ownership, not the symptom.
- **Threads and pools only at the edges.** Process pools belong in `research/`. Adapters may use
  the loop's executor for genuinely blocking venue I/O. Nothing else may.
- **Async functions do not hide sync blocking.** An `async def` that calls a blocking library
  still blocks the loop. Blocking calls are moved to an executor or moved out of the path.

## 2. Queues, batching, and backpressure

- **Every buffer is bounded, and every bound is a config value with a documented overflow policy**
  (drop oldest, drop newest, or halt). Unbounded means the failure mode is memory exhaustion at
  the worst possible moment.
- The `SelectorActor` batching window is a queue. It gets a maximum size *and* a maximum age, both
  configured, and a stated policy for what happens when either is hit.
- **Backpressure means stop trading, not buffer harder.** Falling behind on market data is a
  reason to reject intents until caught up. Staleness is a gate input, not an afterthought:
  `max_chain_snapshot_age_secs` is the pattern, and it extends to quotes, greeks, and account
  state.
- **Bound every retry.** Reconnects and resubmits get a cap, jittered exponential backoff, and a
  terminal state that halts trading rather than looping. An unbounded retry against a venue that
  is rejecting you is how you get rate-limited out of the ability to flatten.

## 3. Latency

- **State the budget, then measure it.** Each stage from market-data callback to order submit has
  a documented p50 and p99 budget. The harness records the histogram per run; a regression above
  budget fails the load test in CI.
- **Tail latency is the number that matters.** A good mean with a bad p99 is a system that misses
  exactly the trades it most wanted, because the moments that matter are the busy ones.
- **No allocation surprises on the hot path.** Avoid per-tick dict, list, and string construction.
  Avoid f-string log messages that format even when the level is off. Avoid `Decimal` arithmetic
  in inner loops where the engine already provides fixed-precision types.
- **Measure before optimising, and only on the path that runs per tick.** Everything else is
  premature.

## 4. Correctness under failure

- **Idempotent orders.** Client order IDs are derived deterministically from
  `(strategy, intent, attempt)`. A reconnect must never be able to double-submit.
- **Crash-only recovery.** The journal plus venue reconciliation is the recovery path. Restart
  reconstructs state from those two and never from in-memory assumptions. State that exists only
  in RAM is state we are prepared to lose.
- **Reconcile, then trade.** On startup and after any disconnect, positions and open orders are
  reconciled against the venue before a single new intent passes. A mismatch **halts and journals
  the difference**; it never auto-corrects. Auto-correcting a mismatch you do not understand is
  how one bug becomes a position.
- **Partial fills and duplicate fills are normal, not exceptional.** Both have tests.
- **Clock jumps happen.** A backwards jump on a venue timestamp is a fault to journal and reject
  on, not something to average away.
- **UTC everywhere in code.** Local time exists only in reports rendered for a human. Deribit
  expiries are 08:00 UTC and that is the only representation stored.

## 5. Observability

- **The journal is a contract.** Event names, gate stages, and transition reasons are public API.
  Renaming one is a breaking change and needs a migration note.
- **Every intent is traceable end to end by `intent_id`:** proposed, gated (with the deciding gate
  and the inputs it decided on), approved or rejected, submitted, filled, attributed. If you
  cannot reconstruct why a trade happened from the journal alone, the journal is incomplete.
- **Every run journals its manifest** (config, git SHA, data range, seed, catalog hash). See
  `docs/evidence.md`.
- **Log levels mean something.** ERROR means a human must look. WARN means a guardrail fired.
  INFO is lifecycle. DEBUG is the hot path and is off in live.
- **Metrics are per-stage counters and histograms**, not free-text logs that someone greps later.

## 6. Security

- **No secrets in the repo.** `.env.example` documents names, never values. Keys come from the
  environment and are never logged or journaled, not even redacted with a visible prefix.
- **Live trading is opt-in at three independent levels:** a config profile, an explicit `--live`
  flag, and an environment variable. `DRY_RUN` defaults to on. Two of the three agreeing is not
  enough, because the common accident is a copied config plus a stale shell.
- **Testnet by default for Deribit** until the promotion checklist in `INTENTS.md` passes.
- **Venue authentication.** Deribit request signing uses HMAC over a timestamp and nonce. Treat
  the timestamp window as a replay-protection control: keep the local clock disciplined, reject
  responses outside the window, and never widen the window to "fix" a clock problem.
- **Client order IDs are deterministic but must not be guessable** if they ever touch a shared or
  logged surface. Derive them through a keyed hash rather than a plain counter.
- **Dependencies are a liability carried on the order path.** New ones need a written reason and a
  pinned version; the lockfile is checked in.
