"""The ``mcp`` plugin: ``nyx mcp`` — expose NYXOR as an MCP server over stdio.

Same lazy-import + stdio-safety pattern as ``nyx script lsp``: the ``mcp``
extra is optional, and once the stdio transport is running, stdout is
reserved for JSON-RPC framing, so any human-readable output goes to
``context.error_console``.
"""

from __future__ import annotations

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.errors import NyxorError
from nyxor.core.interfaces import PluginMetadata


def _mcp(ctx: typer.Context) -> None:
    """Start the NYXOR MCP server (stdio) for Claude and other MCP clients."""
    context: NyxorContext = ctx.obj
    try:
        from nyxor.mcp.server import main as run_mcp
    except ImportError as exc:
        raise NyxorError(
            "The MCP server needs the 'mcp' extra.",
            hint="Install it with: uv sync --extra mcp",
        ) from exc

    context.error_console.print(
        "[dim]NYXOR MCP server starting on stdio — point your MCP client at "
        "'nyx mcp'. Ctrl+C to stop.[/dim]"
    )
    run_mcp()


class McpPlugin:
    metadata = PluginMetadata(
        name="mcp",
        description="Expose NYXOR's audit modules and NyxScript as an MCP server.",
        version="0.1.0",
        author="NYXOR",
        commands=("mcp",),
        category="Automation",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        """Register the MCP server command with the Typer application.
        
        Parameters:
        	app (typer.Typer): CLI application to which the command is added.
        	context (NyxorContext): Shared NYXOR execution context passed to the command.
        """
        app.command("mcp", rich_help_panel=self.metadata.category)(_mcp)


PLUGIN = McpPlugin()
