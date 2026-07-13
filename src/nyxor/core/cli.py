"""The NYXOR root CLI.

This module is intentionally thin: it wires global options, loads
configuration, discovers plugins, and hands control to them. It has no
knowledge of what ``nyx network`` or ``nyx dns`` actually do — see
docs/architecture.md.
"""

from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import typer
from rich.console import Console

from nyxor.core.banner import boot_sequence
from nyxor.core.config import load_config
from nyxor.core.context import NyxorContext, OutputOptions
from nyxor.core.errors import NyxorError
from nyxor.core.events import EventBus
from nyxor.core.logging import configure_logging, get_logger
from nyxor.core.plugins import discover_plugins

app = typer.Typer(
    name="nyxor",
    help="NYXOR — a modular security assessment and infrastructure auditing toolkit.",
    no_args_is_help=False,
    add_completion=True,
    pretty_exceptions_enable=False,
)

logger = get_logger(__name__)


#: `nyx --help` groups commands into a Rich panel per
#: ``PluginMetadata.category`` (see each plugin's ``register()``), and
#: panels appear in the order their first command was registered — so this
#: is the one place that decides the *category* order shown to a first-time
#: user. A category missing here (a third-party plugin's own name) just
#: sorts after all of these, rather than erroring.
_CATEGORY_PRIORITY = (
    "Scanning",
    "Continuous & History",
    "AI (local model)",
    "Host Security",
    "Automation",
    "Dashboard & Reports",
    "Setup & Config",
    "API",
    "Fun",
)


def _category_sort_key(category: str) -> int:
    """Where ``category`` falls in :data:`_CATEGORY_PRIORITY` — unlisted

    categories (a third-party plugin's own name) sort after all of these.
    """
    if category in _CATEGORY_PRIORITY:
        return _CATEGORY_PRIORITY.index(category)
    return len(_CATEGORY_PRIORITY)


def _register_plugins() -> None:
    """Attach every discovered plugin's commands to the root app.

    Runs once at import time, using a bootstrap context built from defaults
    only (no profile/CLI overrides yet — those aren't known until the root
    callback below parses argv). Commands should read the *runtime* context
    from ``typer.Context.obj``, populated by :func:`main_callback`.
    """
    bootstrap_config = load_config()
    bootstrap = NyxorContext(config=bootstrap_config)
    discovered_plugins = discover_plugins(disabled=bootstrap_config.plugins.disabled)
    discovered_plugins.sort(key=lambda d: _category_sort_key(d.plugin.metadata.category))
    for discovered in discovered_plugins:
        try:
            discovered.plugin.register(app, bootstrap)
        except Exception as exc:
            logger.warning(
                "plugin.register_failed", plugin=discovered.entry_point.name, error=str(exc)
            )


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose (debug) logging."),
    json_output: bool = typer.Option(False, "--json", help="Emit machine-readable JSON output."),
    yaml_output: bool = typer.Option(False, "--yaml", help="Emit YAML output."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write output to this file instead of stdout."
    ),
    profile: str | None = typer.Option(
        None, "--profile", "-p", help="Configuration profile to apply."
    ),
) -> None:
    """Global options shared by every command."""
    if json_output and yaml_output:
        raise typer.BadParameter("--json and --yaml are mutually exclusive.")

    config = load_config(profile=profile)
    configure_logging(
        level="DEBUG" if verbose else config.general.log_level, json_output=json_output
    )

    output_format = "json" if json_output else "yaml" if yaml_output else "table"
    ctx.obj = NyxorContext(
        config=config,
        events=EventBus(),
        output=OutputOptions(format=output_format, output_path=output, verbose=verbose),
    )

    if ctx.invoked_subcommand is None:
        boot_sequence(ctx.obj.console)
        ctx.obj.console.print(ctx.get_help(), markup=False, highlight=False)
        raise typer.Exit()


def _print_error(exc: Exception, *, verbose: bool) -> None:
    console = Console(stderr=True)
    if isinstance(exc, NyxorError):
        console.print(f"[bold red]Error:[/bold red] {exc.message}")
        if exc.hint:
            console.print(f"[dim]Hint: {exc.hint}[/dim]")
    else:
        console.print(f"[bold red]Unexpected error:[/bold red] {exc}")
    if verbose:
        console.print_exception()


_register_plugins()


def _ensure_utf8_streams() -> None:
    """Force UTF-8 stdio so the banner's box-drawing glyphs render on Windows,
    where the default console codepage otherwise can't encode them."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding="utf-8")


def main() -> None:
    """Entry point for the ``nyxor`` and ``nyx`` executables."""
    _ensure_utf8_streams()
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    try:
        app()
    except NyxorError as exc:
        _print_error(exc, verbose=verbose)
        raise SystemExit(1) from None
    except typer.Exit:
        raise
    except Exception as exc:  # last-resort safety net: NYXOR should never crash raw
        _print_error(exc, verbose=verbose)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
