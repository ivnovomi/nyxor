"""The ``report`` plugin: ``nyx report convert`` — re-render a saved JSON
report (produced by any module via ``--output foo.json``) into another
format."""

from __future__ import annotations

import json
from pathlib import Path

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.reporting import ReportDocument, get_writer

report_app = typer.Typer(
    name="report", help="Generate reports from structured scan output.", no_args_is_help=True
)


@report_app.command("convert")
def convert(
    ctx: typer.Context,
    input_path: Path = typer.Argument(
        ..., help="A JSON report previously written with --output foo.json"
    ),
    to: str = typer.Option("html", "--to", help="Target format: json, markdown, or html."),
    output: Path = typer.Option(..., "--output", "-o", help="Where to write the converted report."),
) -> None:
    """Convert a saved JSON report into another format."""
    context: NyxorContext = ctx.obj
    document = ReportDocument.model_validate(json.loads(input_path.read_text(encoding="utf-8")))
    writer = get_writer(to)
    writer.write(document, output)
    context.console.print(f"[green]Wrote {to} report to[/green] {output}")


class ReportPlugin:
    metadata = PluginMetadata(
        name="report",
        description="Generate JSON, Markdown, and HTML reports from structured scan output.",
        version="0.1.0",
        author="NYXOR",
        commands=("convert",),
        category="Dashboard & Reports",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.add_typer(report_app, rich_help_panel=self.metadata.category)


PLUGIN = ReportPlugin()
