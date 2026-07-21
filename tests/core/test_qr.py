from __future__ import annotations

import math

import qrcode

from nyxor.core.qr import render_qr

_GLYPHS = frozenset(" █▀▄")


def test_render_qr_only_uses_the_four_expected_glyphs() -> None:
    output = render_qr("https://example.com/oauth/device?user_code=ABCD-EFGH")
    assert set(output) - _GLYPHS == {"\n"}


def test_render_qr_packs_two_matrix_rows_per_output_line() -> None:
    data = "https://example.com/oauth/device?user_code=ABCD-EFGH"
    qr = qrcode.QRCode(border=1)
    qr.add_data(data)
    qr.make(fit=True)
    matrix = qr.get_matrix()

    lines = render_qr(data).splitlines()

    assert len(lines) == math.ceil(len(matrix) / 2)
    assert all(len(line) == len(matrix[0]) for line in lines)


def test_render_qr_is_deterministic() -> None:
    data = "https://example.com/oauth/device?user_code=ABCD-EFGH"
    assert render_qr(data) == render_qr(data)


def test_render_qr_differs_for_different_data() -> None:
    assert render_qr("https://example.com/a") != render_qr("https://example.com/b")


def test_render_qr_grows_with_a_larger_border() -> None:
    data = "https://example.com/oauth/device?user_code=ABCD-EFGH"
    narrow = render_qr(data, border=1).splitlines()
    wide = render_qr(data, border=4).splitlines()
    assert len(wide[0]) > len(narrow[0])
