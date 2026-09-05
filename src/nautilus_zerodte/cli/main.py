from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import typer

from nautilus_zerodte.config.loader import load_config
from nautilus_zerodte.config.schema import StreamCaptureConfig
from nautilus_zerodte.journal.service import Journal, gate_rejection_report, journal_overview
from nautilus_zerodte.models.enums import GateStage, VenueAdapter
from nautilus_zerodte.node.factory import build_trading_node, run_backtest
from nautilus_zerodte.node.streaming import convert_stream_catalog
from nautilus_zerodte.research.offline import run_catalog_partitions

app = typer.Typer(
    name="nautilus-zerodte",
    help="0DTE extension layer on NautilusTrader.",
    no_args_is_help=True,
)

journal_app = typer.Typer(help="Inspect JSONL audit logs.")
catalog_app = typer.Typer(help="Catalog capture and conversion.")
research_app = typer.Typer(help="Offline catalog research (never on order path).")
app.add_typer(journal_app, name="journal")
app.add_typer(catalog_app, name="catalog")
app.add_typer(research_app, name="research")


LIVE_ENV_VAR = "ZERODTE_ALLOW_LIVE"
_TRUTHY = {"1", "true", "yes"}

# Execution modes for the `paper` command. Named so the operator sees a word, not a boolean.
MODE_BUILD_ONLY = "BUILD ONLY"
MODE_OBSERVE = "OBSERVE"
MODE_LIVE = "LIVE"


def _missing_live_opt_ins(app_config, *, live_flag: bool) -> list[str]:
    """Which of the three independent live opt-ins are absent.

    Empty list means all three are present and real orders may be submitted. Three separate
    sources on purpose: a copied profile, a stale shell, or a habitual flag should each be
    survivable on its own. Two agreeing is not enough.
    """
    missing: list[str] = []
    if not live_flag:
        missing.append("the --live flag")
    if not app_config.allow_live:
        missing.append("allow_live: true in the profile")
    if os.environ.get(LIVE_ENV_VAR, "").strip().lower() not in _TRUTHY:
        missing.append(f"{LIVE_ENV_VAR}=1 in the environment")
    return missing


def _mode_banner(*, mode: str, app_config, journal_path: Path) -> str:
    """A banner the operator cannot miss, printed before the node does anything.

    The old output was `TradingNode built (dry_run=False)` followed by `Starting live node`,
    which is easy to skim past and does not say whether real money is at risk.
    """
    rule = "=" * 72
    venue = app_config.venue.name
    if app_config.venue.adapter == VenueAdapter.DERIBIT:
        venue = f"{venue} ({'TESTNET' if app_config.deribit.testnet else 'MAINNET'})"

    if mode == MODE_LIVE:
        headline = "MODE: LIVE - REAL ORDERS WILL BE SUBMITTED"
    elif mode == MODE_OBSERVE:
        headline = "MODE: OBSERVE - gates run and intents are journalled, NO orders are sent"
    else:
        headline = "MODE: BUILD ONLY - the node is constructed and never run"

    lines = [
        rule,
        f"  {headline}",
        rule,
        f"  Venue      {venue}",
        f"  Trader     {app_config.trader_id}",
        f"  Strategy   {app_config.strategy.strategy_id}",
        f"  Journal    {journal_path}",
    ]
    if mode == MODE_LIVE:
        lines += [
            "  Opt-ins    --live flag + profile allow_live + " + LIVE_ENV_VAR,
            "",
            "  This will place real orders against a real account and can lose money.",
        ]
        if app_config.venue.adapter == VenueAdapter.DERIBIT and not app_config.deribit.testnet:
            lines += ["  MAINNET: this is not testnet. Real funds."]
    elif mode == MODE_OBSERVE:
        lines += [
            "",
            "  To submit real orders, ALL THREE of these are required:",
            "    1. the --live flag",
            "    2. allow_live: true in the profile",
            f"    3. {LIVE_ENV_VAR}=1 in the environment",
        ]
    lines.append(rule)
    return "\n".join(lines)


def _enable_stream_capture(
    app_config,
    *,
    run_id: str | None = None,
):  # noqa: ANN001
    run_id = run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    stream_path = f"data/streaming/{run_id}"
    catalog_path = f"data/catalogs/{run_id}"
    streaming = app_config.streaming.model_copy(
        update={
            "enabled": True,
            "stream_path": stream_path,
            "permanent_catalog_path": catalog_path,
        }
    )
    return app_config.model_copy(update={"streaming": streaming}), run_id


