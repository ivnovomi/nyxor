"""``ui.*`` — the interactive half of "bring GUIs and all that" for NyxScript.

Not a bundled GUI toolkit (too heavy for a security CLI's dependency tree) —
real terminal interactivity instead: confirmations, prompts, choice menus,
tables, and banners, built on Rich (already a dependency everywhere else in
NYXOR). The same implementation works from both front ends:

- ``nyx script run`` — the CLI owns the terminal outright, so prompts just
  block normally (off the event loop, via ``asyncio.to_thread``).
- ``nyx tui`` — Textual owns the terminal instead, so a blocking prompt
  would corrupt the screen. `ScriptUI` is handed the running `App` and
  wraps each prompt in ``App.suspend()``, which hands the real terminal
  back for exactly as long as the prompt needs it, then restores the TUI.

Either way, the NyxScript author just writes ``ui.confirm("Proceed?")`` and
never has to know which front end is running it.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from rich.console import Console
from rich.markup import escape as escape_markup
from rich.prompt import Confirm, Prompt
from rich.table import Table

if TYPE_CHECKING:
    from textual.app import App


class ScriptUI:
    """Interactive + presentational helpers exposed to NyxScript as ``ui.*``."""

    def __init__(self, console: Console | None = None, app: App[Any] | None = None) -> None:
        self.console = console or Console()
        self._app = app

    async def _blocking(self, fn: Any, *args: Any, **kwargs: Any) -> Any:
        if self._app is not None:
            with self._app.suspend():
                return fn(*args, **kwargs)
        return await asyncio.to_thread(fn, *args, **kwargs)

    async def confirm(self, args: list[Any]) -> bool:
        if len(args) != 1:
            raise TypeError("ui.confirm() expects 1 argument (question)")
        return bool(await self._blocking(Confirm.ask, str(args[0]), console=self.console))

    async def input(self, args: list[Any]) -> str:
        if len(args) != 1:
            raise TypeError("ui.input() expects 1 argument (prompt)")
        return str(await self._blocking(Prompt.ask, str(args[0]), console=self.console))

    async def select(self, args: list[Any]) -> str:
        if len(args) != 2:
            raise TypeError("ui.select() expects 2 arguments (prompt, options)")
        prompt, options = args
        if not isinstance(options, list) or not options:
            raise TypeError("ui.select()'s second argument must be a non-empty list")
        choices = [str(o) for o in options]
        return str(
            await self._blocking(Prompt.ask, str(prompt), choices=choices, console=self.console)
        )

    async def table(self, args: list[Any]) -> None:
        """Display tabular data with headers and rows.
        
        Parameters:
            args (list[Any]): A two-item list containing the header list and row list.
        """
        if len(args) != 2:
            raise TypeError("ui.table() expects 2 arguments (headers, rows)")
        headers, rows = args
        if not isinstance(headers, list) or not isinstance(rows, list):
            raise TypeError("ui.table()'s arguments must both be lists")
        table = Table(show_header=True, header_style="bold")
        for header in headers:
            table.add_column(escape_markup(str(header)))
        for row in rows:
            if not isinstance(row, list):
                raise TypeError("ui.table()'s rows must each be a list")
            # A script commonly feeds scan-result data (a finding's title,
            # a banner, a header value) through here — escape each cell so a
            # literal "[" in that data can't be parsed as a Rich style tag.
            table.add_row(*(escape_markup(str(cell)) for cell in row))
        self.console.print(table)

    async def banner(self, args: list[Any]) -> None:
        """
        Display a styled rule containing the specified banner text.
        
        Parameters:
        	args (list[Any]): A single-item list containing the banner text.
        """
        if len(args) != 1:
            raise TypeError("ui.banner() expects 1 argument (text)")
        self.console.rule(f"[bold]{escape_markup(str(args[0]))}[/bold]")

    async def status(self, args: list[Any]) -> None:
        """
        Display a dim status message.
        
        Parameters:
        	args (list[Any]): A single-item list containing the message to display.
        """
        if len(args) != 1:
            raise TypeError("ui.status() expects 1 argument (message)")
        self.console.print(f"[dim]…[/dim] {escape_markup(str(args[0]))}")


#: Method names reachable as ``ui.<name>(...)`` from NyxScript.
UI_FUNCTIONS = frozenset({"confirm", "input", "select", "table", "banner", "status"})
