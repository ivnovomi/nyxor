"""The ``update`` plugin: ``nyx update`` — checks for a newer release.

NYXOR never updates itself in-place (that would mean silently rewriting the
user's environment); it only reports whether a newer version is available
and how to install it via ``uv``.
"""

from __future__ import annotations

import typer

from nyxor import __version__
from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata

PYPI_URL = "https://pypi.org/pypi/nyxor/json"


def _update(ctx: typer.Context) -> None:
    """Check whether a newer version of NYXOR is available."""
    context: NyxorContext = ctx.obj
    logger = context.get_logger(__name__)

    latest: str | None = None
    try:
        import httpx

        response = httpx.get(PYPI_URL, timeout=5.0)
        response.raise_for_status()
        latest = response.json()["info"]["version"]
    except Exception as exc:  # network unavailable, package not on PyPI yet, etc.
        logger.debug("update.check_failed", error=str(exc))

    context.console.print(f"Installed version: [bold]{__version__}[/bold]")
    if latest is None:
        context.console.print("[yellow]Could not reach PyPI to check for updates.[/yellow]")
        return

    if latest != __version__:
        context.console.print(f"[green]A newer version is available: {latest}[/green]")
        context.console.print("Run: [bold]uv tool upgrade nyxor[/bold]")
    else:
        context.console.print("[green]You are on the latest version.[/green]")


class UpdatePlugin:
    metadata = PluginMetadata(
        name="update",
        description="Check for newer NYXOR releases.",
        version="0.1.0",
        author="NYXOR",
        commands=("update",),
        category="Setup & Config",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("update", rich_help_panel=self.metadata.category)(_update)


PLUGIN = UpdatePlugin()
