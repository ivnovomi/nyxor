"""The ``system`` plugin: ``nyx doctor``."""

from __future__ import annotations

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.output import emit_results
from nyxor.plugins.system.doctor import run_diagnostics


def _doctor(ctx: typer.Context) -> None:
    """Run environment diagnostics and dependency checks."""
    context: NyxorContext = ctx.obj
    result = run_diagnostics()
    emit_results(context, [result], title="NYXOR Doctor Report")


class SystemPlugin:
    metadata = PluginMetadata(
        name="system",
        description="Environment diagnostics and dependency validation.",
        version="0.1.0",
        author="NYXOR",
        commands=("doctor",),
        category="Setup & Config",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("doctor", rich_help_panel=self.metadata.category)(_doctor)


PLUGIN = SystemPlugin()
