from __future__ import annotations

import pytest
from rich.console import Console

from nyxor.core.scripting.ui import ScriptUI


@pytest.mark.asyncio
async def test_table_preserves_literal_brackets_in_cells() -> None:
    console = Console(record=True, width=120)
    ui = ScriptUI(console=console)

    await ui.table([["title"], [["Banner: [admin] [bold red]FAKE[/bold red]"]]])

    text = console.export_text()
    assert "[admin]" in text
    assert "FAKE" in text


@pytest.mark.asyncio
async def test_banner_preserves_literal_brackets() -> None:
    console = Console(record=True, width=120)
    ui = ScriptUI(console=console)

    await ui.banner(["Section [bold red]FAKE[/bold red]"])

    assert "FAKE" in console.export_text()


@pytest.mark.asyncio
async def test_status_preserves_literal_brackets() -> None:
    console = Console(record=True, width=120)
    ui = ScriptUI(console=console)

    await ui.status(["Scanning [bold red]FAKE[/bold red]..."])

    assert "FAKE" in console.export_text()
