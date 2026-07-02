from __future__ import annotations

from nautilus_trader.config import ImportableActorConfig

from nautilus_zerodte.config.schema import AppConfig, resolved_option_series_id


def actor_configs(config: AppConfig) -> list[ImportableActorConfig]:
    primary = config.resolved_strategies()[0]
    actors = [
        ImportableActorConfig(
            actor_path="nautilus_zerodte.actors.session:SessionActor",
            config_path="nautilus_zerodte.actors.session:SessionActorConfig",
            config={
                "blackout_minutes_before_close": config.session.blackout_minutes_before_close,
                "market_close_utc": config.session.market_close_utc,
                "underlying": primary.underlying,
            },
        ),
        ImportableActorConfig(
            actor_path="nautilus_zerodte.actors.regime:RegimeActor",
            config_path="nautilus_zerodte.actors.regime:RegimeActorConfig",
            config={
                "underlying": primary.underlying,
                "trend_move_pct": config.regime.trend_move_pct,
                "chop_range_pct": config.regime.chop_range_pct,
                "pin_strike_proximity_pct": config.regime.pin_strike_proximity_pct,
            },
        ),
    ]
    if config.selector_enabled():
        journal_path = config.resolved_journal_path()
        actors.append(
            ImportableActorConfig(
                actor_path="nautilus_zerodte.actors.selector:SelectorActor",
                config_path="nautilus_zerodte.actors.selector:SelectorActorConfig",
                config={
                    "journal_path": str(journal_path),
                    "diversification": config.diversification.model_dump(mode="json"),
                    "approval": config.approval.model_dump(mode="json"),
                    "batch_interval_ms": config.diversification.batch_interval_ms,
                },
            )
        )
    if config.ingestion.enabled:
        primary = config.resolved_strategies()[0]
        reference = primary.reference or config.reference
        actors.append(
            ImportableActorConfig(
                actor_path="nautilus_zerodte.actors.ingestion:IngestionPlannerActor",
                config_path="nautilus_zerodte.actors.ingestion:IngestionPlannerActorConfig",
                config={
                    "underlying": primary.underlying,
                    "option_series_id": resolved_option_series_id(
                        config,
                        underlying=primary.underlying,
                        reference=reference,
                    ),
                    "hedge_perp_instrument": reference.hedge_perp_instrument,
                    "chain_snapshot_interval_ms": config.subscriptions.chain_snapshot_interval_ms,
                    "max_chain_subscriptions": config.ingestion.budget.max_chain_subscriptions,
                    "max_snapshot_interval_ms": config.ingestion.budget.max_snapshot_interval_ms,
                    "min_snapshot_interval_ms": config.ingestion.budget.min_snapshot_interval_ms,
                },
            )
        )
    return actors
