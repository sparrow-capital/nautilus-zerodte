from __future__ import annotations

from pathlib import Path

from nautilus_trader.backtest.config import BacktestEngineConfig, BacktestRunConfig
from nautilus_trader.backtest.node import BacktestNode
from nautilus_trader.config import LoggingConfig
from nautilus_trader.live.config import TradingNodeConfig
from nautilus_trader.live.node import TradingNode
from nautilus_trader.model.identifiers import InstrumentId

from nautilus_zerodte.config.schema import AppConfig
from nautilus_zerodte.journal.service import Journal
from nautilus_zerodte.models.enums import GateStage
from nautilus_zerodte.node.adapters.registry import (
    apply_venue_client_wiring,
    build_venue_client_wiring,
    register_venue_factories,
)
from nautilus_zerodte.node.streaming import build_nt_streaming_config
from nautilus_zerodte.node.wiring.actors import actor_configs as _actor_configs
from nautilus_zerodte.node.wiring.backtest import (
    backtest_data_configs as _backtest_data_configs,
)
from nautilus_zerodte.node.wiring.backtest import (
    backtest_fee_model as _backtest_fee_model,
)
from nautilus_zerodte.node.wiring.backtest import (
    backtest_venue_config as _backtest_venue_config,
)
from nautilus_zerodte.node.wiring.backtest import (
    catalog_time_bounds as _catalog_time_bounds,
)
from nautilus_zerodte.node.wiring.strategy import (
    gate_strategy_config as _gate_strategy_config,
)
from nautilus_zerodte.node.wiring.strategy import (
    reference_strategy_config as _reference_strategy_config,
)
from nautilus_zerodte.node.wiring.strategy import (
    strategy_config as _strategy_config,
)
from nautilus_zerodte.node.wiring.strategy import (
    strategy_configs as _strategy_configs,
)


def build_backtest_node(config: AppConfig, catalog_path: Path | str) -> BacktestNode:
    """Build a BacktestNode wired with actors, strategy, and catalog data."""
    catalog = Path(catalog_path)
    instrument_id = InstrumentId.from_str(config.resolved_strategies()[0].underlying)
    start_time, end_time = _catalog_time_bounds(catalog, instrument_id)
    journal_path = config.resolved_journal_path()

    engine_config = BacktestEngineConfig(
        trader_id=config.trader_id,
        actors=_actor_configs(config),
        strategies=_strategy_configs(config, journal_path),
        logging=LoggingConfig(bypass_logging=True),
    )
    data_config = _backtest_data_configs(config, catalog, instrument_id, start_time, end_time)
    run_config = BacktestRunConfig(
        engine=engine_config,
        venues=[_backtest_venue_config(config)],
        data=data_config,
    )
    return BacktestNode(configs=[run_config])


def build_trading_node(config: AppConfig) -> TradingNode:
    """Build a TradingNode with actors, strategy, and venue adapter wiring."""
    journal_path = config.resolved_journal_path()
    streaming = (
        build_nt_streaming_config(config.streaming) if config.streaming.enabled else None
    )
    node_config = TradingNodeConfig(
        trader_id=config.trader_id,
        logging=LoggingConfig(log_level="ERROR"),
        actors=_actor_configs(config),
        strategies=_strategy_configs(config, journal_path),
        streaming=streaming,
    )

    wiring = build_venue_client_wiring(config, dry_run=config.dry_run)
    node_config = apply_venue_client_wiring(node_config, wiring)

    node = TradingNode(config=node_config)
    register_venue_factories(node, wiring)

    return node


def run_backtest(config: AppConfig, catalog_path: Path | str) -> Journal:
    """Run backtest with node lifecycle journal entries."""
    journal_path = config.resolved_journal_path()
    journal = Journal(journal_path)
    journal.record(
        GateStage.LIFECYCLE,
        payload={
            "event": "NODE_START",
            "node": "BacktestNode",
            "trader_id": config.trader_id,
            "risk_policy_version": config.risk.version,
            "venue_adapter": config.venue.adapter.value,
        },
    )
    node = build_backtest_node(config, catalog_path)
    try:
        node.run()
    finally:
        journal.record(
            GateStage.LIFECYCLE,
            payload={"event": "NODE_STOP", "node": "BacktestNode"},
        )
    return journal


# Backward-compatible aliases for tests and internal callers.
__all__ = [
    "build_backtest_node",
    "build_trading_node",
    "run_backtest",
    "_actor_configs",
    "_backtest_data_configs",
    "_backtest_fee_model",
    "_backtest_venue_config",
    "_catalog_time_bounds",
    "_gate_strategy_config",
    "_reference_strategy_config",
    "_strategy_config",
    "_strategy_configs",
]
