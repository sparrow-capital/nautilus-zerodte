from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from nautilus_zerodte.cli.main import app
from nautilus_zerodte.journal.service import Journal
from nautilus_zerodte.models.enums import GateStage

REPO_ROOT = Path(__file__).resolve().parents[2]
PROFILE = REPO_ROOT / "configs" / "profiles" / "paper_spy.yaml"
CATALOG = REPO_ROOT / "tests" / "fixtures" / "catalog"

runner = CliRunner()


def test_backtest_command_smoke(tmp_path: Path) -> None:
    with patch("nautilus_zerodte.cli.main.run_backtest") as mock_run:
        journal_path = tmp_path / "bt.jsonl"
        mock_run.return_value = Journal(journal_path)
        result = runner.invoke(
            app,
            ["backtest", "-c", str(PROFILE), "--catalog", str(CATALOG)],
        )
        assert result.exit_code == 0, result.stdout
        assert "Backtest complete" in result.stdout
        mock_run.assert_called_once()


def test_backtest_dry_run_flag(tmp_path: Path) -> None:
    with patch("nautilus_zerodte.cli.main.run_backtest") as mock_run:
        mock_run.return_value = Journal(tmp_path / "bt.jsonl")
        result = runner.invoke(
            app,
            ["backtest", "-c", str(PROFILE), "--catalog", str(CATALOG), "--dry-run"],
        )
        assert result.exit_code == 0, result.stdout
        config = mock_run.call_args[0][0]
        assert config.dry_run is True


def test_paper_command_dry_run_smoke(tmp_path: Path) -> None:
    with patch("nautilus_zerodte.cli.main.build_trading_node") as mock_build:
        mock_build.return_value = MagicMock()
        result = runner.invoke(app, ["paper", "-c", str(PROFILE), "--dry-run"])
        assert result.exit_code == 0, result.stdout
        assert "TradingNode built" in result.stdout
        mock_build.assert_called_once()


def test_flatten_command_smoke(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "flatten",
            "-c",
            str(PROFILE),
        ],
    )
    assert result.exit_code == 0, result.stdout
    assert "Flatten request recorded" in result.stdout


def test_journal_report_command(tmp_path: Path) -> None:
    journal_path = tmp_path / "report.jsonl"
    journal = Journal(journal_path)
    journal.record(
        GateStage.EDGE,
        payload={"event": "GATE_REJECT", "breached_rules": ["min_edge"]},
    )
    result = runner.invoke(app, ["journal", "report", "-p", str(journal_path)])
    assert result.exit_code == 0, result.stdout
    assert "Gate rejection report" in result.stdout
    assert "EDGE: 1" in result.stdout
    assert "min_edge: 1" in result.stdout


def test_journal_summary_command(tmp_path: Path) -> None:
    journal_path = tmp_path / "summary.jsonl"
    journal = Journal(journal_path)
    journal.record(GateStage.LIFECYCLE, payload={"event": "NODE_START"}, strategy_id="s1")
    journal.record(GateStage.EDGE, payload={"event": "GATE_REJECT"}, strategy_id="s1")
    result = runner.invoke(app, ["journal", "summary", "-p", str(journal_path)])
    assert result.exit_code == 0, result.stdout
    assert "Total entries: 2" in result.stdout
    assert "Strategies: s1" in result.stdout
    assert "Gate rejections:" in result.stdout


def test_catalog_convert_command(tmp_path: Path) -> None:
    with patch("nautilus_zerodte.cli.main.convert_stream_catalog") as mock_convert:
        out = tmp_path / "catalog-out"
        mock_convert.return_value = out
        result = runner.invoke(
            app,
            ["catalog", "convert", "--run-id", "test-run", "--catalog-out", str(out)],
        )
        assert result.exit_code == 0, result.stdout
        assert "Converted stream" in result.stdout
        mock_convert.assert_called_once()


def test_research_catalog_command() -> None:
    with patch("nautilus_zerodte.cli.main.run_catalog_partitions") as mock_research:
        mock_research.return_value = [
            {"instrument_id": "SPY.NYSE", "quote_tick_count": 42},
        ]
        result = runner.invoke(
            app,
            ["research", "catalog", "--catalog", str(CATALOG)],
        )
        assert result.exit_code == 0, result.stdout
        assert "Partitions analyzed: 1" in result.stdout
        assert "SPY.NYSE" in result.stdout


# --- live execution gate -------------------------------------------------------------
#
# Live submission needs three independent opt-ins: the --live flag, allow_live in the
# profile, and ZERODTE_ALLOW_LIVE in the environment. Each test below removes exactly one
# and asserts the run is REFUSED, because two agreeing is not enough.

LIVE_PROFILE_UPDATE = {"allow_live": True}


def _profile_with(**update):
    """Load the committed profile and patch it, so no live-enabled profile is committed."""
    from nautilus_zerodte.config.loader import load_config

    return load_config(PROFILE).model_copy(update=update)


