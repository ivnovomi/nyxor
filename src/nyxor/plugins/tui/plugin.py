"""The ``tui`` plugin: ``nyx tui`` — the interactive dashboard."""

from __future__ import annotations

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata


def _tui(ctx: typer.Context) -> None:
    """Launch the interactive NYXOR dashboard."""
    from nyxor.plugins.tui.app import NyxorApp

    NyxorApp().run()


class TuiPlugin:
    metadata = PluginMetadata(
        name="tui",
        description="Interactive terminal dashboard: diagnostics, inventory, and live scans.",
        version="0.1.0",
        author="NYXOR",
        commands=("tui",),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("tui")(_tui)


PLUGIN = TuiPlugin()
