"""The ``script`` plugin: ``nyx script run|lint|new|repl`` — NyxScript automation."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer
from rich.table import Table

from nyxor.core.context import NyxorContext
from nyxor.core.errors import NyxorError
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.scripting import (
    TEMPLATE,
    Interpreter,
    LintIssue,
    ScriptError,
    lint_source,
    parse,
    run_script,
)

script_app = typer.Typer(
    name="script", help="Write, lint, and run NyxScript automation files.", no_args_is_help=True
)

_SEVERITY_STYLE = {"error": "bold red", "warning": "yellow"}


def _print_issues(context: NyxorContext, path: Path, issues: list[LintIssue]) -> None:
    table = Table(title=f"Lint report — {path}", show_header=True, header_style="bold")
    table.add_column("Severity")
    table.add_column("Line", justify="right")
    table.add_column("Message")
    for issue in issues:
        style = _SEVERITY_STYLE[issue.severity]
        table.add_row(f"[{style}]{issue.severity}[/]", str(issue.line), issue.message)
    context.console.print(table)


@script_app.command("lint")
def lint(ctx: typer.Context, path: Path) -> None:
    """Statically check a NyxScript file without running it."""
    context: NyxorContext = ctx.obj
    if not path.is_file():
        raise NyxorError(f"Script not found: {path}")

    issues = lint_source(path.read_text(encoding="utf-8"))
    if not issues:
        context.console.print(f"[bold green]{path}: no issues found.[/bold green]")
        return

    _print_issues(context, path, issues)
    error_count = sum(1 for issue in issues if issue.severity == "error")
    if error_count:
        raise typer.Exit(code=1)


@script_app.command("run")
def run(
    ctx: typer.Context,
    path: Path,
    no_lint: bool = typer.Option(False, "--no-lint", help="Skip the pre-flight lint check."),
    unsafe: bool = typer.Option(
        False, "--unsafe", help="Allow 'python:' blocks and 'pip' statements to actually run."
    ),
) -> None:
    """Lint, then execute, a NyxScript (.nyx) file."""
    context: NyxorContext = ctx.obj
    if not path.is_file():
        raise NyxorError(f"Script not found: {path}")

    source = path.read_text(encoding="utf-8")
    console = context.console

    if not no_lint:
        issues = lint_source(source)
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            _print_issues(context, path, issues)
            console.print(
                "[bold red]Aborting:[/bold red] fix the errors above, or re-run with --no-lint."
            )
            raise typer.Exit(code=1)
        if issues:
            _print_issues(context, path, issues)

    if unsafe:
        console.print(
            "[bold yellow]--unsafe:[/bold yellow] 'python:' and 'pip' statements will execute "
            "for real. Only run scripts you trust."
        )

    def emit(line: str) -> None:
        # markup=False: this is raw script output (e.g. `print [1, 2, 3]`),
        # not our own Rich markup — Rich would otherwise try to parse a
        # literal "[...]" in it as a style tag and silently eat the text.
        style = "#7ee7e1" if line.startswith("→") else "dim" if line.startswith("  ") else ""
        console.print(line, style=style or None, markup=False)

    asyncio.run(run_script(source, context.config, output=emit, base_dir=Path.cwd(), unsafe=unsafe))
    console.print("[bold green]Script finished.[/bold green]")


@script_app.command("new")
def new(
    ctx: typer.Context,
    path: Path,
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
) -> None:
    """Scaffold a starter NyxScript file."""
    context: NyxorContext = ctx.obj
    if path.exists() and not force:
        context.console.print(f"[yellow]{path} already exists.[/yellow] Use --force to overwrite.")
        raise typer.Exit(code=1)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(TEMPLATE, encoding="utf-8")
    context.console.print(f"[green]Wrote starter script to[/green] {path}")


_BLOCK_OPENERS = ("if", "foreach", "while", "func", "try")


@script_app.command("repl")
def repl(
    ctx: typer.Context,
    unsafe: bool = typer.Option(
        False, "--unsafe", help="Allow 'python:' blocks and 'pip' statements to actually run."
    ),
) -> None:
    """An interactive NyxScript prompt — variables and functions persist between lines."""
    context: NyxorContext = ctx.obj
    console = context.console
    console.print(
        "[dim]NyxScript REPL — variables persist across lines. "
        "'exit' or Ctrl+D/Ctrl+C to quit.[/dim]"
    )

    def emit(line: str) -> None:
        # markup=False: this is raw script output (e.g. `print [1, 2, 3]`),
        # not our own Rich markup — Rich would otherwise try to parse a
        # literal "[...]" in it as a style tag and silently eat the text.
        style = "#7ee7e1" if line.startswith("→") else "dim" if line.startswith("  ") else ""
        console.print(line, style=style or None, markup=False)

    interpreter = Interpreter(context.config, output=emit, base_dir=Path.cwd(), unsafe=unsafe)
    buffer: list[str] = []
    depth = 0

    while True:
        try:
            line = input("... " if depth > 0 else "nyx> ")
        except (EOFError, KeyboardInterrupt):
            console.print()
            break

        stripped = line.strip()
        if not buffer and stripped in ("exit", "quit"):
            break
        if not buffer and not stripped:
            continue

        first_word = stripped.split(" ", 1)[0].rstrip(":") if stripped else ""
        if first_word in _BLOCK_OPENERS and stripped.endswith(":"):
            depth += 1
        elif stripped == "end":
            depth -= 1

        buffer.append(line)
        if depth > 0:
            continue

        source = "\n".join(buffer)
        buffer = []
        depth = 0

        try:
            program = parse(source)
        except ScriptError as exc:
            console.print(f"[bold red]{exc}[/bold red]")
            continue

        try:
            asyncio.run(interpreter.run(program))
        except ScriptError as exc:
            console.print(f"[bold red]{exc}[/bold red]")


@script_app.command("lsp")
def lsp(ctx: typer.Context) -> None:
    """Start the NyxScript language server (stdio) for editors like Neovim/VS Code."""
    context: NyxorContext = ctx.obj
    try:
        from nyxor.lsp.server import main as run_lsp
    except ImportError as exc:
        raise NyxorError(
            "The language server needs the 'lsp' extra.",
            hint="Install it with: uv sync --extra lsp",
        ) from exc

    # stdout is reserved for the LSP's JSON-RPC framing once start_io() runs,
    # so any human-readable output has to go to stderr instead.
    context.error_console.print(
        "[dim]NyxScript LSP starting on stdio — point your editor's LSP client at "
        "'nyx script lsp'. Ctrl+C to stop.[/dim]"
    )
    run_lsp()


class ScriptPlugin:
    metadata = PluginMetadata(
        name="script",
        description="A tiny, safe scripting language (NyxScript) for batch-driving modules.",
        version="0.1.0",
        author="NYXOR",
        commands=("run", "lint", "new", "repl", "lsp"),
        category="Automation",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        """Register the script command group with the application.
        
        Parameters:
        	app (typer.Typer): The application to which the command group is added.
        	context (NyxorContext): The host application context.
        """
        app.add_typer(script_app, rich_help_panel=self.metadata.category)


PLUGIN = ScriptPlugin()
