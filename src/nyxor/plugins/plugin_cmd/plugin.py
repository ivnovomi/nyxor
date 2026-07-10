"""The ``plugin`` plugin: ``nyx plugin list|info`` — introspection over the
plugin system itself."""

from __future__ import annotations

import typer
from rich.table import Table

from nyxor.core.context import NyxorContext
from nyxor.core.errors import PluginNotFoundError
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.plugins import discover_plugins

plugin_app = typer.Typer(
    name="plugin", help="List and inspect installed plugins.", no_args_is_help=True
)


@plugin_app.command("list")
def list_plugins(ctx: typer.Context) -> None:
    """List every plugin discovered via the `nyxor.plugins` entry-point group."""
    context: NyxorContext = ctx.obj
    discovered = discover_plugins(disabled=context.config.plugins.disabled)

    if context.output.format == "json":
        payload = [d.plugin.metadata.model_dump() for d in discovered]
        context.console.print_json(data=payload)
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("Name")
    table.add_column("Version")
    table.add_column("Description")
    table.add_column("Author")
    table.add_column("Commands")
    for d in discovered:
        meta = d.plugin.metadata
        table.add_row(
            meta.name, meta.version, meta.description, meta.author, ", ".join(meta.commands)
        )
    context.console.print(table)


@plugin_app.command("info")
def plugin_info(ctx: typer.Context, name: str) -> None:
    """Show metadata for a single plugin."""
    context: NyxorContext = ctx.obj
    discovered = discover_plugins(disabled=context.config.plugins.disabled)
    match = next((d for d in discovered if d.plugin.metadata.name == name), None)
    if match is None:
        raise PluginNotFoundError(f"No plugin named {name!r} is installed.")

    meta = match.plugin.metadata
    if context.output.format == "json":
        context.console.print_json(data=meta.model_dump())
        return

    context.console.print(f"[bold]{meta.name}[/bold] v{meta.version}")
    context.console.print(meta.description)
    context.console.print(f"Author: {meta.author}")
    context.console.print(f"Commands: {', '.join(meta.commands) or '(none)'}")


class PluginManagementPlugin:
    metadata = PluginMetadata(
        name="plugin",
        description="Plugin discovery and introspection.",
        version="0.1.0",
        author="NYXOR",
        commands=("list", "info"),
        category="Setup & Config",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.add_typer(plugin_app, rich_help_panel=self.metadata.category)


PLUGIN = PluginManagementPlugin()
