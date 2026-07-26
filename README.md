# nautilus-zerodte

Greek-aware **0DTE options** trading as a thin extension on
[NautilusTrader](https://nautilustrader.io/) — same strategies for backtest and live.

**What this is:** layered trade gates (edge, liquidity, regime, session, greeks),
strategy FSM, venue adapters (Deribit primary, Interactive Brokers secondary),
and a JSONL journal for end-to-end audit.

**What this is not:** a matching engine, custom greek book, or parallel data pipeline.
NautilusTrader owns the event loop, subscriptions, greeks, orders, and catalog replay.

**Default venue:** Deribit crypto 0DTE (`configs/profiles/paper_btc.yaml`).
Equity 0DTE via IB is the secondary profile (`paper_spy.yaml`).

## Install

```bash
make setup
```

Requires [uv](https://docs.astral.sh/uv/) and Python 3.14+.

Verify the engine and package are available:

```bash
uv run python -c "import nautilus_trader; import nautilus_zerodte; print('ok')"
```

## Quick start

```bash
# Backtest (SPY catalog fixture)
uv run nautilus-zerodte backtest \
  --config configs/profiles/backtest_reference.yaml \
  --catalog tests/fixtures/catalog

# Backtest (Deribit BTC 0DTE fixture)
uv run nautilus-zerodte backtest \
  --config configs/profiles/backtest_btc.yaml \
  --catalog tests/fixtures/catalog_deribit

# Paper node (dry-run — no live orders)
uv run nautilus-zerodte paper \
  --config configs/profiles/paper_btc.yaml \
  --dry-run

# Inspect journal
uv run nautilus-zerodte journal summary --path runs/latest.jsonl
```

## What's here

| Path | Purpose |
| --- | --- |
| `src/nautilus_zerodte/gates/` | Pre-trade gate evaluation (edge → greek) |
| `src/nautilus_zerodte/actors/` | Session blackout, regime tags |
| `src/nautilus_zerodte/strategies/` | 0DTE FSM, reference strategy, venue spread selectors |
| `src/nautilus_zerodte/node/adapters/` | Deribit / IB venue wiring |
| `src/nautilus_zerodte/journal/` | JSONL audit trail |
| `configs/profiles/` | Paper and backtest profiles per venue |
| `docs/design/` | Architecture diagrams and NT capability mapping |

## Environment overrides (runtime contract)

Config is primarily YAML-layered via `configs/`, with a small set of **environment
variable overrides** applied in `src/nautilus_zerodte/config/loader.py`:

- **IB connection**
  - `IB_HOST`
  - `IB_PORT`
  - `IB_CLIENT_ID`
- **Deribit**
  - `DERIBIT_TESTNET` (set `1/true/yes` to use testnet)
  - `DERIBIT_API_KEY` / `DERIBIT_API_SECRET` (default env var names)
  - `DERIBIT_TESTNET_API_KEY` / `DERIBIT_TESTNET_API_SECRET` (fallback when `DERIBIT_TESTNET=1`)
- **Operational**
  - `DRY_RUN` (set `1/true/yes` to force dry-run mode)

For a higher-level overview of wiring and the strategy/selector flow, see
`docs/architecture.md`.

## Author

Akash Mahalik (<akashmahalik@gmail.com>)
