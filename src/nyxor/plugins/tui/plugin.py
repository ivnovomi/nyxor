"""The ``tui`` plugin: ``nyx tui`` — the interactive dashboard."""

from __future__ import annotations

import typer

from nyxor.core.banner import boot_sequence
from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata


def _tui(ctx: typer.Context) -> None:
    """Launch the interactive NYXOR dashboard."""
    from nyxor.plugins.tui.app import NyxorApp

    context: NyxorContext = ctx.obj
    # A plain Rich Live animation, run to completion in the current
    # terminal *before* Textual takes the screen over — Textual owns the
    # terminal for the rest of the process once .run() starts, so this
    # has to happen first, not as part of the app itself.
    boot_sequence(context.console, subtitle="Interactive Dashboard")
    NyxorApp().run()


class TuiPlugin:
    metadata = PluginMetadata(
        name="tui",
        description="Interactive terminal dashboard: diagnostics, inventory, and live scans.",
        version="0.1.0",
        author="NYXOR",
        commands=("tui",),
        category="Dashboard & Reports",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("tui", rich_help_panel=self.metadata.category)(_tui)


PLUGIN = TuiPlugin()
