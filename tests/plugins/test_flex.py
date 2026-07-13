from __future__ import annotations

from rich.console import Console
from rich.panel import Panel

from nyxor.core.config import load_config
from nyxor.core.context import NyxorContext
from nyxor.plugins.flex.plugin import _stats_panel


def test_stats_panel_reflects_real_plugin_and_builtin_counts() -> None:
    context = NyxorContext(config=load_config())
    panel = _stats_panel(context)

    assert isinstance(panel, Panel)
    console = Console(record=True, width=200)
    console.print(panel)
    text = console.export_text()
    assert "plugins" in text
    assert "scan modules" in text
    assert "NyxScript builtins" in text
