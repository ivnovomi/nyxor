"""The ``trends`` plugin: ``nyx trends <domain>`` — score history over time.

Runs an audit, records the score, and reports real statistics (mean, std,
least-squares trend slope) over every recorded run for that domain — not
just "did the grade go up or down since last time".
"""

from __future__ import annotations

import asyncio

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.scoring import score_results
from nyxor.plugins.audit.plugin import run_audit
from nyxor.plugins.trends.analysis import analyze, z_scores
from nyxor.plugins.trends.store import TrendStore

trends_app = typer.Typer(
    name="trends", help="Score history and trend analysis for a domain.", no_args_is_help=True
)


@trends_app.command("show")
def show(
    ctx: typer.Context,
    domain: str,
    no_record: bool = typer.Option(
        False, "--no-record", help="Only report existing history — don't run a new audit."
    ),
    limit: int = typer.Option(30, "--limit", help="Number of most recent runs to consider."),
) -> None:
    """Audit a domain, record its score, and report the trend."""
    context: NyxorContext = ctx.obj
    store = TrendStore()

    if not no_record:
        results = asyncio.run(run_audit(domain, context.config))
        score = score_results(results)
        store.record(domain, score.points, score.grade)

    history = store.history(domain, limit=limit)
    if not history:
        context.console.print(
            f"[dim]No history for {domain} yet.[/dim] Run without --no-record first."
        )
        raise typer.Exit(code=1)

    points = [sample["points"] for sample in history]
    stats = analyze(points)
    assert stats is not None  # history is non-empty, analyze() only returns None on empty input

    direction_style = {
        "improving": "green",
        "degrading": "red",
        "flat": "dim",
    }[stats.direction]

    context.console.print(f"[bold]Trend — {domain}[/bold]  ({stats.n} run(s) considered)")
    context.console.print(f"  {stats.sparkline}")
    context.console.print(
        f"  mean {stats.mean:.1f}  ·  std {stats.std:.1f}  ·  range {stats.minimum}-{stats.maximum}"
    )
    context.console.print(
        f"  trend: [{direction_style}]{stats.direction}[/{direction_style}] "
        f"({stats.slope_per_run:+.2f} points/run)"
    )

    latest = history[-1]
    zs = z_scores(points)
    latest_z = zs[-1]
    if abs(latest_z) >= 2:
        context.console.print(
            f"  [bold yellow]latest run is an outlier[/bold yellow] "
            f"(z={latest_z:+.2f}, grade {latest['grade']}, {latest['points']} pts)"
        )


@trends_app.command("clear")
def clear(ctx: typer.Context, domain: str) -> None:
    """Delete recorded history for a domain."""
    context: NyxorContext = ctx.obj
    if TrendStore().clear(domain):
        context.console.print(f"[green]Cleared[/green] history for {domain}.")
    else:
        context.console.print(f"[dim]No history for {domain}.[/dim]")


class TrendsPlugin:
    metadata = PluginMetadata(
        name="trends",
        description="Score history and NumPy-backed trend analysis for a domain.",
        version="0.1.0",
        author="NYXOR",
        commands=("show", "clear"),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.add_typer(trends_app)


PLUGIN = TrendsPlugin()
