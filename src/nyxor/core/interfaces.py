"""Contracts the Core relies on. Plugins depend on this module; the Core
depends on nothing here that lives in a plugin.

Keeping the interface surface small and stable is what lets ``No feature
should require modifying the Core`` remain true in practice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from pydantic import BaseModel

if TYPE_CHECKING:
    import typer

    from nyxor.core.context import NyxorContext


class PluginMetadata(BaseModel):
    """Self-description every plugin must provide.

    The Core never hardcodes plugin names — it reads this metadata to build
    help text, the ``nyx plugin list`` output, and command registration.
    """

    name: str
    description: str
    version: str
    author: str
    commands: tuple[str, ...] = ()
    #: Groups this plugin's command(s) under a named panel in `nyx --help`
    #: (via Typer's ``rich_help_panel``) — purely cosmetic, no effect on
    #: behavior. Third-party plugins that don't set one fall back to
    #: "General" rather than being left out of any group.
    category: str = "General"


@runtime_checkable
class Plugin(Protocol):
    """Interface every plugin's ``PLUGIN`` object must satisfy.

    A plugin is discovered via the ``nyxor.plugins`` entry-point group (see
    docs/plugin-development.md) and is asked to register its Typer commands
    against the shared app. It receives a :class:`NyxorContext` so it can
    read configuration, log, and emit events without importing Core
    internals directly.
    """

    metadata: PluginMetadata

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        """Attach this plugin's commands to the root CLI app."""
        ...
