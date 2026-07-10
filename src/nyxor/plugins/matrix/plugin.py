"""The ``matrix`` plugin: ``nyx matrix`` — a Matrix-rain easter egg.

Not a security feature. NYXOR audits real infrastructure passively and
safely; this just animates falling green characters in your terminal
because "let's be hackers, as a joke" was an explicit request. `--duration
0` runs it until Ctrl+C, same as everything else that loops in this tool.
"""

from __future__ import annotations

import random
import time

import typer
from rich.live import Live
from rich.text import Text

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata

_GLYPHS = "アイウエオカキクケコサシスセソタチツテトナニヌネノ0123456789NYXOR#$%&"
_TRAIL_LENGTH = 14
_FPS = 14


def _random_glyph() -> str:
    return random.choice(_GLYPHS)


def _make_frame(width: int, height: int, heads: list[int]) -> Text:
    frame = Text()
    for row in range(height):
        for col in range(width):
            distance = heads[col] - row
            if distance == 0:
                frame.append(_random_glyph(), style="bold white")
            elif 0 < distance <= _TRAIL_LENGTH:
                style = "bold green" if distance <= 3 else "green" if distance <= 8 else "dim green"
                frame.append(_random_glyph(), style=style)
            else:
                frame.append(" ")
        if row < height - 1:
            frame.append("\n")
    return frame


def _matrix(
    ctx: typer.Context,
    duration: float = typer.Option(6.0, "--duration", help="Seconds to run — 0 runs until Ctrl+C."),
) -> None:
    """A Matrix-rain easter egg. Not a scan, not a security feature — just for fun."""
    context: NyxorContext = ctx.obj
    console = context.console

    if not console.is_terminal:
        console.print("[green]Wake up, Neo...[/] (this one only works in a real terminal.)")
        return

    width = max(min(console.size.width, 160), 10)
    height = max(min(console.size.height - 1, 50), 5)
    heads = [random.randint(-height, 0) for _ in range(width)]
    speeds = [random.choice((1, 1, 1, 2)) for _ in range(width)]

    start = time.monotonic()
    try:
        with Live(console=console, refresh_per_second=_FPS, screen=True) as live:
            while duration <= 0 or time.monotonic() - start < duration:
                live.update(_make_frame(width, height, heads))
                for i in range(width):
                    heads[i] += speeds[i]
                    if heads[i] - height > _TRAIL_LENGTH:
                        heads[i] = random.randint(-height, 0)
                time.sleep(1 / _FPS)
    except KeyboardInterrupt:
        pass

    console.print(
        "[bold green]There is no spoon.[/] "
        "[dim](that was `nyx matrix` — for the real thing, try `nyx audit <domain>`.)[/]"
    )


class MatrixPlugin:
    metadata = PluginMetadata(
        name="matrix",
        description="A Matrix-rain easter egg. Not a security feature.",
        version="0.1.0",
        author="NYXOR",
        commands=("matrix",),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("matrix")(_matrix)


PLUGIN = MatrixPlugin()
