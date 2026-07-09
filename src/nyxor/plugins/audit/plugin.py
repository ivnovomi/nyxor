"""The ``audit`` plugin: ``nyx audit`` — a one-shot combined assessment.

Runs DNS, TLS, and HTTP checks against a domain concurrently and reports
them together, so a user doesn't have to chain three separate commands to
get a first read on a target's posture.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.table import Table
from rich.text import Text

from nyxor.core.config import NyxorConfig
from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import ModuleResult, Severity
from nyxor.core.output import SEVERITY_STYLE, emit_results
from nyxor.core.scoring import render_badge, score_results
from nyxor.plugins.dns_.plugin import run_lookup as dns_run_lookup
from nyxor.plugins.http_.plugin import run_inspect as http_run_inspect
from nyxor.plugins.inventory.store import InventoryStore
from nyxor.plugins.tls_.plugin import run_inspect as tls_run_inspect

_SEVERITY_ORDER = list(Severity)


async def run_audit(domain: str, config: NyxorConfig) -> list[ModuleResult]:
    """Run DNS, TLS, and HTTP checks against ``domain`` concurrently."""
    dns_result, tls_result, http_result = await asyncio.gather(
        dns_run_lookup(domain, config.dns.resolvers, config.dns.timeout_seconds),
        tls_run_inspect(domain, config.tls.timeout_seconds),
        http_run_inspect(domain, config.http),
    )
    return [dns_result, tls_result, http_result]


def _print_summary(context: NyxorContext, domain: str, results: list[ModuleResult]) -> None:
    score = score_results(results)
    grade_text = f"grade [{score.color}]{score.grade}[/] ({score.points}/100)"
    table = Table(
        title=f"Audit summary — {domain}  ·  {grade_text}",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Module")
    table.add_column("Findings")
    table.add_column("Highest severity")

    for result in results:
        if not result.findings:
            worst = Text("-", style="dim")
        else:
            worst_finding = max(result.findings, key=lambda f: _SEVERITY_ORDER.index(f.severity))
            worst_severity = worst_finding.severity
            worst = Text(worst_severity.value.upper(), style=SEVERITY_STYLE[worst_severity])
        table.add_row(result.module, str(len(result.findings)), worst)

    context.console.print(table)


def _audit(
    ctx: typer.Context,
    domain: str,
    no_inventory: bool = typer.Option(False, "--no-inventory"),
    badge: Path | None = typer.Option(
        None, "--badge", help="Write a shields.io-style security grade SVG badge to this path."
    ),
) -> None:
    """Run a combined DNS + TLS + HTTP audit against a domain."""
    context: NyxorContext = ctx.obj
    results = asyncio.run(run_audit(domain, context.config))

    all_assets = [asset for result in results for asset in result.assets]
    if all_assets and not no_inventory:
        InventoryStore().add(all_assets)

    if badge is not None:
        score = score_results(results)
        badge.parent.mkdir(parents=True, exist_ok=True)
        badge.write_text(render_badge(score, label=f"nyxor: {domain}"), encoding="utf-8")
        context.console.print(f"[green]Wrote badge[/green] {badge} (grade {score.grade})")

    if context.output.format == "table" and context.output.output_path is None:
        _print_summary(context, domain, results)
    emit_results(context, results, title=f"NYXOR Audit — {domain}")


class AuditPlugin:
    metadata = PluginMetadata(
        name="audit",
        description="Combined DNS, TLS, and HTTP assessment for a single domain.",
        version="0.1.0",
        author="NYXOR",
        commands=("audit",),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("audit")(_audit)


PLUGIN = AuditPlugin()
