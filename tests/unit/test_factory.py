from __future__ import annotations

from pathlib import Path

import pytest
from nautilus_trader.model.data import QuoteTick
from nautilus_trader.model.identifiers import InstrumentId

from nautilus_zerodte.config.schema import AppConfig
from nautilus_zerodte.node.factory import (
    _actor_configs,
    _backtest_data_configs,
    _backtest_fee_model,
    _backtest_venue_config,
    _strategy_config,
)


def test_unknown_strategy_class_gets_gated_skeleton_config() -> None:
    config = AppConfig(
        strategy={
            "strategy_id": "s1",
            "strategy_class": "nonexistent",
            "underlying": "SPY.NYSE",
        },
        gates={"min_edge_after_cost_bps": 7.5, "min_liquidity_score": 0.6},
        regime={"blocked_regimes": ["TREND"]},
        operational={"require_chain_snapshot": False},
        risk={"version": "test-policy", "max_net_delta": 42.0},
    )
    importable = _strategy_config(config, Path("/tmp/journal.jsonl"))

    assert "gated_skeleton" in importable.strategy_path
    assert importable.config["min_edge_after_cost_bps"] == 7.5
    assert importable.config["min_liquidity_score"] == 0.6
    assert importable.config["blocked_regimes"] == ("TREND",)
    assert importable.config["require_chain_snapshot"] is False
    assert importable.config["risk_policy"]["version"] == "test-policy"
    assert importable.config["risk_policy"]["max_net_delta"] == 42.0


def test_reference_strategy_config_wiring() -> None:
    config = AppConfig(
        strategy={
            "strategy_id": "ref-1",
            "strategy_class": "reference",
            "underlying": "SPY.NYSE",
        },
        reference={"backtest_plumbing": True, "order_qty": 2},
        dry_run=True,
    )
    importable = _strategy_config(config, Path("/tmp/journal.jsonl"))

    assert "reference" in importable.strategy_path
    assert importable.config["backtest_plumbing"] is True
    assert importable.config["order_qty"] == 2
    assert importable.config["dry_run"] is True
    assert importable.config["fee_schedule"]["taker_fee"] == 0.0003
    assert importable.config["option_series_id"] == "SPY"
    assert importable.config["option_venue"] == "NYSE"
    assert importable.config["option_multiplier"] == 100.0


def test_deribit_backtest_fee_model_wired() -> None:
    config = AppConfig(venue={"adapter": "DERIBIT", "name": "DERIBIT", "base_currency": "USD"})
    fee_model = _backtest_fee_model(config)
    assert fee_model is not None
    assert "MakerTakerFeeModel" in fee_model.fee_model_path

    venue = _backtest_venue_config(config)
    assert venue.fee_model is not None


def test_ib_backtest_fixed_fee_model_wired() -> None:
    config = AppConfig(
        venue={"adapter": "IB", "name": "NYSE", "base_currency": "USD"},
        reference={"backtest_plumbing": False},
        fees={
            "model": "fixed_per_contract",
            "commission_per_contract": 0.65,
            "contracts_per_spread": 2,
        },
    )
    fee_model = _backtest_fee_model(config)
    assert fee_model is not None
    assert "FixedFeeModel" in fee_model.fee_model_path
    assert fee_model.config["commission"] == "0.65 USD"

    venue = _backtest_venue_config(config)
    assert venue.fee_model is not None


def test_selector_actor_registered_when_multi_strategy() -> None:
    config = AppConfig(
        strategies=[
            {"strategy_id": "a", "underlying": "SPY.NYSE"},
            {"strategy_id": "b", "underlying": "QQQ.NASDAQ"},
        ]
    )
    actors = _actor_configs(config)
    assert any("selector" in actor.actor_path for actor in actors)


def test_backtest_data_configs_quote_only_for_skeleton() -> None:
    catalog = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "catalog"
    if not catalog.exists():
        pytest.skip("Catalog fixture not built")
    config = AppConfig(
        strategy={"strategy_class": "skeleton", "underlying": "BTC-PERPETUAL.DERIBIT"},
        venue={"adapter": "DERIBIT", "name": "DERIBIT"},
    )
    instrument_id = InstrumentId.from_str("BTC-PERPETUAL.DERIBIT")
    configs = _backtest_data_configs(config, catalog, instrument_id, 0, 1_000_000_000)
    assert len(configs) == 1
    assert configs[0].instrument_id == instrument_id


def test_backtest_data_configs_option_chain_for_reference() -> None:
    catalog = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "catalog"
    if not catalog.exists():
        pytest.skip("Catalog fixture not built")
    config = AppConfig(
        strategy={"strategy_class": "reference", "underlying": "BTC-PERPETUAL.DERIBIT"},
        venue={"adapter": "DERIBIT", "name": "DERIBIT"},
        reference={"backtest_plumbing": False},
    )
    instrument_id = InstrumentId.from_str("BTC-PERPETUAL.DERIBIT")
    configs = _backtest_data_configs(config, catalog, instrument_id, 0, 1_000_000_000)
    assert len(configs) >= 1
    assert any("OptionGreeks" in str(cfg.data_cls) for cfg in configs)
