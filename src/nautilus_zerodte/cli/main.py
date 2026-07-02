from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import typer

from nautilus_zerodte.config.loader import load_config
from nautilus_zerodte.config.schema import StreamCaptureConfig
from nautilus_zerodte.journal.service import Journal, gate_rejection_report, journal_overview
from nautilus_zerodte.models.enums import GateStage
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
    dry_run: bool = typer.Option(False, "--dry-run", help="Build node without live orders."),
    streaming: bool = typer.Option(
        False,
        "--streaming",
        help="Capture HOT/WARM market data to feather for later catalog convert.",
    ),
) -> None:
    """Build (and optionally run) a TradingNode against the configured venue adapter."""
    app_config = load_config(config)
    if dry_run:
        app_config = app_config.model_copy(update={"dry_run": True})

    run_id: str | None = None
    if streaming:
        app_config, run_id = _enable_stream_capture(app_config)

    journal_path = app_config.resolved_journal_path()
    journal = Journal(journal_path)
    journal.record(
        GateStage.LIFECYCLE,
        payload={
            "event": "NODE_START",
            "node": "TradingNode",
            "dry_run": app_config.dry_run,
            "streaming": app_config.streaming.enabled,
            "run_id": run_id,
            "stream_path": app_config.streaming.stream_path if run_id else None,
        },
    )
    node = build_trading_node(app_config)
    typer.echo(f"TradingNode built (dry_run={app_config.dry_run}). Journal: {journal_path}")
    if run_id:
        typer.echo(
            f"Streaming enabled (run_id={run_id}). "
            f"After stop: nautilus-zerodte catalog convert --run-id {run_id}"
        )
    if app_config.dry_run:
        journal.record(
            GateStage.LIFECYCLE,
            payload={"event": "NODE_STOP", "node": "TradingNode", "reason": "dry_run"},
        )
        return
    typer.echo("Starting live node — Ctrl+C to stop.")
    try:
        node.build()
        node.run()
    finally:
        journal.record(
            GateStage.LIFECYCLE,
            payload={
                "event": "NODE_STOP",
                "node": "TradingNode",
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
    """Request emergency flatten — journals intent; session flatten is automatic when node runs."""
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
    """Report gate failures by stage and breached rule — for policy tuning."""
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
