"""The ``audit`` plugin: ``nyx audit`` — a one-shot combined assessment.

Runs DNS, TLS, and HTTP checks against a domain concurrently and reports
them together, so a user doesn't have to chain three separate commands to
get a first read on a target's posture.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from urllib.parse import urlsplit

import typer
from rich.markup import escape as escape_markup
from rich.table import Table
from rich.text import Text

from nyxor.core.config import NyxorConfig
from nyxor.core.context import NyxorContext
from nyxor.core.explain import explain
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import ModuleResult, Severity
from nyxor.core.output import SEVERITY_STYLE, emit_results
from nyxor.core.scoring import render_badge, render_terminal_badge, score_results
from nyxor.plugins.analyze.advisor import dumber_writeup, fix_suggestions
from nyxor.plugins.dns_.plugin import run_lookup as dns_run_lookup
from nyxor.plugins.http_.plugin import run_inspect as http_run_inspect
from nyxor.plugins.inventory.store import InventoryStore
from nyxor.plugins.tls_.plugin import run_inspect as tls_run_inspect

_SEVERITY_ORDER = list(Severity)


def _hostname_for_dns(domain: str) -> str:
    """DNS needs a bare hostname — TLS/HTTP both accept a full URL

    (`nyx audit https://example.com/` is meant to work, same as
    `nyx http inspect` already does), but resolving the literal string
    "https://example.com/" as a domain name doesn't, so pull the host back
    out of it first.
    """
    if "://" in domain:
        return urlsplit(domain).hostname or domain
    if domain.startswith("[") and "]" in domain:
        return domain[1 : domain.index("]")]
    if domain.count(":") == 1:
        return domain.split(":", 1)[0]
    return domain


async def run_audit(domain: str, config: NyxorConfig) -> list[ModuleResult]:
    """Run DNS, TLS, and HTTP checks against ``domain`` concurrently."""
    dns_result, tls_result, http_result = await asyncio.gather(
        dns_run_lookup(_hostname_for_dns(domain), config.dns.resolvers, config.dns.timeout_seconds),
        tls_run_inspect(domain, config.tls.timeout_seconds),
        http_run_inspect(domain, config.http),
    )
    return [dns_result, tls_result, http_result]


def _print_summary(context: NyxorContext, domain: str, results: list[ModuleResult]) -> None:
    score = score_results(results)
    badge = render_terminal_badge(score, label=domain)
    badge.append(f"  {score.points}/100", style="dim")
    context.console.print(badge)

    grade_text = f"grade [{score.color}]{score.grade}[/] ({score.points}/100)"
    table = Table(
        title=f"Audit summary — {escape_markup(domain)}  ·  {grade_text}",
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


async def _print_dumber(
    context: NyxorContext, domain: str, results: list[ModuleResult], *, no_local: bool
) -> None:
    console = context.console
    console.print()
    console.rule("[bold]Plain-English rundown[/bold] (no jargon, promise)")

    ai_config = context.config.ai
    ai_text = (
        None
        if no_local
        else await dumber_writeup(
            domain,
            results,
            host=ai_config.ollama_host,
            model=ai_config.model,
            timeout_seconds=ai_config.timeout_seconds,
        )
    )

    if ai_text is not None:
        console.print(f"[dim](written by local model: {ai_config.model})[/dim]\n")
        # ai_text is model-generated free text — escape it the same as any
        # other text sourced from outside NYXOR's own hardcoded strings.
        console.print(escape_markup(ai_text))
        console.print()
        return

    for result in results:
        if not result.findings:
            continue
        console.print(f"\n[bold #7ee7e1]{result.module}[/]")
        for finding in result.findings:
            style = SEVERITY_STYLE[finding.severity]
            # finding.title and explain()'s output both embed text sourced
            # from the scanned target — escape so a literal "[" in it can't
            # be parsed as a Rich style tag.
            console.print(f"  [{style}]●[/] [bold]{escape_markup(finding.title)}[/]")
            console.print(f"    {escape_markup(explain(finding))}", style="dim")
    console.print()


async def _print_fix_suggestions(
    context: NyxorContext, results: list[ModuleResult], *, no_local: bool
) -> None:
    console = context.console
    if no_local:
        return

    ai_config = context.config.ai
    console.print()
    console.rule("[bold]Suggested fixes[/bold] (local model)")
    text = await fix_suggestions(
        results,
        host=ai_config.ollama_host,
        model=ai_config.model,
        timeout_seconds=ai_config.timeout_seconds,
    )
    if text is None:
        console.print("[dim]No local model reachable, or nothing medium-or-worse to fix.[/dim]")
        return
    console.print(escape_markup(text))
    console.print()


def _audit(
    ctx: typer.Context,
    domain: str,
    no_inventory: bool = typer.Option(False, "--no-inventory"),
    badge: Path | None = typer.Option(
        None, "--badge", help="Write a shields.io-style security grade SVG badge to this path."
    ),
    dumber: bool = typer.Option(
        False,
        "--dumber",
        help="Explain every finding in plain, no-jargon language "
        "(uses a local model if one is reachable, template fallback otherwise).",
    ),
    fix_suggestions_flag: bool = typer.Option(
        False,
        "--fix-suggestions",
        help="Ask a local model for concrete remediation steps on medium+ findings.",
    ),
    no_local: bool = typer.Option(
        False,
        "--no-local",
        help="Skip the local model for --dumber/--fix-suggestions (templates/skip instead).",
    ),
    fail_on: Severity | None = typer.Option(
        None,
        "--fail-on",
        help="Exit with code 1 if any finding is at least this severity — for CI gates.",
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
        if dumber:
            asyncio.run(_print_dumber(context, domain, results, no_local=no_local))
        if fix_suggestions_flag:
            asyncio.run(_print_fix_suggestions(context, results, no_local=no_local))
    emit_results(context, results, title=f"NYXOR Audit — {domain}")

    if fail_on is not None and score_results(results).meets_or_exceeds(fail_on):
        context.console.print(
            f"[bold red]--fail-on {fail_on.value}:[/bold red] "
            f"at least one {fail_on.value}-or-worse finding was found."
        )
        raise typer.Exit(code=1)


class AuditPlugin:
    metadata = PluginMetadata(
        name="audit",
        description="Combined DNS, TLS, and HTTP assessment for a single domain.",
        version="0.1.0",
        author="NYXOR",
        commands=("audit",),
        category="Scanning",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("audit", rich_help_panel=self.metadata.category)(_audit)


PLUGIN = AuditPlugin()
