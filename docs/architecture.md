# Architecture (runtime contracts)

This document is intentionally short and **contract-focused**: it describes how
`nautilus-zerodte` wires NautilusTrader components together at runtime, and the
message flows that must remain stable.

## Config layering

- **Primary source**: YAML in `configs/` (base → risk → strategy → profile).
- **Overlays**: fee + session overlays are selected based on `venue.adapter`.
- **Env overrides**: a small set of environment variables is applied last in
  `src/nautilus_zerodte/config/loader.py` (see `README.md`).

## Node wiring

- The trading node is assembled from config in `src/nautilus_zerodte/node/factory.py`.
- **Strategy class resolution** is based on stable import paths; keep those
  contracts stable when refactoring strategies/actors.
- Venue clients are wired in `src/nautilus_zerodte/node/adapters/` (Deribit / IB).

## Strategy FSM + gate pipeline (high level)

Each strategy owns a small FSM (flat → evaluating → pending entry → in position).
For entry signals:

- Build a `ChainEvaluationContext` from either:
  - Option chain snapshots (live), or
  - Quote ticks (backtest plumbing mode in the reference strategy).
- Build a `TradeIntent`.
- Run gates in sequence:
  - **pre-greek** gates (regime/session/edge/liquidity/etc)
  - **risk/greek** gate (portfolio + shocks)
- If `--dry-run` / `DRY_RUN=1` is enabled, intent is journaled but no orders are submitted.

Journal event strings and transition reasons are treated as stable observability
contracts.

## SelectorActor flow (diversification + approval)

When diversification is enabled (or multiple strategies are configured), the
system routes candidate `TradeIntent`s through the `SelectorActor`:

- Strategies publish intents to `TRADE_INTENT_TOPIC`.
- `SelectorActor` buffers briefly (batching) and applies:
  - diversification (`top_n`, caps per instrument/strategy)
  - approval routing (human vs automation)
- The actor publishes:
  - rejections to `TRADE_INTENT_REJECTED_TOPIC`
  - approvals to `TRADE_INTENT_APPROVED_TOPIC`

Strategies subscribe to those topics and either submit orders (approved) or
reset to `FLAT` (rejected).

