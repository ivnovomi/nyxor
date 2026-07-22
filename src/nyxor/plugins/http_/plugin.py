"""The ``http`` plugin: ``nyx http inspect``."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from nyxor.core.config import HttpConfig
from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.core.output import emit_results
from nyxor.plugins.http_.inspector import ValidateUrl, inspect
from nyxor.plugins.http_.screenshot import (
    ScreenshotError,
    capture_screenshot,
    missing_screenshot_extra,
)

http_app = typer.Typer(
    name="http",
    help="Response headers, redirects, cookies, compression, security headers.",
    no_args_is_help=True,
)


async def run_inspect(
    url: str, config: HttpConfig, *, validate_url: ValidateUrl | None = None
) -> ModuleResult:
    """Inspect the HTTP response for a URL and return a ModuleResult.

    ``validate_url``, if given, is checked against the initial URL and every
    redirect hop (see :func:`nyxor.plugins.http_.inspector.inspect`) — used
    by the REST API to enforce its SSRF guard past redirects, not needed by
    the CLI/TUI/NyxScript, which are allowed to target internal hosts.
    """
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"

    result = ModuleResult(module="http.inspect", target=url)
    try:
        info = await inspect(
            url,
            config.timeout_seconds,
            config.follow_redirects,
            config.max_redirects,
            validate_url=validate_url,
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

    if info["technologies"]:
        result.findings.append(
            Finding(
                title="Detected technology",
                severity=Severity.INFO,
                target=url,
                description=", ".join(info["technologies"]),
                evidence={"technologies": info["technologies"]},
                tags=("fingerprint",),
            )
        )

    if info["cdn_waf"]:
        result.findings.append(
            Finding(
                title="CDN / WAF",
                severity=Severity.INFO,
                target=url,
                description=", ".join(info["cdn_waf"]),
                evidence={"cdn_waf": info["cdn_waf"]},
                tags=("fingerprint",),
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


async def _screenshot_and_preview(context: NyxorContext, url: str, output_path: Path) -> None:
    await capture_screenshot(url, output_path)
    context.console.print(f"[green]Screenshot saved:[/green] {output_path}")

    if not context.console.is_terminal:
        return
    try:
        # See screenshot.py's module docstring: 'screenshot' is a
        # deliberately optional, CI-excluded extra.
        from textual_image.renderable import Image  # type: ignore[import-not-found]
    except ImportError as exc:
        raise missing_screenshot_extra(exc) from exc
    context.console.print(Image(output_path, width="auto"))


@http_app.command("inspect")
def http_inspect(
    ctx: typer.Context,
    url: str,
    screenshot: Path | None = typer.Option(
        None,
        "--screenshot",
        help="Save a full-page PNG screenshot to this path (requires --unsafe).",
    ),
    unsafe: bool = typer.Option(
        False,
        "--unsafe",
        help="Allow --screenshot to render the page in a real headless browser.",
    ),
) -> None:
    """Inspect the HTTP response for a URL."""
    context: NyxorContext = ctx.obj
    result = asyncio.run(run_inspect(url, context.config.http))
    emit_results(context, [result], title="NYXOR HTTP Report")

    if screenshot is not None:
        if not unsafe:
            context.console.print(
                "[red]--screenshot requires --unsafe.[/red] Unlike the rest of this "
                "command, a screenshot renders the page in a real browser — it executes "
                "the page's own JavaScript and loads whatever it references, not just "
                "the bounded request this command otherwise makes."
            )
            raise typer.Exit(code=1)
        # raw_data is only empty when run_inspect() itself already failed (e.g. a
        # connection error) — in that case there's no resolved final_url to fall
        # back on, so normalize the scheme the same way run_inspect() does and let
        # the screenshot attempt fail on its own terms instead of silently skipping.
        target_url = (result.raw_data or {}).get("final_url", url)
        if not target_url.startswith(("http://", "https://")):
            target_url = f"https://{target_url}"
        try:
            asyncio.run(_screenshot_and_preview(context, target_url, screenshot))
        except ScreenshotError as exc:
            context.console.print(f"[red]{exc}[/red]")
            raise typer.Exit(code=1) from None

    if not result.ok:
        raise typer.Exit(code=1)


class HttpPlugin:
    metadata = PluginMetadata(
        name="http",
        description="HTTP response headers, redirects, cookies, compression, and security headers.",
        version="0.1.0",
        author="NYXOR",
        commands=("inspect",),
        category="Scanning",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.add_typer(http_app, rich_help_panel=self.metadata.category)


PLUGIN = HttpPlugin()
