from pathlib import Path

import pytest

from nautilus_zerodte.config.loader import _apply_env_overrides, _deep_merge, load_config
from nautilus_zerodte.config.schema import AppConfig
from nautilus_zerodte.models.enums import VenueAdapter


def test_load_paper_spy_profile() -> None:
    config = load_config("configs/profiles/paper_spy.yaml")
    assert config.strategy.underlying == "SPY.NYSE"
    assert config.strategy.strategy_id == "reference-001"
    assert config.strategy.strategy_class == "reference"
    assert config.venue.adapter is VenueAdapter.IB
    assert config.session.blackout_minutes_before_close == 30
    assert config.session.expiry_mode.value == "us_equity_close"
    assert config.reference.structure_selector == "ib"
    assert config.fees.model == "fixed_per_contract"
    assert config.fees.commission_per_contract == 0.65
    assert config.dry_run is True
    assert config.risk.version == "default"


def test_load_backtest_spy_fees_overlay() -> None:
    config = load_config("configs/profiles/backtest_spy.yaml")
    assert config.venue.adapter is VenueAdapter.IB
    assert config.fees.model == "fixed_per_contract"
    assert config.fees.commission_per_contract == 0.65
    assert config.reference.structure_selector == "ib"


def test_load_paper_btc_profile() -> None:
    config = load_config("configs/profiles/paper_btc.yaml")
    assert config.venue.adapter is VenueAdapter.DERIBIT
    assert config.venue.name == "DERIBIT"
    assert config.venue.base_currency == "USD"
    assert config.strategy.underlying == "BTC-PERPETUAL.DERIBIT"
    assert config.reference.option_series_id == "BTC"
    assert config.session.expiry_mode.value == "daily_utc"
    assert config.session.market_close_utc == "08:00"
    assert config.subscriptions.chain_snapshot_interval_ms == 30_000
    assert config.deribit.testnet is True
    assert config.dry_run is True
    assert config.fees.taker_fee == 0.0003
    assert config.fees.maker_fee == 0.0003


def test_load_backtest_btc_fees_overlay() -> None:
    config = load_config("configs/profiles/backtest_btc.yaml")
    assert config.fees.model == "maker_taker"
    assert config.fees.taker_fee == 0.0003


def test_layered_risk_overlay(tmp_path: Path) -> None:
    configs_root = tmp_path / "configs"
    (configs_root / "risk").mkdir(parents=True)
    (configs_root / "session").mkdir()
    (configs_root / "strategies").mkdir()
    (configs_root / "profiles").mkdir()

    (configs_root / "base.yaml").write_text("trader_id: TEST\n")
    (configs_root / "risk" / "default.yaml").write_text("risk:\n  version: default\n")
    (configs_root / "session" / "us_equity.yaml").write_text(
        "session:\n  blackout_minutes_before_close: 30\n"
    )
    (configs_root / "strategies" / "reference.yaml").write_text(
        "strategy:\n  underlying: SPY.NYSE\n"
    )
    (configs_root / "profiles" / "test.yaml").write_text("risk:\n  version: conservative\n")

    config = load_config(configs_root / "profiles" / "test.yaml")
    assert config.risk.version == "conservative"
    assert config.strategy.underlying == "SPY.NYSE"


def test_resolved_journal_path_default_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression PIN, not a guardrail.

    It passes on both the old and the new resolver by design: it exists so the bare
    default cannot drift while ZERODTE_RUNS_DIR is being added around it. The delenv is
    load-bearing - without it the suite-wide autouse fixture turns this into an assertion
    about the fixture.
    """
    monkeypatch.delenv("ZERODTE_RUNS_DIR", raising=False)
    config = AppConfig()
    assert config.resolved_journal_path() == Path("runs/latest.jsonl")


def test_resolved_journal_path_custom_relative_uses_runs_dir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ZERODTE_RUNS_DIR", raising=False)
    config = AppConfig(journal={"path": "custom/journal.jsonl"})
    base = Path("/tmp/test_runs")
    assert config.resolved_journal_path(base) == base / "custom/journal.jsonl"


def test_resolved_journal_path_strips_runs_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZERODTE_RUNS_DIR", raising=False)
    config = AppConfig(journal={"path": "runs/audit/trades.jsonl"})
    base = Path("/tmp/test_runs")
    assert config.resolved_journal_path(base) == base / "audit/trades.jsonl"


def test_resolved_journal_path_uses_env_when_no_arg(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERODTE_RUNS_DIR", "/tmp/env_runs")
    config = AppConfig()
    assert config.resolved_journal_path() == Path("/tmp/env_runs/latest.jsonl")


def test_resolved_journal_path_explicit_arg_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERODTE_RUNS_DIR", "/tmp/env_runs")
    config = AppConfig()
    base = Path("/tmp/explicit_runs")
    assert config.resolved_journal_path(base) == base / "latest.jsonl"


def test_absolute_journal_path_ignores_runs_dir_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """An absolute journal.path is returned verbatim, whatever the base would have been.

    Limit worth knowing: deleting the `is_absolute` early return does NOT turn this red,
    because `Path("/a") / Path("/b")` is already `Path("/b")`. It goes red against a
    resolver that joins by string concatenation, which is the regression it guards.
    """
    monkeypatch.setenv("ZERODTE_RUNS_DIR", "/tmp/env_runs")
    config = AppConfig(journal={"path": "/var/audit/trades.jsonl"})
    assert config.resolved_journal_path() == Path("/var/audit/trades.jsonl")
    assert config.resolved_journal_path(Path("/tmp/explicit_runs")) == Path(
        "/var/audit/trades.jsonl"
    )


def test_deep_merge_nested_dicts() -> None:
    base = {"risk": {"version": "default", "max_net_delta": 10.0}, "dry_run": False}
    overlay = {"risk": {"version": "conservative"}}
    merged = _deep_merge(base, overlay)
    assert merged["risk"]["version"] == "conservative"
    assert merged["risk"]["max_net_delta"] == 10.0
    assert merged["dry_run"] is False


def test_apply_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("IB_HOST", "10.0.0.1")
    monkeypatch.setenv("IB_PORT", "4002")
    data = _apply_env_overrides({"ib": {"host": "127.0.0.1"}})
    assert data["dry_run"] is True
    assert data["ib"]["host"] == "10.0.0.1"
    assert data["ib"]["port"] == 4002


def test_selector_enabled_multi_strategy() -> None:
    config = AppConfig(
        strategies=[
            {"strategy_id": "a", "underlying": "SPY.NYSE"},
            {"strategy_id": "b", "underlying": "QQQ.NASDAQ"},
        ]
    )
    assert config.selector_enabled() is True


def test_selector_enabled_diversification_flag() -> None:
    config = AppConfig(diversification={"enabled": True})
    assert config.selector_enabled() is True


def test_selector_disabled_single_strategy() -> None:
    config = AppConfig()
    assert config.selector_enabled() is False


def test_per_strategy_reference_override() -> None:
    from nautilus_zerodte.config.schema import resolved_option_series_id

    config = AppConfig(
        reference={"option_series_id": "GLOBAL"},
        strategies=[
            {
                "strategy_id": "a",
                "underlying": "SPY.NYSE",
                "reference": {"option_series_id": "SPY"},
            },
        ],
    )
    runtime = config.resolved_strategies()[0]
    assert (
        resolved_option_series_id(
            config,
            underlying=runtime.underlying,
            reference=runtime.reference,
        )
        == "SPY"
    )