@app.command()
def backtest(
    config: Path = typer.Option(..., "--config", "-c", help="Profile YAML path."),
    catalog: Path = typer.Option(..., "--catalog", help="Parquet catalog directory."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Evaluate only; no order submit."),
) -> None:
    """Run a catalog backtest with the skeleton strategy."""
    app_config = load_config(config)
    if dry_run:
        app_config = app_config.model_copy(update={"dry_run": True})
    journal = run_backtest(app_config, catalog)
    typer.echo(f"Backtest complete. Journal: {journal.path}")


@app.command()
def paper(
    config: Path = typer.Option(..., "--config", "-c", help="Profile YAML path."),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Build the node and exit without running it."
    ),
    live: bool = typer.Option(
        False,
        "--live",
        help=(
            "Submit REAL orders. Also requires allow_live: true in the profile and "
            f"{LIVE_ENV_VAR}=1 in the environment."
        ),
    ),
    streaming: bool = typer.Option(
        False,
        "--streaming",
        help="Capture HOT/WARM market data to feather for later catalog convert.",
    ),
) -> None:
    """Build (and optionally run) a TradingNode against the configured venue adapter.

    Three modes. The default submits nothing.
      (no flags)   OBSERVE    - run, evaluate gates, journal intents, submit nothing
      --dry-run    BUILD ONLY - construct the node and exit without running it
      --live       LIVE       - submit real orders, and only with all three opt-ins
    """
    app_config = load_config(config)

    if dry_run and live:
        typer.echo("--dry-run and --live are mutually exclusive.", err=True)
        raise typer.Exit(code=2)

    if dry_run:
        app_config = app_config.model_copy(update={"build_only": True, "dry_run": True})
        mode = MODE_BUILD_ONLY
    else:
        missing = _missing_live_opt_ins(app_config, live_flag=live)
        if live and missing:
            # Fail closed and loudly. Never silently downgrade a --live request to OBSERVE:
            # the operator asked for live, and quietly doing something else is how someone
            # believes orders are going out when they are not.
            typer.echo("REFUSING TO START: --live was requested but not granted.", err=True)
            typer.echo("Missing opt-in(s):", err=True)
            for item in missing:
                typer.echo(f"  - {item}", err=True)
            raise typer.Exit(code=2)
        app_config = app_config.model_copy(update={"build_only": False, "dry_run": bool(missing)})
        mode = MODE_LIVE if not missing else MODE_OBSERVE

    run_id: str | None = None
    if streaming:
        app_config, run_id = _enable_stream_capture(app_config)

    journal_path = app_config.resolved_journal_path()
    journal = Journal(journal_path)
    # The banner goes out before anything is constructed or connected, so an operator who
    # stops reading after the first screenful has still seen whether money is at risk.
    typer.echo(_mode_banner(mode=mode, app_config=app_config, journal_path=journal_path))
    journal.record(
        GateStage.LIFECYCLE,
        payload={
            "event": "NODE_START",
            "node": "TradingNode",
            "mode": mode,
            "dry_run": app_config.dry_run,
            "build_only": app_config.build_only,
            "streaming": app_config.streaming.enabled,
            "run_id": run_id,
            "stream_path": app_config.streaming.stream_path if run_id else None,
        },
    )
    node = build_trading_node(app_config)
    typer.echo(f"TradingNode built. Journal: {journal_path}")
    if run_id:
        typer.echo(
            f"Streaming enabled (run_id={run_id}). "
            f"After stop: nautilus-zerodte catalog convert --run-id {run_id}"
        )
    if app_config.build_only:
        journal.record(
            GateStage.LIFECYCLE,
            payload={"event": "NODE_STOP", "node": "TradingNode", "reason": "build_only"},
        )
        return
    typer.echo(f"Starting node in {mode} mode - Ctrl+C to stop.")
    try:
        node.build()
        node.run()
    finally:
        journal.record(
            GateStage.LIFECYCLE,
            payload={
                "event": "NODE_STOP",
                "node": "TradingNode",
                "mode": mode,
                "run_id": run_id,
            },
        )


