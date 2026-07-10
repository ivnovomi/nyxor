"""The ``inventory`` plugin: ``nyx inventory list|export|clear``."""

from __future__ import annotations

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import ModuleResult
from nyxor.core.output import emit_results
from nyxor.plugins.inventory.store import InventoryStore

inventory_app = typer.Typer(
    name="inventory", help="Store and export discovered assets.", no_args_is_help=True
)


@inventory_app.command("list")
def list_assets(ctx: typer.Context) -> None:
    """List every asset currently in the inventory."""
    context: NyxorContext = ctx.obj
    assets = InventoryStore().list()
    result = ModuleResult(module="inventory", target="local", assets=assets)
    emit_results(context, [result], title="NYXOR Inventory")


@inventory_app.command("export")
def export(ctx: typer.Context) -> None:
    """Export the inventory. Combine with --output to write JSON/Markdown/HTML."""
    list_assets(ctx)


@inventory_app.command("clear")
def clear(
    ctx: typer.Context, yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation.")
) -> None:
    """Delete every asset from the inventory."""
    context: NyxorContext = ctx.obj
    if not yes and not typer.confirm("This will delete all stored inventory assets. Continue?"):
        raise typer.Exit()
    InventoryStore().clear()
    context.console.print("[green]Inventory cleared.[/green]")


class InventoryPlugin:
    metadata = PluginMetadata(
        name="inventory",
        description="Discovered asset storage and export.",
        version="0.1.0",
        author="NYXOR",
        commands=("list", "export", "clear"),
        category="Dashboard & Reports",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        """Register the inventory command group with the CLI application.
        
        Parameters:
        	app (typer.Typer): The CLI application to extend.
        	context (NyxorContext): The shared application context.
        """
        app.add_typer(inventory_app, rich_help_panel=self.metadata.category)


PLUGIN = InventoryPlugin()
