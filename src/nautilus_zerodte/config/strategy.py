from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, model_validator

from nautilus_zerodte.config.venue import (
    DeribitConfig,
    FeeScheduleConfig,
    GateThresholdsConfig,
    IngestionConfig,
    InteractiveBrokersConfig,
    OperationalConfig,
    RegimeConfig,
    SessionConfig,
    StreamCaptureConfig,
    VenueConfig,
)
from nautilus_zerodte.models.diversification import DiversificationPolicy
from nautilus_zerodte.models.halt import TRIP_DIR_NAME, trip_path
from nautilus_zerodte.models.risk import RiskPolicy


class JournalConfig(BaseModel):
    path: str = "runs/latest.jsonl"


class HaltConfig(BaseModel):
    """Operator kill-switch knobs.

    A node-level operator control is not venue knowledge, so this lives here next to
    JournalConfig and not in venue.py (hard rule 1).

    The ranges are enforced rather than only documented. The failure they prevent is an operator
    typo in a profile nobody reads again until the night it matters, and a comment does not
    prevent it.
    """

    model_config = ConfigDict(frozen=True)

    # Off in base.yaml, true only in the paper and live profiles. Whether `paper` should REFUSE
    # to start when this is false is open question 3 in docs/killswitch_plan.md.
    enabled: bool = False

    # THIS is the trip-to-first-cancel bound: the worst case between the operator writing the
    # trip file and the first cancel leaving. It does not affect the startup case, where each
    # strategy checks the file itself before subscribing to any data.
    poll_secs: float = Field(default=1.0, ge=0.25, le=5.0)

    # Roughly 3x the exit budget below, so a healthy exit acknowledges well before this fires.
    ack_timeout_secs: float = Field(default=30.0, ge=5.0, le=120.0)

    # NautilusTrader's own market_exit retry loop, passed through rather than reimplemented (T1).
    market_exit_interval_ms: int = Field(default=100, ge=50, le=500)
    # 60 x 100ms is a 6.0s budget. NT's own default of 100 gives exactly 10.0s, which ties with
    # its default timeout_post_stop of 10.0s - the flatten and the exec-client disconnect racing
    # each other. The validator below refuses that tie instead of leaving it to chance.
    market_exit_max_attempts: int = Field(default=60, ge=1, le=1000)
    # False ONLY for a venue that rejects reduce_only on options.
    market_exit_reduce_only: bool = True

    timeout_post_stop_secs: float = Field(default=20.0, ge=15.0, le=60.0)

    # PHASE 2, ships false. A trip that shuts the node down cannot settle its own closing orders
    # in backtest: _on_shutdown_system sets FORCE_STOP synchronously (kernel.py:632-634) and
    # FORCE_STOP breaks the run loop (engine.pyx:1668) before settlement.
    shutdown_after_flat: bool = False

    @model_validator(mode="after")
    def _exit_budget_fits_inside_post_stop(self) -> HaltConfig:
        budget_secs = self.market_exit_interval_ms * self.market_exit_max_attempts / 1000
        if budget_secs >= self.timeout_post_stop_secs:
            raise ValueError(
                f"halt: market exit budget {budget_secs}s (market_exit_interval_ms="
                f"{self.market_exit_interval_ms} x market_exit_max_attempts="
                f"{self.market_exit_max_attempts}) must be strictly less than "
                f"timeout_post_stop_secs={self.timeout_post_stop_secs}, or the execution "
                f"clients can disconnect while the flatten is still retrying."
            )
        return self


class ReferenceStrategyConfig(BaseModel):
    backtest_plumbing: bool = False
    structure_selector: str = "auto"
    option_series_id: str | None = None
    option_series_expiry: str | None = None
    option_series_expiry_time_utc: str | None = None
    option_venue: str | None = None
    option_multiplier: float | None = None
    settlement_currency: str | None = None
    strike_width: int = 5
    order_qty: float = 1.0
    take_profit_pct: float = 0.25
    stop_loss_pct: float = 0.50
    hedge_perp_instrument: str | None = None
    hedge_delta_band: float = 0.30


class StrategyRuntimeConfig(BaseModel):
    strategy_id: str = "skeleton-001"
    strategy_class: str = "skeleton"
    underlying: str = "SPY.NYSE"
    min_edge_after_cost_bps: float | None = None
    min_liquidity_score: float | None = None
    blocked_regimes: list[str] | None = None
    reference: ReferenceStrategyConfig | None = None


