from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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
    journal_path = tmp_path / "flatten.jsonl"
    with patch.dict("os.environ", {}, clear=False):
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
