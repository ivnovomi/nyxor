"""The ``serve`` plugin: ``nyx serve`` — run NYXOR's REST API."""

from __future__ import annotations

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.errors import NyxorError
from nyxor.core.interfaces import PluginMetadata


def _serve(
    ctx: typer.Context,
    host: str = typer.Option("127.0.0.1", "--host", help="Interface to bind to."),
    port: int = typer.Option(8842, "--port", help="Port to listen on."),
) -> None:
    """Run NYXOR's REST API — a fourth front-end over the same scan modules."""
    context: NyxorContext = ctx.obj
    try:
        import uvicorn

        from nyxor.api.app import create_app
    except ImportError as exc:
        raise NyxorError(
            "The REST API needs the 'api' extra.",
            hint="Install it with: uv sync --extra api",
        ) from exc

    context.console.print(
        f"[bold #7ee7e1]NYXOR API[/] listening on http://{host}:{port} "
        f"(interactive docs at /docs). Ctrl+C to stop."
    )
    uvicorn.run(create_app(context.config), host=host, port=port, log_level="warning")


class ServePlugin:
    metadata = PluginMetadata(
        name="serve",
        description="Run NYXOR's REST API — a fourth front-end over the same scan modules.",
        version="0.1.0",
        author="NYXOR",
        commands=("serve",),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("serve")(_serve)


PLUGIN = ServePlugin()
