from __future__ import annotations

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import run_script
from nyxor.core.scripting.errors import RuntimeScriptError


async def _run(source: str) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append)
    return lines


async def test_base64_encode_matches_a_known_value() -> None:
    lines = await _run('print base64_encode("hello:world")\n')
    assert lines == ["aGVsbG86d29ybGQ="]


async def test_base64_round_trips() -> None:
    lines = await _run(
        """
set encoded = base64_encode("round trip me")
print base64_decode(encoded)
"""
    )
    assert lines == ["round trip me"]


async def test_base64_decode_rejects_invalid_input() -> None:
    with pytest.raises(RuntimeScriptError, match="invalid base64"):
        await _run('print base64_decode("not valid base64!!!")\n')


async def test_random_is_within_the_unit_interval() -> None:
    lines = await _run("print random() >= 0.0 and random() < 1.0\n")
    assert lines == ["true"]


async def test_random_rejects_arguments() -> None:
    with pytest.raises(RuntimeScriptError, match="random"):
        await _run("print random(1)\n")
