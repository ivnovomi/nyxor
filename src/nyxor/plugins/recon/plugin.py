"""The ``recon`` plugin: ``nyx recon`` — passive subdomain discovery.

Combines certificate transparency logs (see `sources.py`) with an optional
DNS resolution pass to tell "seen in a cert once" apart from "resolves
right now" — still entirely passive: a standard DNS lookup, the same kind
`nyx dns lookup` already does, not a probe against the target.
"""

from __future__ import annotations

import asyncio

import dns.asyncresolver
import dns.exception
import dns.resolver
import typer
from rich.markup import escape as escape_markup
from rich.table import Table

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import Asset, Finding, ModuleResult, Severity
from nyxor.core.output import emit_results
from nyxor.plugins.recon.sources import crtsh_subdomains

recon_app = typer.Typer(
    name="recon",
    help="Passive subdomain discovery via certificate transparency.",
    no_args_is_help=True,
)

MAX_RESOLVE_CONCURRENCY = 20
_RESOLVE_EXCEPTIONS = (
    dns.resolver.NXDOMAIN,
    dns.resolver.NoAnswer,
    dns.resolver.NoNameservers,
    dns.exception.Timeout,
)


async def _resolves(name: str, timeout: float, semaphore: asyncio.Semaphore) -> bool:
    resolver = dns.asyncresolver.Resolver()
    resolver.timeout = timeout
    resolver.lifetime = timeout
    async with semaphore:
        try:
            await resolver.resolve(name, "A")
            return True
        except _RESOLVE_EXCEPTIONS:
            return False


async def run_recon(
    domain: str, *, resolve: bool = True, timeout: float = 15.0, limit: int = 500
) -> list[ModuleResult]:
    result = ModuleResult(module="recon.subdomains", target=domain)

    subdomains = await crtsh_subdomains(domain, timeout=timeout)
    if not subdomains:
        result.errors.append(
            "crt.sh returned nothing (no certificates on record, or the service is unavailable)"
        )
        return [result]

    names = sorted(subdomains)[:limit]
    live: dict[str, bool] = {}
    if resolve:
        semaphore = asyncio.Semaphore(MAX_RESOLVE_CONCURRENCY)
        statuses = await asyncio.gather(*(_resolves(name, timeout, semaphore) for name in names))
        live = dict(zip(names, statuses, strict=True))

    for name in names:
        is_live = live.get(name)
        severity = Severity.INFO
        if is_live is True:
            description = "Resolves now — live host."
        elif is_live is False:
            description = "Seen in a certificate, doesn't resolve now — possibly decommissioned."
        else:
            description = "Seen in a certificate (resolution not checked)."
        result.findings.append(
            Finding(
                title=name,
                severity=severity,
                target=domain,
                description=description,
                evidence={"live": is_live},
                tags=("subdomain", "live") if is_live else ("subdomain",),
            )
        )
        result.assets.append(
            Asset(
                kind="subdomain",
                identifier=name,
                attributes={"live": is_live},
                source_module="recon.subdomains",
            )
        )

    result.raw_data = {"total_found": len(subdomains), "shown": len(names), "resolved": resolve}
    return [result]


def _print_summary(context: NyxorContext, domain: str, results: list[ModuleResult]) -> None:
    result = results[0]
    live_count = sum(1 for f in result.findings if f.evidence.get("live") is True)
    table = Table(
        title=f"Recon — {domain}  ({len(result.findings)} subdomain(s), {live_count} live)",
        show_header=True,
        header_style="bold",
    )
    table.add_column("Subdomain")
    table.add_column("Status")
    for finding in result.findings:
        live = finding.evidence.get("live")
        if live is True:
            status = "[green]live[/]"
        elif live is False:
            status = "[dim]historical[/]"
        else:
            status = "[dim]?[/]"
        table.add_row(escape_markup(finding.title), status)
    context.console.print(table)


def _recon(
    ctx: typer.Context,
    domain: str,
    no_resolve: bool = typer.Option(
        False, "--no-resolve", help="Skip DNS resolution — just list names seen in certificates."
    ),
    limit: int = typer.Option(500, "--limit", help="Maximum subdomains to report."),
) -> None:
    """Passively discover subdomains via certificate transparency logs."""
    context: NyxorContext = ctx.obj
    results = asyncio.run(run_recon(domain, resolve=not no_resolve, limit=limit))

    if context.output.format == "table" and context.output.output_path is None:
        _print_summary(context, domain, results)
    emit_results(context, results, title=f"NYXOR Recon — {domain}")


class ReconPlugin:
    metadata = PluginMetadata(
        name="recon",
        description="Passive subdomain discovery via certificate transparency logs.",
        version="0.1.0",
        author="NYXOR",
        commands=("recon",),
        category="Scanning",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("recon", rich_help_panel=self.metadata.category)(_recon)


PLUGIN = ReconPlugin()