class DiversificationConfig(BaseModel):
    enabled: bool = False
    top_n: int = 3
    max_per_instrument: int = 1
    max_per_strategy: float = 0.5
    max_gross_risk_pct: float = 1.0
    batch_interval_ms: int = 100

    def to_policy(self) -> DiversificationPolicy:
        return DiversificationPolicy(
            top_n=self.top_n,
            max_per_instrument=self.max_per_instrument,
            max_per_strategy=self.max_per_strategy,
            max_gross_risk_pct=self.max_gross_risk_pct,
        )


class ApprovalConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    human_notional_threshold: float = 10_000.0
    human_edge_bps_threshold: float = 50.0


class SubscriptionConfig(BaseModel):
    chain_snapshot_interval_ms: int = 60_000


def _resolve_under_runs(path_str: str, runs_dir: Path | None) -> Path:
    """Resolve a run-artifact path against the runs directory.

    Base precedence is explicit argument, then ZERODTE_RUNS_DIR, then "runs", so with the
    variable unset the result is what it has always been.

    The environment read lives here and not in `config/loader.py:_apply_env_overrides`
    because a directly constructed `AppConfig()` never passes through the loader, and both
    the test suite and library callers construct one that way. This function is the single
    chokepoint every production caller of `resolved_journal_path` already funnels through,
    so one guard here beats one guard per caller.
    """
    path = Path(path_str)
    if path.is_absolute():
        return path
    base = runs_dir or Path(os.environ.get("ZERODTE_RUNS_DIR") or "runs")
    relative = path
    if path.parts and path.parts[0] == "runs":
        relative = Path(*path.parts[1:]) if len(path.parts) > 1 else Path("latest.jsonl")
    return base / relative


class AppConfig(BaseModel):
    """Merged runtime configuration for backtest and live nodes."""

    trader_id: str = "TRADER-001"
    # `dry_run` means exactly one thing: strategies journal the intent and do NOT submit an
    # order. It does not stop the node running. `build_only` is the separate concern of
    # constructing the node and exiting without running it. They used to be the same flag,
    # which is how CLAUDE.md hard rule 5 came to say something incoherent - see D10.
    dry_run: bool = False
    build_only: bool = False
    # Profile-level opt-in to real order submission: one of the three independent opt-ins
    # live execution requires. Never default this to true in a committed profile.
    allow_live: bool = False
    venue: VenueConfig = Field(default_factory=VenueConfig)
    journal: JournalConfig = Field(default_factory=JournalConfig)
    halt: HaltConfig = Field(default_factory=HaltConfig)
    risk: RiskPolicy = Field(default_factory=RiskPolicy)
    session: SessionConfig = Field(default_factory=SessionConfig)
    regime: RegimeConfig = Field(default_factory=RegimeConfig)
    gates: GateThresholdsConfig = Field(default_factory=GateThresholdsConfig)
    fees: FeeScheduleConfig = Field(default_factory=FeeScheduleConfig)
    operational: OperationalConfig = Field(default_factory=OperationalConfig)
    strategy: StrategyRuntimeConfig = Field(default_factory=StrategyRuntimeConfig)
    strategies: list[StrategyRuntimeConfig] | None = None
    diversification: DiversificationConfig = Field(default_factory=DiversificationConfig)
    approval: ApprovalConfig = Field(default_factory=ApprovalConfig)
    reference: ReferenceStrategyConfig = Field(default_factory=ReferenceStrategyConfig)
    subscriptions: SubscriptionConfig = Field(default_factory=SubscriptionConfig)
    ib: InteractiveBrokersConfig = Field(default_factory=InteractiveBrokersConfig)
    deribit: DeribitConfig = Field(default_factory=DeribitConfig)
    streaming: StreamCaptureConfig = Field(default_factory=StreamCaptureConfig)
    ingestion: IngestionConfig = Field(default_factory=IngestionConfig)

    def resolved_journal_path(self, runs_dir: Path | None = None) -> Path:
        return _resolve_under_runs(self.journal.path, runs_dir)

    def resolved_halt_trip_path(self, runs_dir: Path | None = None) -> Path:
        """`<runs>/halt/<trader_id>.trip`, resolved through the same seam as the journal.

        Sharing `_resolve_under_runs` means the trip file inherits the ZERODTE_RUNS_DIR override
        (D9) and therefore the autouse tripwire in tests/conftest.py. That matters more here
        than it does for the journal: a stray trip file written by pytest into the operator's
        real runs/halt/ would kill their next live session at startup.
        """
        base = _resolve_under_runs(TRIP_DIR_NAME, runs_dir).parent
        return trip_path(base, self.trader_id)

    def resolved_strategies(self) -> list[StrategyRuntimeConfig]:
        if self.strategies:
            return self.strategies
        return [self.strategy]

    def selector_enabled(self) -> bool:
        strategies = self.resolved_strategies()
        return self.diversification.enabled or len(strategies) > 1
