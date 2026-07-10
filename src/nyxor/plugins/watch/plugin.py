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
from rich.markup import escape as escape_markup

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.scoring import render_terminal_badge, score_results
from nyxor.plugins.analyze.advisor import watch_narration
from nyxor.plugins.audit.plugin import run_audit

MIN_INTERVAL_SECONDS = 5.0

# (module, finding title, finding description) — stable across runs, unlike
# Finding.id which is a fresh UUID every time.
Fingerprint = tuple[str, str, str]


async def _watch_loop(
    domain: str, context: NyxorContext, interval: float, iterations: int, *, narrate: bool
) -> None:
    """
    Continuously audits a domain and reports finding and grade changes.
    
    Parameters:
        domain (str): Domain to monitor.
        interval (float): Seconds to wait between checks.
        iterations (int): Number of checks to perform; zero runs continuously.
        narrate (bool): Whether to generate narration for detected changes.
    """
    console = context.console
    console.print(
        f"[bold #7ee7e1]Watching[/] {escape_markup(domain)} every {interval:.0f}s "
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
                f"[dim]{timestamp}[/] baseline —",
                render_terminal_badge(score, label="grade"),
                f"({score.points}/100), {len(current)} finding(s)",
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
                        f"{timestamp} [bold]grade:[/] {previous_grade} ->",
                        render_terminal_badge(score, label="grade"),
                    )
                for module, title, description in new:
                    # title/description are finding text sourced from the
                    # scanned target — escape so a literal "[" in them can't
                    # be parsed as a Rich style tag.
                    console.print(
                        f"{timestamp} [bold #ff4d6d]NEW[/] [{module}] "
                        f"{escape_markup(title)} — {escape_markup(description)}"
                    )
                for module, title, _description in resolved:
                    console.print(
                        f"{timestamp} [bold #2ecc71]RESOLVED[/] [{module}] {escape_markup(title)}"
                    )

                if narrate and previous_grade is not None:
                    ai_config = context.config.ai
                    narration = await watch_narration(
                        domain,
                        grade=score.grade,
                        previous_grade=previous_grade,
                        new=list(new),
                        resolved=list(resolved),
                        host=ai_config.ollama_host,
                        model=ai_config.model,
                        timeout_seconds=ai_config.timeout_seconds,
                    )
                    if narration:
                        console.print(f"{timestamp} [bold #7ee7e1]»[/] {escape_markup(narration)}")

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
    narrate: bool = typer.Option(
        False,
        "--narrate",
        help="On a change, ask a local model for a one-line plain-English narration.",
    ),
) -> None:
    """
    Continuously audit a domain and report only changes between checks.
    
    Parameters:
        domain (str): Domain to monitor.
        interval (float): Seconds to wait between checks.
        iterations (int): Number of checks to run; zero runs continuously.
        narrate (bool): Whether to generate a one-line narration when changes occur.
    
    Raises:
        typer.BadParameter: If the interval is less than the minimum allowed value.
    """
    context: NyxorContext = ctx.obj
    if interval < MIN_INTERVAL_SECONDS:
        raise typer.BadParameter(f"--interval must be >= {MIN_INTERVAL_SECONDS:.0f}s.")

    try:
        asyncio.run(_watch_loop(domain, context, interval, iterations, narrate=narrate))
    except KeyboardInterrupt:
        context.console.print("\n[dim]Stopped.[/]")


class WatchPlugin:
    metadata = PluginMetadata(
        name="watch",
        description="Continuously audit a domain and report only new/resolved findings.",
        version="0.1.0",
        author="NYXOR",
        commands=("watch",),
        category="Continuous & History",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("watch", rich_help_panel=self.metadata.category)(_watch)


PLUGIN = WatchPlugin()
