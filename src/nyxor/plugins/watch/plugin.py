"""The ``watch`` plugin: ``nyx watch`` — continuous monitoring with diffs.

Re-runs `nyx audit` against a domain on an interval and only reports what
*changed* since the last check: new findings, resolved findings, and grade
transitions. Quiet in between — a heartbeat line, not a wall of repeated
output — so it's actually usable left running in a terminal.
"""

from __future__ import annotations

import asyncio
from datetime import datetime

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.scoring import score_results
from nyxor.plugins.audit.plugin import run_audit

MIN_INTERVAL_SECONDS = 5.0

# (module, finding title, finding description) — stable across runs, unlike
# Finding.id which is a fresh UUID every time.
Fingerprint = tuple[str, str, str]


def _grade_markup(grade: str, color: str) -> str:
    return f"[{color}]{grade}[/]"


async def _watch_loop(domain: str, context: NyxorContext, interval: float, iterations: int) -> None:
    console = context.console
    console.print(
        f"[bold #7ee7e1]Watching[/] {domain} every {interval:.0f}s "
        f"({iterations or '∞'} check(s)). Ctrl+C to stop."
    )

    previous: set[Fingerprint] | None = None
    previous_grade: str | None = None
    count = 0

    while iterations == 0 or count < iterations:
        count += 1
        timestamp = datetime.now().strftime("%H:%M:%S")
        results = await run_audit(domain, context.config)
        score = score_results(results)
        current: set[Fingerprint] = {
            (result.module, finding.title, finding.description)
            for result in results
            for finding in result.findings
        }

        if previous is None:
            console.print(
                f"[dim]{timestamp}[/] baseline — grade {_grade_markup(score.grade, score.color)} "
                f"({score.points}/100), {len(current)} finding(s)"
            )
        else:
            new = sorted(current - previous)
            resolved = sorted(previous - current)
            grade_changed = score.grade != previous_grade

            if not new and not resolved and not grade_changed:
                console.print(f"[dim]{timestamp} no changes (grade {score.grade})[/]")
            else:
                if grade_changed:
                    console.print(
                        f"{timestamp} [bold]grade:[/] {previous_grade} -> "
                        f"{_grade_markup(score.grade, score.color)}"
                    )
                for module, title, description in new:
                    console.print(
                        f"{timestamp} [bold #ff4d6d]NEW[/] [{module}] {title} — {description}"
                    )
                for module, title, _description in resolved:
                    console.print(f"{timestamp} [bold #2ecc71]RESOLVED[/] [{module}] {title}")

        previous = current
        previous_grade = score.grade

        if iterations != 0 and count >= iterations:
            break
        await asyncio.sleep(interval)


def _watch(
    ctx: typer.Context,
    domain: str,
    interval: float = typer.Option(300.0, "--interval", help="Seconds between checks."),
    iterations: int = typer.Option(0, "--iterations", help="Stop after N checks (0 = forever)."),
) -> None:
    """Continuously audit a domain and report only what changes."""
    context: NyxorContext = ctx.obj
    if interval < MIN_INTERVAL_SECONDS:
        raise typer.BadParameter(f"--interval must be >= {MIN_INTERVAL_SECONDS:.0f}s.")

    try:
        asyncio.run(_watch_loop(domain, context, interval, iterations))
    except KeyboardInterrupt:
        context.console.print("\n[dim]Stopped.[/]")


class WatchPlugin:
    metadata = PluginMetadata(
        name="watch",
        description="Continuously audit a domain and report only new/resolved findings.",
        version="0.1.0",
        author="NYXOR",
        commands=("watch",),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("watch")(_watch)


PLUGIN = WatchPlugin()
