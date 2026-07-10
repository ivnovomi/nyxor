"""The ``config`` plugin: ``nyx config show|path|init``."""

from __future__ import annotations

import json

import tomli_w
import typer

from nyxor.core.config import DEFAULT_CONFIG, find_project_config, user_config_path
from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata

config_app = typer.Typer(
    name="config", help="Inspect and manage NYXOR configuration.", no_args_is_help=True
)


@config_app.command("show")
def show(ctx: typer.Context) -> None:
    """Print the fully resolved, merged configuration."""
    context: NyxorContext = ctx.obj
    payload = context.config.model_dump(mode="json")
    if context.output.format == "yaml":
        import yaml

        context.console.print(yaml.safe_dump(payload, sort_keys=False))
    else:
        context.console.print_json(json.dumps(payload))


@config_app.command("path")
def path(ctx: typer.Context) -> None:
    """Show where NYXOR looks for configuration files."""
    context: NyxorContext = ctx.obj
    user_path = user_config_path()
    project_path = find_project_config()
    context.console.print(
        f"User config:    {user_path} {'(exists)' if user_path.is_file() else '(not found)'}"
    )
    context.console.print(
        f"Project config: {project_path if project_path else '(not found — looked for nyxor.toml)'}"
    )


@config_app.command("init")
def init(
    ctx: typer.Context,
    project: bool = typer.Option(
        False, "--project", help="Write to ./nyxor.toml instead of the user config."
    ),
    force: bool = typer.Option(False, "--force", help="Overwrite an existing file."),
) -> None:
    """Write a default configuration file."""
    context: NyxorContext = ctx.obj
    target = user_config_path()
    if project:
        from pathlib import Path

        target = Path.cwd() / "nyxor.toml"

    if target.exists() and not force:
        context.console.print(
            f"[yellow]{target} already exists.[/yellow] Use --force to overwrite."
        )
        raise typer.Exit(code=1)

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(tomli_w.dumps(DEFAULT_CONFIG).encode("utf-8"))
    context.console.print(f"[green]Wrote default configuration to[/green] {target}")


class ConfigPlugin:
    metadata = PluginMetadata(
        name="config",
        description="Profiles and multi-environment configuration management.",
        version="0.1.0",
        author="NYXOR",
        commands=("show", "path", "init"),
        category="Setup & Config",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        """Register the configuration command group with the application.
        
        Parameters:
        	app (typer.Typer): The Typer application to extend.
        	context (NyxorContext): The active NYXOR application context.
        """
        app.add_typer(config_app, rich_help_panel=self.metadata.category)


PLUGIN = ConfigPlugin()