@catalog_app.command("convert")
def catalog_convert(
    run_id: str = typer.Option(..., "--run-id", help="Captured stream run id."),
    stream_base: Path = typer.Option(
        Path("data/streaming"),
        "--stream-base",
        help="Base directory containing captured feather streams.",
    ),
    catalog_out: Path | None = typer.Option(
        None,
        "--catalog-out",
        help="Output Parquet catalog directory (default: data/catalogs/<run-id>).",
    ),
    instance_id: str | None = typer.Option(
        None,
        "--instance-id",
        help="NT kernel instance id when multiple live captures exist.",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        "-c",
        help="Optional profile for include_types defaults.",
    ),
) -> None:
    """Convert a captured feather stream into a replayable Parquet catalog."""
    include_types = StreamCaptureConfig().include_types
    if config is not None:
        include_types = load_config(config).streaming.include_types

    output = catalog_out or Path("data/catalogs") / run_id
    result = convert_stream_catalog(
        stream_base=stream_base,
        run_id=run_id,
        catalog_out=output,
        include_types=include_types,
        instance_id=instance_id,
    )
    typer.echo(f"Converted stream {run_id} to catalog: {result}")
    typer.echo(f"Replay: nautilus-zerodte backtest --config <profile> --catalog {result}")


@research_app.command("catalog")
def research_catalog(
    catalog: Path = typer.Option(..., "--catalog", help="Parquet catalog directory."),
    workers: int | None = typer.Option(None, "--workers", help="ProcessPool worker count."),
) -> None:
    """Run offline quote-tick partition research over a catalog."""
    results = run_catalog_partitions(catalog, max_workers=workers)
    typer.echo(f"Partitions analyzed: {len(results)}")
    for row in results:
        typer.echo(f"  {row['instrument_id']}: {row['quote_tick_count']} quote ticks")


@app.command()
def flatten(
    config: Path = typer.Option(..., "--config", "-c", help="Profile YAML path."),
) -> None:
    """Request emergency flatten - journals intent; session flatten is automatic when node runs."""
    app_config = load_config(config)
    journal_path = app_config.resolved_journal_path()
    journal = Journal(journal_path)
    journal.record(
        GateStage.LIFECYCLE,
        payload={
            "event": "FLATTEN_REQUEST",
            "strategy_id": app_config.strategy.strategy_id,
            "note": "Live flatten requires running node; SessionActor flatten_signal is automatic",
        },
        strategy_id=app_config.strategy.strategy_id,
        level="WARN",
    )
    typer.echo(
        f"Flatten request recorded in journal: {journal_path}. "
        "In-position strategies flatten on SessionActor blackout when the node is running."
    )


@journal_app.command("report")
def journal_report(
    path: Path = typer.Option(..., "--path", "-p", help="JSONL journal file."),
) -> None:
    """Report gate failures by stage and breached rule - for policy tuning."""
    report = gate_rejection_report(Journal.load(path))
    typer.echo(f"Gate rejection report: {path}")
    typer.echo(f"Total rejections: {report.total}")
    if report.by_stage:
        typer.echo("\nBy stage:")
        for stage, count in sorted(report.by_stage.items()):
            typer.echo(f"  {stage}: {count}")
    if report.by_rule:
        typer.echo("\nBy breached rule:")
        for rule, count in sorted(report.by_rule.items(), key=lambda x: (-x[1], x[0])):
            typer.echo(f"  {rule}: {count}")
    if not report.by_stage and not report.by_rule:
        typer.echo("No gate rejections found.")


@journal_app.command("summary")
def journal_summary(
    path: Path = typer.Option(..., "--path", "-p", help="JSONL journal file."),
) -> None:
    """Summarize journal entries by stage, gate rejections, and recent events."""
    overview = journal_overview(Journal.load(path))
    typer.echo(f"Journal: {path}")
    typer.echo(f"Total entries: {overview.total}")
    if overview.strategies:
        typer.echo(f"Strategies: {', '.join(sorted(overview.strategies))}")
    typer.echo("Stage counts:")
    for stage, count in sorted(overview.stage_counts.items()):
        typer.echo(f"  {stage}: {count}")

    if overview.gate_rejections:
        typer.echo("\nGate rejections:")
        for stage, count in sorted(overview.gate_rejections.items()):
            typer.echo(f"  {stage}: {count}")

    typer.echo("\nLast 10 entries:")
    for entry in overview.last_entries:
        event = entry.payload.get("event", "")
        breached = entry.payload.get("breached_rules")
        extra = f" rules={breached}" if breached else ""
        typer.echo(
            f"  [{entry.ts.isoformat()}] {entry.stage.value}"
            f"{f'/{event}' if event else ''}"
            f"{f' strategy={entry.strategy_id}' if entry.strategy_id else ''}"
            f"{extra}"
        )


if __name__ == "__main__":
    app()
