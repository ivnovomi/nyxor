"""Render a QR code as text, for terminals with no image support.

Uses Unicode half-block glyphs (``▀``/``▄``/``█``/space) rather than a
graphics protocol (Kitty, Sixel, iTerm2) or a color fill — a QR code is
just a black-and-white bitmap, and glyph shape alone is enough to encode
it, so this works in any UTF-8-capable terminal (Windows Terminal, tmux,
a CI log, an SSH session with no truecolor support) without needing to
detect what the terminal can do.

Two QR rows are packed into one terminal row because a monospace cell is
roughly twice as tall as it is wide — packing 1:1 would render a QR code
visibly stretched vertically, which some scanners tolerate and some
don't. Half-block packing keeps each rendered module square.
"""

from __future__ import annotations

import qrcode


def render_qr(data: str, *, border: int = 1) -> str:
    """Render ``data`` as a QR code, one line per output row.

    ``error_correction`` is pinned (rather than left to whatever the
    installed ``qrcode`` version currently defaults to) so the module
    layout for the same input can't shift under us across a dependency
    bump. ``version`` is intentionally left on auto-fit — that's the
    correct behavior (grow to whatever the data needs), not something to
    pin. ``box_size``/output-image options don't apply here at all: this
    only ever reads the QR matrix, never renders through qrcode's own
    (Pillow-based) image output.
    """
    qr = qrcode.QRCode(border=border, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(data)
    qr.make(fit=True)
    matrix: list[list[bool]] = qr.get_matrix()

    lines: list[str] = []
    for y in range(0, len(matrix), 2):
        top = matrix[y]
        bottom = matrix[y + 1] if y + 1 < len(matrix) else [False] * len(top)
        line = "".join(
            "█" if is_top and is_bottom else "▀" if is_top else "▄" if is_bottom else " "
            for is_top, is_bottom in zip(top, bottom, strict=True)
        )
        lines.append(line)
    return "\n".join(lines)
