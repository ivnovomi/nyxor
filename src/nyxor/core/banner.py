"""The NYXOR wordmark, rendered with a cyan-to-violet gradient.

Shown when `nyx` is invoked with no arguments and as the TUI splash. Also
home to the glitch-reveal renderer shared with `nyx flex` — a short,
one-shot version of the same effect plays as a boot sequence before the
static banner+help text, so the CLI's very first impression matches the
"fun" the rest of the tool leans into. It never adds real latency to a
normal command: it only ever plays for the bare `nyx` (no subcommand)
invocation, and only in a real terminal.
"""

from __future__ import annotations

import colorsys
import random
import time

from rich.align import Align
from rich.console import Console
from rich.live import Live
from rich.text import Text

LOGO = r"""
███╗   ██╗██╗   ██╗██╗  ██╗ ██████╗ ██████╗
████╗  ██║╚██╗ ██╔╝╚██╗██╔╝██╔═══██╗██╔══██╗
██╔██╗ ██║ ╚████╔╝  ╚███╔╝ ██║   ██║██████╔╝
██║╚██╗██║  ╚██╔╝   ██╔██╗ ██║   ██║██╔══██╗
██║ ╚████║   ██║   ██╔╝ ██╗╚██████╔╝██║  ██║
╚═╝  ╚═══╝   ╚═╝   ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝
"""

GRADIENT = ("#7ee7e1", "#6fd0da", "#8fa3e6", "#a988e8", "#b98cff", "#c76bf0")

GLITCH_CHARS = "█▓▒░╬╫╪┼#%&$@01XYZ"


def banner_text(*, subtitle: str = "Security Assessment Toolkit") -> Text:
    """Build the gradient-colored NYXOR wordmark as a single Rich Text object."""
    text = Text()
    for line in LOGO.strip("\n").splitlines():
        for i, ch in enumerate(line):
            text.append(ch, style=f"bold {GRADIENT[i % len(GRADIENT)]}")
        text.append("\n")
    text.append(f"{subtitle}\n", style="italic #6b7a99")
    return text


def print_banner(
    console: Console | None = None, *, subtitle: str = "Security Assessment Toolkit"
) -> None:
    console = console or Console()
    console.print(Align.center(banner_text(subtitle=subtitle)))


def hue_to_hex(hue: float) -> str:
    r, g, b = colorsys.hsv_to_rgb(hue % 1.0, 0.85, 1.0)
    return f"#{int(r * 255):02x}{int(g * 255):02x}{int(b * 255):02x}"


def glitch_char() -> str:
    return random.choice(GLITCH_CHARS)


def lock_frame_for(col: int, width: int, reveal_frames: int) -> int:
    """Which frame index column ``col`` settles on its real character —

    a left-to-right wave with a little jitter so it doesn't look
    mechanically perfect.
    """
    base = (col / max(width - 1, 1)) * (reveal_frames * 0.6)
    return int(base + random.uniform(0, reveal_frames * 0.4))


def render_glitch_frame(
    lines: list[str], lock_frames: list[list[int]], frame: int, hue_offset: float
) -> Text:
    """One frame of the glitch-reveal effect: characters not yet "locked in"

    (``frame < lock_frames[row][col]``) show a random glitch glyph instead
    of the real one, all colored by a hue that sweeps across columns and
    drifts over time via ``hue_offset``.
    """
    text = Text()
    width = max((len(line) for line in lines), default=1)
    for row, line in enumerate(lines):
        for col in range(width):
            ch = line[col] if col < len(line) else " "
            if ch == " ":
                text.append(" ")
                continue
            hue = (col / max(width - 1, 1)) + hue_offset
            color = hue_to_hex(hue)
            if frame >= lock_frames[row][col]:
                text.append(ch, style=f"bold {color}")
            else:
                text.append(glitch_char(), style=f"dim {color}")
        text.append("\n")
    return text


def boot_sequence(
    console: Console | None = None,
    *,
    subtitle: str = "Security Assessment Toolkit",
    reveal_frames: int = 18,
    fps: int = 24,
) -> None:
    """A short (well under a second), one-shot glitch-reveal of the wordmark,

    landing on the same static banner :func:`print_banner` shows. Falls
    back to the plain static banner outright when stdout isn't a real
    terminal (piped output, CI logs, etc.) — there's nothing to animate
    there, and trying to would just corrupt the output.
    """
    console = console or Console()
    if not console.is_terminal:
        print_banner(console, subtitle=subtitle)
        return

    lines = LOGO.strip("\n").splitlines()
    width = max(len(line) for line in lines)
    lock_frames = [
        [lock_frame_for(col, width, reveal_frames) for col in range(width)] for _ in lines
    ]
    max_lock = max(max(row) for row in lock_frames)

    try:
        with Live(console=console, refresh_per_second=fps, transient=True) as live:
            hue_offset = 0.0
            for frame in range(max_lock + 1):
                art = render_glitch_frame(lines, lock_frames, frame, hue_offset)
                live.update(Align.center(art))
                hue_offset += 0.03
                time.sleep(1 / fps)
    except KeyboardInterrupt:
        pass

    print_banner(console, subtitle=subtitle)
