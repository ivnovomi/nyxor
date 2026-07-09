"""The NYXOR wordmark, rendered with a cyan-to-violet gradient.

Shown when `nyx` is invoked with no arguments and as the TUI splash.
"""

from __future__ import annotations

from rich.align import Align
from rich.console import Console
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
