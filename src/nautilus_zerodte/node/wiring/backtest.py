from __future__ import annotations

from pathlib import Path

from nautilus_trader.backtest.config import (
    BacktestDataConfig,
    BacktestVenueConfig,
    ImportableFeeModelConfig,
)
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.enums import InstrumentClass
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.persistence.catalog.parquet import ParquetDataCatalog

from nautilus_zerodte.config.schema import AppConfig
from nautilus_zerodte.models.enums import VenueAdapter


def catalog_time_bounds(catalog_path: Path, instrument_id: InstrumentId) -> tuple[int, int]:
    catalog = ParquetDataCatalog(str(catalog_path))
    ticks = catalog.quote_ticks(instrument_ids=[instrument_id])
    if not ticks:
        msg = f"No quote ticks for {instrument_id} in catalog at {catalog_path}"
        raise ValueError(msg)
    return ticks[0].ts_event, ticks[-1].ts_event


def backtest_data_configs(
    config: AppConfig,
    catalog_path: Path,
    instrument_id: InstrumentId,
    start_time: int,
    end_time: int,
) -> list[BacktestDataConfig]:
    """Build BacktestDataConfig entries for catalog contents."""
    catalog = ParquetDataCatalog(str(catalog_path))
    data_types = set(catalog.list_data_types())
    primary = config.resolved_strategies()[0]
    use_option_chain = (
        primary.strategy_class == "reference"
        and not config.reference.backtest_plumbing
        and "option_greeks" in data_types
        and config.venue.adapter in {VenueAdapter.DERIBIT, VenueAdapter.IB}
    )

    if not use_option_chain:
        return [
            BacktestDataConfig(
                catalog_path=str(catalog_path),
                catalog_fs_protocol="file",
                data_cls=QuoteTick,
                instrument_id=instrument_id,
                start_time=start_time,
                end_time=end_time,
            )
        ]

    quote_ids = [str(inst.id) for inst in catalog.instruments()]
    configs = [
        BacktestDataConfig(
            catalog_path=str(catalog_path),
            catalog_fs_protocol="file",
            data_cls=QuoteTick,
            instrument_ids=quote_ids,
            start_time=start_time,
            end_time=end_time,
        )
    ]
    option_ids = [
        str(inst.id)
        for inst in catalog.instruments()
        if inst.instrument_class == InstrumentClass.OPTION
    ]
    if option_ids:
        configs.append(
            BacktestDataConfig(
                catalog_path=str(catalog_path),
                catalog_fs_protocol="file",
                data_cls="nautilus_trader.model.data:OptionGreeks",
                instrument_ids=option_ids,
                start_time=start_time,
                end_time=end_time,
            )
        )
    return configs


def backtest_fee_model(config: AppConfig) -> ImportableFeeModelConfig | None:
    if config.reference.backtest_plumbing:
        return None
    if config.venue.adapter is VenueAdapter.DERIBIT:
        if config.fees.model != "maker_taker":
            return None
        return ImportableFeeModelConfig(
            fee_model_path="nautilus_trader.backtest.models.fee:MakerTakerFeeModel",
            config_path="nautilus_trader.backtest.config:MakerTakerFeeModelConfig",
            config={},
        )
    if config.venue.adapter is VenueAdapter.IB:
        if config.fees.model != "fixed_per_contract":
            return None
        currency = config.venue.base_currency
        return ImportableFeeModelConfig(
            fee_model_path="nautilus_trader.backtest.models.fee:FixedFeeModel",
            config_path="nautilus_trader.backtest.config:FixedFeeModelConfig",
            config={"commission": f"{config.fees.commission_per_contract} {currency}"},
        )
    return None


def backtest_venue_config(config: AppConfig) -> BacktestVenueConfig:
    currency = config.venue.base_currency
    fee_model = backtest_fee_model(config)
    return BacktestVenueConfig(
        name=config.venue.name,
        oms_type="HEDGING",
        account_type=config.venue.account_type,
        base_currency=currency,
        starting_balances=[f"100000 {currency}"],
        fee_model=fee_model,
    )
