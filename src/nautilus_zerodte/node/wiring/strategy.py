from __future__ import annotations

from pathlib import Path

from nautilus_trader.config import ImportableStrategyConfig

from nautilus_zerodte.config.schema import (
    AppConfig,
    ReferenceStrategyConfig,
    StrategyRuntimeConfig,
    resolved_option_expiry_time,
    resolved_option_multiplier,
    resolved_option_series_id,
    resolved_option_venue,
    resolved_settlement_currency,
)

_STRATEGY_PATHS: dict[str, tuple[str, str]] = {
    "skeleton": (
        "nautilus_zerodte.strategies.skeleton:SkeletonZeroDteStrategy",
        "nautilus_zerodte.strategies.skeleton:SkeletonZeroDteStrategyConfig",
    ),
    "gated_skeleton": (
        "nautilus_zerodte.strategies.gated_skeleton:GatedSkeletonStrategy",
        "nautilus_zerodte.strategies.gated_skeleton:GatedSkeletonStrategyConfig",
    ),
    "reference": (
        "nautilus_zerodte.strategies.reference:ReferenceZeroDteStrategy",
        "nautilus_zerodte.strategies.reference:ReferenceZeroDteStrategyConfig",
    ),
}


def gate_strategy_config(
    config: AppConfig,
    runtime: StrategyRuntimeConfig | None = None,
) -> dict:
    runtime = runtime or config.strategy
    return {
        "min_edge_after_cost_bps": (
            runtime.min_edge_after_cost_bps
            if runtime.min_edge_after_cost_bps is not None
            else config.gates.min_edge_after_cost_bps
        ),
        "min_liquidity_score": (
            runtime.min_liquidity_score
            if runtime.min_liquidity_score is not None
            else config.gates.min_liquidity_score
        ),
        "blocked_regimes": tuple(
            runtime.blocked_regimes
            if runtime.blocked_regimes is not None
            else config.regime.blocked_regimes
        ),
        "require_chain_snapshot": config.operational.require_chain_snapshot,
        "max_underlying_quote_age_secs": config.operational.max_underlying_quote_age_secs,
        "risk_policy": config.risk.model_dump(mode="json"),
    }


def reference_strategy_config(
    config: AppConfig,
    reference: ReferenceStrategyConfig,
    runtime: StrategyRuntimeConfig | None = None,
) -> dict:
    runtime = runtime or config.strategy
    return {
        **gate_strategy_config(config, runtime),
        "dry_run": config.dry_run,
        "venue_adapter": config.venue.adapter.value,
        "fee_schedule": config.fees.model_dump(mode="json"),
        "max_chain_snapshot_age_secs": config.operational.max_chain_snapshot_age_secs,
        "chain_snapshot_interval_ms": config.subscriptions.chain_snapshot_interval_ms,
        "backtest_plumbing": reference.backtest_plumbing,
        "structure_selector": reference.structure_selector,
        "option_series_id": resolved_option_series_id(
            config, underlying=runtime.underlying, reference=reference
        ),
        "option_series_expiry": reference.option_series_expiry,
        "option_series_expiry_time_utc": resolved_option_expiry_time(config, reference),
        "option_venue": resolved_option_venue(config, reference),
        "option_multiplier": resolved_option_multiplier(config, reference),
        "settlement_currency": resolved_settlement_currency(config, reference),
        "strike_width": reference.strike_width,
        "order_qty": reference.order_qty,
        "take_profit_pct": reference.take_profit_pct,
        "stop_loss_pct": reference.stop_loss_pct,
        "hedge_perp_instrument": reference.hedge_perp_instrument,
        "hedge_delta_band": reference.hedge_delta_band,
    }


def strategy_config(
    config: AppConfig,
    journal_path: Path,
    runtime: StrategyRuntimeConfig | None = None,
) -> ImportableStrategyConfig:
    runtime = runtime or config.strategy
    strategy_class = runtime.strategy_class
    resolved_class = strategy_class if strategy_class in _STRATEGY_PATHS else "gated_skeleton"
    paths = _STRATEGY_PATHS[resolved_class]
    reference = runtime.reference or config.reference
    base_config: dict = {
        "strategy_id": runtime.strategy_id,
        "journal_path": str(journal_path),
        "underlying": runtime.underlying,
    }
    if resolved_class == "gated_skeleton":
        base_config.update(gate_strategy_config(config, runtime))
    elif resolved_class == "reference":
        base_config["selector_enabled"] = config.selector_enabled()
        base_config.update(reference_strategy_config(config, reference, runtime))
    return ImportableStrategyConfig(
        strategy_path=paths[0],
        config_path=paths[1],
        config=base_config,
    )


def strategy_configs(config: AppConfig, journal_path: Path) -> list[ImportableStrategyConfig]:
    runtimes = config.resolved_strategies()
    return [strategy_config(config, journal_path, runtime) for runtime in runtimes]
