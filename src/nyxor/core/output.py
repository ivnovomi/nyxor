"""Shared rendering of :class:`ModuleResult` objects to the terminal or a file.

Every plugin command ends by calling :func:`emit_results` instead of
hand-rolling its own printing — that's what makes ``--json`` / ``--yaml`` /
``--output`` behave consistently across ``nyx network``, ``nyx dns``,
``nyx tls``, etc.
"""

from __future__ import annotations

import json

import yaml
from rich.console import Console
from rich.markup import escape as escape_markup
from rich.table import Table

from nyxor.core.context import NyxorContext
from nyxor.core.models import ModuleResult, Severity
from nyxor.core.reporting import ReportDocument, get_writer

SEVERITY_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "green",
    Severity.INFO: "dim",
}

_SUFFIX_FORMATS = {
    ".json": "json",
    ".md": "markdown",
    ".markdown": "markdown",
    ".html": "html",
    ".htm": "html",
}


def emit_results(context: NyxorContext, results: list[ModuleResult], *, title: str) -> None:
    """Render module results per the current ``--json``/``--yaml``/``--output`` options."""
    document = ReportDocument(title=title, profile=context.config.active_profile, results=results)

    if context.output.output_path is not None:
        fmt = _SUFFIX_FORMATS.get(context.output.output_path.suffix.lower(), "json")
        writer = get_writer(fmt)
        writer.write(document, context.output.output_path)
        context.console.print(f"[green]Report written to[/green] {context.output.output_path}")
        return

    if context.output.format == "json":
        context.console.print_json(document.model_dump_json())
    elif context.output.format == "yaml":
        context.console.print(
            yaml.safe_dump(json.loads(document.model_dump_json()), sort_keys=False)
        )
    else:
        _print_table(context.console, results)


def _print_table(console: Console, results: list[ModuleResult]) -> None:
    for result in results:
        console.rule(f"{result.module} — {result.target}")
        for err in result.errors:
            console.print(f"[bold red]Error:[/bold red] {err}")

        if not result.findings:
            console.print("[dim]No findings.[/dim]")
            continue

        table = Table(show_header=True, header_style="bold")
        table.add_column("Severity")
        table.add_column("Title")
        table.add_column("Description")
        for finding in result.findings:
            style = SEVERITY_STYLE[finding.severity]
            # title/description come from the scanned target (a TCP banner,
            # a DNS TXT record, an HTTP header, ...) — escape them so a
            # literal "[" in that data can't be parsed as a Rich style tag
            # and silently swallowed (or worse, used to inject fake styling).
            table.add_row(
                f"[{style}]{finding.severity.value}[/]",
                escape_markup(finding.title),
                escape_markup(finding.description),
            )
        console.print(table)
