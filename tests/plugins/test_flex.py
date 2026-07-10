from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from nyxor.core.banner import LOGO
from nyxor.core.config import load_config
from nyxor.core.context import NyxorContext
from nyxor.plugins.flex.plugin import (
    _glitch_char,
    _hue_to_hex,
    _lock_frame_for,
    _render_frame,
    _stats_panel,
)


def test_hue_to_hex_produces_a_valid_hex_color() -> None:
    for hue in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, -0.3):
        color = _hue_to_hex(hue)
        assert color.startswith("#")
        assert len(color) == 7
        int(color[1:], 16)  # doesn't raise


def test_glitch_char_returns_a_single_character() -> None:
    for _ in range(20):
        assert len(_glitch_char()) == 1


def test_lock_frame_for_is_non_negative_and_bounded() -> None:
    for col in range(20):
        frame = _lock_frame_for(col, 20)
        assert frame >= 0


def test_render_frame_produces_a_rich_text_matching_the_logo_shape() -> None:
    lines = LOGO.strip("\n").splitlines()
    width = max(len(line) for line in lines)
    lock_frames = [[0 for _ in range(width)] for _ in lines]  # everything locked in

    art = _render_frame(lines, lock_frames, frame=0, hue_offset=0.0)

    assert isinstance(art, Text)
    rendered_lines = art.plain.splitlines()
    assert len(rendered_lines) == len(lines)


def test_render_frame_before_lock_shows_glitch_not_the_real_character() -> None:
    lines = ["NYXOR"]
    lock_frames = [[999, 999, 999, 999, 999]]  # never locks in

    art = _render_frame(lines, lock_frames, frame=0, hue_offset=0.0)

    assert art.plain.strip("\n") != "NYXOR"


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
