"""The ``http`` plugin: ``nyx http inspect``."""

from __future__ import annotations

import asyncio

import typer

from nyxor.core.config import HttpConfig
from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.core.output import emit_results
from nyxor.plugins.http_.inspector import inspect

http_app = typer.Typer(
    name="http",
    help="Response headers, redirects, cookies, compression, security headers.",
    no_args_is_help=True,
)


async def run_inspect(url: str, config: HttpConfig) -> ModuleResult:
    """Inspect the HTTP response for a URL and return a ModuleResult."""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    result = ModuleResult(module="http.inspect", target=url)
    try:
        info = await inspect(
            url, config.timeout_seconds, config.follow_redirects, config.max_redirects
        )
    except Exception as exc:
        result.errors.append(str(exc))
        return result

    result.raw_data = info

    result.findings.append(
        Finding(
            title="Response status",
            severity=Severity.INFO,
            target=url,
            description=f"{info['status_code']} from {info['final_url']}",
        )
    )

    if info["redirect_chain"]:
        hops = (
            " -> ".join(hop["url"] for hop in info["redirect_chain"]) + f" -> {info['final_url']}"
        )
        result.findings.append(
            Finding(
                title="Redirect chain",
                severity=Severity.INFO,
                target=url,
                description=hops,
                evidence={"hops": info["redirect_chain"]},
            )
        )

    if info["content_encoding"]:
        result.findings.append(
            Finding(
                title="Compression",
                severity=Severity.INFO,
                target=url,
                description=f"Content-Encoding: {info['content_encoding']}",
            )
        )

    for cookie in info["cookies"]:
        issues = []
        if not cookie["secure"]:
            issues.append("missing Secure")
        if not cookie["http_only"]:
            issues.append("missing HttpOnly")
        if not cookie["same_site"]:
            issues.append("missing SameSite")
        result.findings.append(
            Finding(
                title=f"Cookie: {cookie['name']}",
                severity=Severity.MEDIUM if issues else Severity.INFO,
                target=url,
                description=", ".join(issues)
                if issues
                else "Secure, HttpOnly, and SameSite are all set.",
                evidence=cookie,
            )
        )

    if info["missing_security_headers"]:
        result.findings.append(
            Finding(
                title="Missing security headers",
                severity=Severity.MEDIUM,
                target=url,
                description=", ".join(info["missing_security_headers"]),
                evidence={"missing": info["missing_security_headers"]},
            )
        )
    else:
        result.findings.append(
            Finding(
                title="Security headers",
                severity=Severity.INFO,
                target=url,
                description="All checked security headers are present.",
            )
        )

    return result


@http_app.command("inspect")
def http_inspect(ctx: typer.Context, url: str) -> None:
    """Inspect the HTTP response for a URL."""
    context: NyxorContext = ctx.obj
    result = asyncio.run(run_inspect(url, context.config.http))
    emit_results(context, [result], title="NYXOR HTTP Report")
    if not result.ok:
        raise typer.Exit(code=1)


class HttpPlugin:
    metadata = PluginMetadata(
        name="http",
        description="HTTP response headers, redirects, cookies, compression, and security headers.",
        version="0.1.0",
        author="NYXOR",
        commands=("inspect",),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.add_typer(http_app)


PLUGIN = HttpPlugin()
