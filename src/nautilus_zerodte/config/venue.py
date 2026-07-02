from __future__ import annotations

from pydantic import BaseModel, Field

from nautilus_zerodte.models.enums import SessionExpiryMode, VenueAdapter


class VenueConfig(BaseModel):
    name: str = "NYSE"
    adapter: VenueAdapter = VenueAdapter.IB
    base_currency: str = "USD"
    account_type: str = "MARGIN"


class DeribitConfig(BaseModel):
    api_key_env: str = "DERIBIT_API_KEY"
    api_secret_env: str = "DERIBIT_API_SECRET"
    testnet: bool = False


class SessionConfig(BaseModel):
    blackout_minutes_before_close: int = 30
    market_close_utc: str = "21:00"
    expiry_mode: SessionExpiryMode = SessionExpiryMode.US_EQUITY_CLOSE


class RegimeConfig(BaseModel):
    trend_move_pct: float = 0.005
    chop_range_pct: float = 0.002
    pin_strike_proximity_pct: float = 0.001
    blocked_regimes: list[str] = Field(default_factory=lambda: ["PIN_RISK"])


class GateThresholdsConfig(BaseModel):
    min_edge_after_cost_bps: float = 5.0
    min_liquidity_score: float = 0.5


class FeeScheduleConfig(BaseModel):
    """Venue fee schedule — single source for edge gate and BacktestVenueConfig FeeModel."""

    model: str = "maker_taker"
    maker_fee: float = 0.0003
    taker_fee: float = 0.0003
    entry_liquidity: str = "taker"
    commission_per_contract: float = 0.65
    contracts_per_spread: int = 2
    expected_slippage_bps: float = 0.0


class OperationalConfig(BaseModel):
    max_underlying_quote_age_secs: float = 30.0
    max_chain_snapshot_age_secs: float = 90.0
    require_chain_snapshot: bool = True


class InteractiveBrokersConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 1


class StreamCaptureConfig(BaseModel):
    """Operator path for NT StreamingFeatherWriter — off by default."""

    enabled: bool = False
    stream_path: str = "data/streaming/latest"
    permanent_catalog_path: str = "data/catalogs/latest"
    include_types: list[str] = Field(
        default_factory=lambda: [
            "nautilus_trader.model.data:QuoteTick",
            "nautilus_trader.model.data:OptionGreeks",
        ]
    )
    rotation_mode: str = "NO_ROTATION"
    flush_interval_ms: int | None = None


class IngestionBudgetConfig(BaseModel):
    max_chain_subscriptions: int = 3
    max_snapshot_interval_ms: int = 300_000
    min_snapshot_interval_ms: int = 30_000


class IngestionConfig(BaseModel):
    """Optional subscription planner — emits plans only, no fetch logic."""

    enabled: bool = False
    budget: IngestionBudgetConfig = Field(default_factory=IngestionBudgetConfig)
