from __future__ import annotations

from nyxor.plugins.matrix.plugin import _make_frame


def test_make_frame_has_the_requested_dimensions() -> None:
    frame = _make_frame(width=10, height=5, heads=[0] * 10)
    lines = frame.plain.splitlines()
    assert len(lines) == 5
    assert all(len(line) == 10 for line in lines)


def test_make_frame_places_a_glyph_at_the_head_row() -> None:
    # heads[0] == 2 means column 0's head is on row 2 — that cell should
    # not be blank, everything below it (row > head) should be.
    frame = _make_frame(width=1, height=6, heads=[2])
    lines = frame.plain.splitlines()
    assert lines[2] != " "
    assert lines[3] == " "  # below the head, no trail yet in this direction
    assert lines[4] == " "
    assert lines[5] == " "


def test_make_frame_trail_extends_above_the_head_and_nothing_below() -> None:
    # The head is the leading (falling) edge; the trail is what it already
    # passed through, i.e. smaller row indices (drawn higher up).
    frame = _make_frame(width=1, height=10, heads=[3])
    lines = frame.plain.splitlines()
    for row in range(3):
        assert lines[row] != " "  # trail above the head
    for row in range(4, 10):
        assert lines[row] == " "  # nothing below it yet


def test_make_frame_head_off_screen_renders_an_all_blank_frame() -> None:
    frame = _make_frame(width=4, height=4, heads=[-100] * 4)
    assert frame.plain == (" " * 4 + "\n") * 3 + " " * 4


def test_make_frame_rainbow_mode_has_the_same_shape_as_default() -> None:
    frame = _make_frame(width=10, height=5, heads=[3] * 10, rainbow=True, hue_offset=0.3)
    lines = frame.plain.splitlines()
    assert len(lines) == 5
    assert all(len(line) == 10 for line in lines)
