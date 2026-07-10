"""The ``dns`` plugin: ``nyx dns lookup``."""

from __future__ import annotations

import asyncio
from typing import cast

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import Asset, Finding, ModuleResult, Severity
from nyxor.core.output import emit_results
from nyxor.plugins.dns_.lookups import (
    DEFAULT_RECORD_TYPES,
    check_dnssec,
    check_mail_records,
    lookup_records,
)

dns_app = typer.Typer(
    name="dns", help="DNS record lookup, DNSSEC, and mail record checks.", no_args_is_help=True
)


async def run_lookup(domain: str, resolvers: list[str], timeout: float) -> ModuleResult:
    result = ModuleResult(module="dns.lookup", target=domain)

    records, dnssec_enabled, mail = await asyncio.gather(
        lookup_records(domain, DEFAULT_RECORD_TYPES, resolvers, timeout),
        check_dnssec(domain, resolvers, timeout),
        check_mail_records(domain, resolvers, timeout),
    )

    for rtype, values in records.items():
        if not values:
            continue
        # DNS answers can come back in a different (e.g. round-robin) order
        # on every lookup even when nothing changed — sort so a stable set
        # of records doesn't look "new" to diffing tools like `nyx watch`.
        sorted_values = sorted(values)
        result.findings.append(
            Finding(
                title=f"{rtype} record(s)",
                severity=Severity.INFO,
                target=domain,
                description=", ".join(sorted_values),
                evidence={"type": rtype, "values": sorted_values},
            )
        )
        for value in values:
            result.assets.append(
                Asset(kind=f"dns:{rtype.lower()}", identifier=value, source_module="dns.lookup")
            )

    result.findings.append(
        Finding(
            title="DNSSEC",
            severity=Severity.INFO if dnssec_enabled else Severity.MEDIUM,
            target=domain,
            description="DNSKEY record published."
            if dnssec_enabled
            else "No DNSKEY record found — DNSSEC likely not enabled.",
            evidence={"enabled": dnssec_enabled},
        )
    )

    mx = cast("list[str]", mail.get("mx") or [])
    result.findings.append(
        Finding(
            title="MX records",
            severity=Severity.INFO if mx else Severity.LOW,
            target=domain,
            description=", ".join(mx) if mx else "No MX records found.",
            evidence={"mx": mx},
        )
    )
    result.findings.append(
        Finding(
            title="SPF record",
            severity=Severity.INFO if mail.get("spf") else Severity.MEDIUM,
            target=domain,
            description=str(mail.get("spf")) if mail.get("spf") else "No SPF record found.",
        )
    )
    result.findings.append(
        Finding(
            title="DMARC record",
            severity=Severity.INFO if mail.get("dmarc") else Severity.MEDIUM,
            target=domain,
            description=str(mail.get("dmarc")) if mail.get("dmarc") else "No DMARC record found.",
        )
    )
    result.raw_data = {"records": records, "dnssec": dnssec_enabled, "mail": mail}
    return result


@dns_app.command("lookup")
def lookup(ctx: typer.Context, domain: str) -> None:
    """Look up standard records, DNSSEC status, and mail-related records for a domain."""
    context: NyxorContext = ctx.obj
    config = context.config.dns
    result = asyncio.run(run_lookup(domain, config.resolvers, config.timeout_seconds))
    emit_results(context, [result], title="NYXOR DNS Report")


class DnsPlugin:
    metadata = PluginMetadata(
        name="dns",
        description="Record lookup, DNSSEC detection, and mail-related DNS checks.",
        version="0.1.0",
        author="NYXOR",
        commands=("lookup",),
        category="Scanning",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.add_typer(dns_app, rich_help_panel=self.metadata.category)


PLUGIN = DnsPlugin()
