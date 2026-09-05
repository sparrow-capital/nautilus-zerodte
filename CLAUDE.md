# CLAUDE.md - nautilus-zerodte

A thin extension of
[NautilusTrader](https://github.com/nautechsystems/nautilus_trader).

**Goal:** back/paper testing over Deribit crypto 0DTE options that produces *actionable tuning
decisions* - "change this knob by this much, here is the evidence" - with guardrails that make
the worst case survivable. Deribit first, nothing venue-specific in the core.

**This file is auto-loaded on every turn, so it stays short.** It holds only what must be true on
every task. Everything else is routed. Read `INDEX.md` to find the one file you need; read
`INTENTS.md` before proposing new work.

---

## Prime directive

NautilusTrader owns the event loop, message bus, clock, order and position state, matching,
greeks, catalog, and venue connectivity. We own gates, the strategy FSM, cost models, the
journal, and the evaluation harness. If something is missing upstream: config it, subclass it,
contribute upstream, and only then wrap it here. **If you are writing a scheduler, a queue, or a
clock, stop.**

`.cursor/rules/ponytail.mdc` governs *how much* code you write. This file governs *what the code
must guarantee*. Where they conflict, this file wins. The laziness ladder is never a reason to
skip a tenet.

---

## The tenets (one line each; full text and enforcement in `docs/tenets.md`)

- **T1 Extend, do not fork the engine.** Every wrapper names the upstream capability it stands in
  for and what would let us delete it.
- **T2 Deterministic, and robust beyond determinism.** Same inputs, same bytes. And a conclusion
  that does not survive bootstrap resampling is not a conclusion.
- **T3 One clock.** Engine clock only. No `datetime.now()` or `time.time()` outside adapters.
- **T4 One strategy object across backtest, paper, and live.** No mode flag inside `strategies/`,
  `gates/`, or `actors/`.
- **T5 Fail closed.** Missing greeks, stale quote, unknown instrument, exception in a gate: all
  are rejections. No path where uncertainty produces an order.
- **T6 Never block the order path.** No disk, no network, no pools, no research code.
- **T7 Costs are first-class and identical everywhere,** and reconciled by regression:
  `edge_realized ~ edge_predicted` must have intercept near 0 and slope near 1.
- **T8 No look-ahead, structurally impossible.** Features exist because the engine delivered the
  data, not because we remembered to filter.
- **T9 Pessimistic execution.** Cross the spread, cap at displayed size, and **no maker fills in
  backtest without a queue model.**
- **T10 Every result is deflated by the number of trials it took to find.** Trials are registered
  across the whole program, not per sweep.
- **T11 PnL must explain.** A residual with a mean significantly different from zero blocks
  adoption. A large zero-mean residual does not.
- **T12 Guardrails are code, and every guardrail has a test that trips it.**

---

## Hard rules (violating one is a defect, not a style opinion)

1. **Venue containment.** Venue-specific knowledge lives only in `node/adapters/`, `costs/`,
   `strategies/selectors/`, and `configs/`. Nowhere else. No hardcoded symbol, tick size,
   multiplier, settlement currency, expiry hour, or fee rate in core code.
2. **Every change lands with its tests, same pass.** New behaviour gets a test; changed behaviour
   gets its old test deliberately updated; **a bug fix gets a test that fails on the unfixed
   code** - revert it, watch it go red, restore. The tests are the review.
3. **A run without its manifest is not evidence.** Config, git SHA, data range, seed, and catalog
   hash, or the result cannot be cited. See `docs/evidence.md`.
4. **Gate-disabled configs are plumbing tests, never evidence.** Any config that relaxes a gate
   to pass a fixture says so in a comment, and the harness refuses to emit a tuning report from
   one. (`backtest_btc.yaml` currently sets `min_edge_after_cost_bps: -5000.0`.)
5. **Live trading needs three independent opt-ins:** a profile, an explicit `--live` flag, and an
   environment variable. `DRY_RUN` defaults to on. Testnet until the promotion checklist passes.
6. **No secrets in the repo.** `.env.example` documents names only. Keys are never logged or
   journaled, not even partially redacted.
7. **UTC everywhere in code.** Local time exists only in reports rendered for a human.
8. **Journal event names, gate stages, and transition reasons are public API.** Renaming one is a
   breaking change.
9. **ASCII only in anything checked in.** Verify with `LC_ALL=C grep -nP '[^\x00-\x7F]' <file>`.
10. **No new dependency without a written reason next to it.**

---

## Routing

| You are about to | Read |
| --- | --- |
| Anything - find the right file | `INDEX.md` |
| Propose new work, or ask if something is in scope | `INTENTS.md` |
| Argue with or apply a tenet | `docs/tenets.md` |
| Touch the order path, actors, queues, or latency | `docs/engineering.md` |
| Run a sweep, tune a parameter, or report a result | `docs/quant/evaluation.md` |
| Touch PnL decomposition or the learning module | `docs/quant/attribution.md` |
| Touch fills, fees, slippage, or settlement | `docs/quant/execution.md` |
| Touch risk limits, shocks, margin, or kill switches | `docs/quant/risk.md` |
| Add a coin or a venue | `docs/venues.md` |
| Write or change tests | `docs/testing.md` |
| Cite a run, or wonder if a number is trustworthy | `docs/evidence.md` |
| Understand why something is the way it is | `docs/decisions.md` |
| Wire a node, actor, or config layer | `docs/architecture.md`, `docs/design/`, `docs/implementation/` |
| Learn the field rather than the codebase | `docs/faq/INDEX.md` |

---

## Commands

```bash
make setup                 # uv sync --group dev  (Python 3.14+, uv required)
make lint                  # ruff check + format check
make test                  # pytest
make backtest-btc          # Deribit BTC 0DTE over the fixture catalog

uv run nautilus-zerodte backtest --config configs/profiles/backtest_btc.yaml \
    --catalog tests/fixtures/catalog_deribit
uv run nautilus-zerodte paper --config configs/profiles/paper_btc.yaml --dry-run
uv run nautilus-zerodte journal summary --path runs/latest.jsonl
```

Config layering: `base -> risk -> strategy -> profile`, then venue-selected fee and session
overlays, then a small set of environment overrides applied last in `config/loader.py`.

```
src/nautilus_zerodte/
  gates/        pre-trade gates (edge -> liquidity -> regime -> session -> greek)
  actors/       session blackout, regime, ingestion, selector
  strategies/   0DTE FSM, reference strategy, venue structure selectors
  node/         node factory, wiring, venue adapters (Deribit, IB)
  costs/        per-venue fee and edge math
  journal/      JSONL audit trail
  learning/     post-trade PnL attribution
  research/     offline analysis over the catalog, never on the order path
  config/       YAML layering, schema, env overrides
```

---

## Style

Plain words, no hype, no emoji. "fixes", not "remediations". Comments explain why, not what.
A `ponytail:` comment marks a deliberate shortcut and names its ceiling and upgrade path.
Small diffs, deletion over addition, boring over clever - especially on the order path, where
clever is what is hard to reason about at 3am.
