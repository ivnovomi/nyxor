"""The ``flex`` plugin: ``nyx flex`` — a pure spectacle.

Not a security feature, not trying to be one. A glitch-reveal of the
NYXOR wordmark in a moving RGB rainbow, landing on real numbers about the
toolkit (plugin count, scan modules, NyxScript builtins) pulled live from
the running process — nothing here is hardcoded set dressing.
"""

from __future__ import annotations

import colorsys
import random
import time

import typer
from rich.align import Align
from rich.console import Group
from rich.live import Live
from rich.panel import Panel
from rich.text import Text

from nyxor import __version__
from nyxor.core.banner import LOGO
from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.plugins import discover_plugins
from nyxor.core.scripting.builtins import BUILTIN_FUNCTIONS, HIGHER_ORDER_FUNCTIONS
from nyxor.core.scripting.stdlib import MODULE_RUNNERS

_GLITCH_CHARS = "█▓▒░╬╫╪┼#%&$@01XYZ"
_REVEAL_FRAMES = 26
_FPS = 20


def _hue_to_hex(hue: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, 0.85, 1.0)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def _glitch_char() -> str:
    return random.choice(_GLITCH_CHARS)


def _lock_frame_for(col: int, width: int) -> int:
    # Left-to-right reveal wave, with a little jitter so it doesn't look
    # mechanically perfect.
    base = (col / max(width - 1, 1)) * (_REVEAL_FRAMES * 0.6)
    return int(base + random.uniform(0, _REVEAL_FRAMES * 0.4))


def _render_frame(
    lines: list[str], lock_frames: list[list[int]], frame: int, hue_offset: float
) -> Text:
    text = Text()
    width = max((len(line) for line in lines), default=1)
    for row, line in enumerate(lines):
        for col in range(width):
            ch = line[col] if col < len(line) else " "
            if ch == " ":
                text.append(" ")
                continue
            hue = (col / max(width - 1, 1)) + hue_offset
            color = _hue_to_hex(hue)
            if frame >= lock_frames[row][col]:
                text.append(ch, style=f"bold {color}")
            else:
                text.append(_glitch_char(), style=f"dim {color}")
        text.append("\n")
    return text


def _stats_panel(context: NyxorContext) -> Panel:
    plugins = discover_plugins(disabled=context.config.plugins.disabled)
    total_commands = sum(len(p.plugin.metadata.commands) for p in plugins)
    builtin_count = len(BUILTIN_FUNCTIONS) + len(HIGHER_ORDER_FUNCTIONS)

    stats = Text(justify="center")
    stats.append(f"v{__version__}", style="bold #7ee7e1")
    stats.append("  ·  ", style="dim")
    stats.append(f"{len(plugins)} plugins", style="bold #b98cff")
    stats.append("  ·  ", style="dim")
    stats.append(f"{total_commands} commands", style="bold #ff9f43")
    stats.append("  ·  ", style="dim")
    stats.append(f"{len(MODULE_RUNNERS)} scan modules", style="bold #2ecc71")
    stats.append("  ·  ", style="dim")
    stats.append(f"{builtin_count} NyxScript builtins", style="bold #ff6b9d")

    return Panel(Align.center(stats), border_style="#7ee7e1", padding=(0, 2))


def _flex(
    ctx: typer.Context,
    duration: float = typer.Option(
        5.0, "--duration", help="Seconds to hold the final frame before exiting."
    ),
) -> None:
    """A pure spectacle — a glitch-reveal RGB wordmark. Not a security feature."""
    context: NyxorContext = ctx.obj
    console = context.console

    if not console.is_terminal:
        console.print("[bold #b98cff]NYXOR[/] — run this one in a real terminal for the show.")
        return

    lines = LOGO.strip("\n").splitlines()
    width = max(len(line) for line in lines)
    lock_frames = [[_lock_frame_for(col, width) for col in range(width)] for _ in lines]
    max_lock = max(max(row) for row in lock_frames)

    try:
        with Live(console=console, refresh_per_second=_FPS, screen=True) as live:
            frame = 0
            hue_offset = 0.0
            while frame <= max_lock + 4:
                art = _render_frame(lines, lock_frames, frame, hue_offset)
                live.update(Align.center(art, vertical="middle"))
                frame += 1
                hue_offset += 0.02
                time.sleep(1 / _FPS)

            # Hold on the fully-revealed wordmark plus real stats, still
            # cycling the rainbow, for `duration` seconds.
            end = time.monotonic() + duration
            while time.monotonic() < end:
                art = _render_frame(lines, lock_frames, frame, hue_offset)
                group = Group(Align.center(art), Align.center(_stats_panel(context)))
                live.update(group)
                hue_offset += 0.02
                time.sleep(1 / _FPS)
    except KeyboardInterrupt:
        pass

    console.print(
        Align.center(Text("NYXOR — audit something real: nyx audit <domain>", style="dim"))
    )


class FlexPlugin:
    metadata = PluginMetadata(
        name="flex",
        description="A pure spectacle — a glitch-reveal RGB wordmark. Not a security feature.",
        version="0.1.0",
        author="NYXOR",
        commands=("flex",),
        category="Fun",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("flex", rich_help_panel=self.metadata.category)(_flex)


PLUGIN = FlexPlugin()