def test_live_refused_without_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ZERODTE_ALLOW_LIVE", raising=False)
    with patch("nautilus_zerodte.cli.main.load_config") as mock_load:
        mock_load.return_value = _profile_with(**LIVE_PROFILE_UPDATE)
        with patch("nautilus_zerodte.cli.main.build_trading_node") as mock_build:
            result = runner.invoke(app, ["paper", "-c", str(PROFILE), "--live"])
    assert result.exit_code == 2, result.stdout
    assert "REFUSING TO START" in result.output
    assert "ZERODTE_ALLOW_LIVE" in result.output
    mock_build.assert_not_called()


def test_live_refused_without_profile_allow_live(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERODTE_ALLOW_LIVE", "1")
    with patch("nautilus_zerodte.cli.main.build_trading_node") as mock_build:
        result = runner.invoke(app, ["paper", "-c", str(PROFILE), "--live"])
    assert result.exit_code == 2, result.stdout
    assert "allow_live" in result.output
    mock_build.assert_not_called()


def test_live_and_dry_run_are_mutually_exclusive() -> None:
    with patch("nautilus_zerodte.cli.main.build_trading_node") as mock_build:
        result = runner.invoke(app, ["paper", "-c", str(PROFILE), "--live", "--dry-run"])
    assert result.exit_code == 2, result.stdout
    mock_build.assert_not_called()


def test_live_granted_with_all_three_opt_ins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ZERODTE_ALLOW_LIVE", "1")
    with patch("nautilus_zerodte.cli.main.load_config") as mock_load:
        mock_load.return_value = _profile_with(**LIVE_PROFILE_UPDATE)
        with patch("nautilus_zerodte.cli.main.build_trading_node") as mock_build:
            mock_build.return_value = MagicMock()
            result = runner.invoke(app, ["paper", "-c", str(PROFILE), "--live"])
    assert result.exit_code == 0, result.stdout
    assert "MODE: LIVE" in result.output
    assert "REAL ORDERS WILL BE SUBMITTED" in result.output
    # The strategies must be told to submit.
    assert mock_build.call_args[0][0].dry_run is False


def test_default_paper_run_is_observe_and_submits_nothing() -> None:
    """No flags must never submit. This is the safe default the old code did not have."""
    with patch("nautilus_zerodte.cli.main.build_trading_node") as mock_build:
        mock_build.return_value = MagicMock()
        result = runner.invoke(app, ["paper", "-c", str(PROFILE)])
    assert result.exit_code == 0, result.stdout
    assert "MODE: OBSERVE" in result.output
    assert "NO orders are sent" in result.output
    passed_config = mock_build.call_args[0][0]
    assert passed_config.dry_run is True
    assert passed_config.build_only is False


def test_dry_run_is_build_only_and_never_runs_the_node() -> None:
    with patch("nautilus_zerodte.cli.main.build_trading_node") as mock_build:
        node = MagicMock()
        mock_build.return_value = node
        result = runner.invoke(app, ["paper", "-c", str(PROFILE), "--dry-run"])
    assert result.exit_code == 0, result.stdout
    assert "MODE: BUILD ONLY" in result.output
    assert mock_build.call_args[0][0].build_only is True
    node.run.assert_not_called()


def test_mainnet_live_banner_warns_about_real_funds(monkeypatch: pytest.MonkeyPatch) -> None:
    """The most dangerous combination must say so in words, not in a boolean."""
    from nautilus_zerodte.cli.main import MODE_LIVE, _mode_banner

    # Load the real Deribit profile rather than patching an adapter enum by hand -
    # model_copy skips validation, so a hand-set string would not match production.
    from nautilus_zerodte.config.loader import load_config

    btc_profile = REPO_ROOT / "configs" / "profiles" / "paper_btc.yaml"
    config = load_config(btc_profile).model_copy(update=LIVE_PROFILE_UPDATE)
    config = config.model_copy(
        update={"deribit": config.deribit.model_copy(update={"testnet": False})}
    )
    banner = _mode_banner(mode=MODE_LIVE, app_config=config, journal_path=Path("x.jsonl"))
    assert "MAINNET" in banner
    assert "Real funds" in banner


def test_config_reaching_the_node_keeps_a_validated_adapter() -> None:
    """The CLI mutates config with model_copy, which skips validation.

    The banner branches on venue.adapter, so pin that the mode-resolution path cannot hand
    build_trading_node a bare string. If a future model_copy starts updating `venue`, this
    is what fails.
    """
    from nautilus_zerodte.models.enums import VenueAdapter

    with patch("nautilus_zerodte.cli.main.build_trading_node") as mock_build:
        mock_build.return_value = MagicMock()
        result = runner.invoke(app, ["paper", "-c", str(PROFILE)])
    assert result.exit_code == 0, result.stdout
    assert isinstance(mock_build.call_args[0][0].venue.adapter, VenueAdapter)
