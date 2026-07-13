from __future__ import annotations

from rich.console import Console
from rich.text import Text

from nyxor.core.banner import (
    LOGO,
    boot_sequence,
    glitch_char,
    hue_to_hex,
    lock_frame_for,
    print_banner,
    render_glitch_frame,
)


def test_hue_to_hex_produces_a_valid_hex_color() -> None:
    for hue in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5, -0.3):
        color = hue_to_hex(hue)
        assert color.startswith("#")
        assert len(color) == 7
        int(color[1:], 16)  # doesn't raise


def test_glitch_char_returns_a_single_character() -> None:
    for _ in range(20):
        assert len(glitch_char()) == 1


def test_lock_frame_for_is_non_negative() -> None:
    for col in range(20):
        frame = lock_frame_for(col, 20, reveal_frames=18)
        assert frame >= 0


def test_render_glitch_frame_matches_the_logo_shape() -> None:
    lines = LOGO.strip("\n").splitlines()
    width = max(len(line) for line in lines)
    lock_frames = [[0 for _ in range(width)] for _ in lines]  # everything locked in

    art = render_glitch_frame(lines, lock_frames, frame=0, hue_offset=0.0)

    assert isinstance(art, Text)
    assert len(art.plain.splitlines()) == len(lines)


def test_render_glitch_frame_before_lock_shows_glitch_not_the_real_character() -> None:
    lines = ["NYXOR"]
    lock_frames = [[999, 999, 999, 999, 999]]  # never locks in

    art = render_glitch_frame(lines, lock_frames, frame=0, hue_offset=0.0)

    assert art.plain.strip("\n") != "NYXOR"


def test_print_banner_includes_the_subtitle() -> None:
    console = Console(record=True, width=120)
    print_banner(console, subtitle="Test Subtitle")
    assert "Test Subtitle" in console.export_text()


def test_boot_sequence_falls_back_to_the_static_banner_when_not_a_terminal() -> None:
    console = Console(record=True, width=120, force_terminal=False)
    assert not console.is_terminal

    boot_sequence(console, subtitle="Boot Test")

    assert "Boot Test" in console.export_text()
