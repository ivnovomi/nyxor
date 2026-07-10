"""The ``tls`` plugin: ``nyx tls inspect``."""

from __future__ import annotations

import asyncio
from urllib.parse import urlsplit

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import Asset, Finding, ModuleResult, Severity
from nyxor.core.output import emit_results
from nyxor.plugins.tls_.inspector import WEAK_PROTOCOLS, inspect

tls_app = typer.Typer(
    name="tls",
    help="Certificate inspection, expiry checks, protocol/cipher overview.",
    no_args_is_help=True,
)


def _parse_target(target: str) -> tuple[str, int]:
    # A full URL (nyx audit accepts one, same as http.inspect) — pull the
    # host/port back out instead of treating "https" as the hostname and
    # "//example.com/" as the port.
    if "://" in target:
        parsed = urlsplit(target)
        if parsed.hostname:
            return parsed.hostname, parsed.port or 443

    # Bracketed IPv6 literal, e.g. "[::1]:443" or bare "[::1]" — pull the
    # address out from between the brackets (unbracketed is what a socket
    # connection wants) before even looking for a ":port" suffix, so it
    # doesn't get treated as one big opaque hostname string port and all.
    if target.startswith("["):
        closing = target.find("]")
        if closing != -1:
            host = target[1:closing]
            rest = target[closing + 1 :]
            if rest.startswith(":") and rest[1:].isdigit():
                return host, int(rest[1:])
            return host, 443

    # A bare (unbracketed) IPv6 address has multiple colons — only treat a
    # single colon as a "host:port" separator, so "2606:4700::1" isn't
    # mangled into host="2606" port(invalid).
    if target.count(":") == 1:
        host, _, port_str = target.rpartition(":")
        if port_str.isdigit():
            return host, int(port_str)

    return target, 443


async def run_inspect(target: str, timeout: float) -> ModuleResult:
    """Inspect the TLS certificate and negotiated connection for HOST[:PORT]."""
    host, port = _parse_target(target)
    result = ModuleResult(module="tls.inspect", target=f"{host}:{port}")

    try:
        info = await asyncio.to_thread(inspect, host, port, timeout)
    except Exception as exc:
        result.errors.append(str(exc))
        return result

    result.raw_data = info

    days_remaining = info["days_remaining"]
    if days_remaining < 0:
        expiry_severity = Severity.CRITICAL
        expiry_desc = f"Certificate expired {abs(days_remaining)} day(s) ago."
    elif days_remaining < 15:
        expiry_severity = Severity.HIGH
        expiry_desc = f"Certificate expires in {days_remaining} day(s)."
    elif days_remaining < 30:
        expiry_severity = Severity.MEDIUM
        expiry_desc = f"Certificate expires in {days_remaining} day(s)."
    else:
        expiry_severity = Severity.INFO
        expiry_desc = f"Certificate valid for {days_remaining} more day(s)."

    result.findings.append(
        Finding(
            title="Certificate expiration",
            severity=expiry_severity,
            target=host,
            description=expiry_desc,
            evidence=info,
        )
    )
    result.findings.append(
        Finding(
            title="Certificate subject",
            severity=Severity.INFO,
            target=host,
            description=f"{info['subject']} (issued by {info['issuer']})",
        )
    )

    protocol = info["protocol"]
    result.findings.append(
        Finding(
            title="Negotiated TLS protocol",
            severity=Severity.HIGH if protocol in WEAK_PROTOCOLS else Severity.INFO,
            target=host,
            description=f"{protocol}"
            + (" — considered weak/deprecated." if protocol in WEAK_PROTOCOLS else ""),
        )
    )
    result.findings.append(
        Finding(
            title="Negotiated cipher",
            severity=Severity.INFO,
            target=host,
            description=f"{info['cipher_name']} ({info['cipher_bits']} bits)",
        )
    )

    result.assets.append(
        Asset(
            kind="tls_certificate",
            identifier=f"{host}:{port}",
            attributes=info,
            source_module="tls.inspect",
        )
    )
    return result


@tls_app.command("inspect")
def tls_inspect(ctx: typer.Context, target: str) -> None:
    """Inspect the TLS certificate and negotiated connection for HOST[:PORT]."""
    context: NyxorContext = ctx.obj
    result = asyncio.run(run_inspect(target, context.config.tls.timeout_seconds))
    emit_results(context, [result], title="NYXOR TLS Report")
    if not result.ok:
        raise typer.Exit(code=1)


class TlsPlugin:
    metadata = PluginMetadata(
        name="tls",
        description="Certificate inspection, expiration checks, protocol and cipher overview.",
        version="0.1.0",
        author="NYXOR",
        commands=("inspect",),
        category="Scanning",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.add_typer(tls_app, rich_help_panel=self.metadata.category)


PLUGIN = TlsPlugin()
