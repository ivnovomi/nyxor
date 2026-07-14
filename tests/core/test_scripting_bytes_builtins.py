from __future__ import annotations

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import run_script
from nyxor.core.scripting.errors import RuntimeScriptError


async def _run(source: str) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append)
    return lines


async def test_bytes_from_hex_and_to_hex_round_trip() -> None:
    lines = await _run('print bytes_to_hex(bytes_from_hex("4142"))\n')
    assert lines == ["4142"]


async def test_bytes_from_hex_matches_known_values() -> None:
    lines = await _run('print bytes_from_hex("4142")\n')
    assert lines == ["[65, 66]"]


async def test_bytes_from_hex_rejects_invalid_hex() -> None:
    with pytest.raises(RuntimeScriptError, match="invalid hex"):
        await _run('print bytes_from_hex("zz")\n')


async def test_bytes_string_round_trip() -> None:
    lines = await _run(
        """
set b = bytes_from_string("hello")
print bytes_to_string(b)
"""
    )
    assert lines == ["hello"]


async def test_bytes_to_hex_rejects_out_of_range_values() -> None:
    with pytest.raises(RuntimeScriptError, match="bytes_to_hex"):
        await _run("print bytes_to_hex([256])\n")


async def test_pack_unpack_uint16_round_trip() -> None:
    lines = await _run(
        """
print pack_uint16(4660)
print unpack_uint16(pack_uint16(4660))
"""
    )
    assert lines == ["[18, 52]", "4660"]


async def test_pack_unpack_uint32_round_trip() -> None:
    lines = await _run(
        """
print pack_uint32(305419896)
print unpack_uint32(pack_uint32(305419896))
"""
    )
    assert lines == ["[18, 52, 86, 120]", "305419896"]


async def test_pack_uint16_rejects_a_value_that_does_not_fit() -> None:
    with pytest.raises(RuntimeScriptError, match="pack_uint16"):
        await _run("print pack_uint16(70000)\n")


async def test_pack_uint16_rejects_negative_values() -> None:
    with pytest.raises(RuntimeScriptError, match="pack_uint16"):
        await _run("print pack_uint16(-1)\n")


async def test_unpack_uint16_requires_exactly_two_bytes() -> None:
    with pytest.raises(RuntimeScriptError, match="exactly 2"):
        await _run("print unpack_uint16([1, 2, 3])\n")
