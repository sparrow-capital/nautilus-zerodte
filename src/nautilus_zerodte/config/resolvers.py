from __future__ import annotations

from nautilus_zerodte.config.strategy import AppConfig, ReferenceStrategyConfig
from nautilus_zerodte.models.enums import VenueAdapter


def underlying_symbol_from_id(instrument_id: str) -> str:
    """Derive option underlying symbol from an NT instrument id string."""
    symbol = instrument_id.split(".")[0]
    if "-" in symbol:
        return symbol.split("-")[0]
    return symbol


def resolved_settlement_currency(
    config: AppConfig,
    reference: ReferenceStrategyConfig | None = None,
) -> str:
    ref = reference or config.reference
    if ref.settlement_currency:
        return ref.settlement_currency
    return config.venue.base_currency


def resolved_option_expiry_time(
    config: AppConfig,
    reference: ReferenceStrategyConfig | None = None,
) -> str:
    ref = reference or config.reference
    if ref.option_series_expiry_time_utc:
        return ref.option_series_expiry_time_utc
    return config.session.market_close_utc


def resolved_option_venue(
    config: AppConfig,
    reference: ReferenceStrategyConfig | None = None,
) -> str:
    ref = reference or config.reference
    if ref.option_venue:
        return ref.option_venue
    return config.venue.name


def resolved_option_multiplier(
    config: AppConfig,
    reference: ReferenceStrategyConfig | None = None,
) -> float:
    ref = reference or config.reference
    if ref.option_multiplier is not None:
        return ref.option_multiplier
    if config.venue.adapter is VenueAdapter.IB:
        return 100.0
    return 1.0


def resolved_option_series_id(
    config: AppConfig,
    *,
    underlying: str | None = None,
    reference: ReferenceStrategyConfig | None = None,
) -> str:
    ref = reference or config.reference
    if ref.option_series_id:
        return ref.option_series_id
    base = underlying or config.resolved_strategies()[0].underlying
    return underlying_symbol_from_id(base)
