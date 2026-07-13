from __future__ import annotations

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import run_script
from nyxor.core.scripting.errors import RuntimeScriptError


async def _run(source: str) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append)
    return lines


async def test_range_rejects_an_absurdly_large_span() -> None:
    # range() eagerly materializes a Python list — with no cap, a single
    # call like this would try to allocate a list with 10 billion items.
    with pytest.raises(RuntimeScriptError, match="range\\(\\) would produce"):
        await _run("set x = range(10000000000)\n")


async def test_range_within_the_limit_still_works() -> None:
    lines = await _run("print len(range(1000))\n")
    assert lines == ["1000"]


async def test_string_repetition_rejects_an_absurdly_large_result() -> None:
    # "x" * n is sequence repetition, not arithmetic — a single tiny
    # operand pair can request an arbitrarily large allocation.
    with pytest.raises(RuntimeScriptError, match="'\\*' would produce a sequence"):
        await _run('set x = "a" * 10000000000\n')


async def test_list_repetition_rejects_an_absurdly_large_result() -> None:
    with pytest.raises(RuntimeScriptError, match="'\\*' would produce a sequence"):
        await _run("set x = [1, 2, 3] * 10000000000\n")


async def test_string_repetition_within_the_limit_still_works() -> None:
    lines = await _run('print "ab" * 3\n')
    assert lines == ["ababab"]


async def test_list_repetition_within_the_limit_still_works() -> None:
    lines = await _run("print [1, 2] * 3\n")
    assert lines == ["[1, 2, 1, 2, 1, 2]"]


async def test_integer_multiplication_is_unaffected_by_the_sequence_guard() -> None:
    lines = await _run("print 7 * 1000000000\n")
    assert lines == ["7000000000"]


async def test_negative_repetition_factor_is_not_flagged_as_oversized() -> None:
    # Python treats `seq * -n` as an empty sequence, not an error — the
    # guard shouldn't misread a negative factor as an enormous positive one.
    lines = await _run('print "ab" * -3\n')
    assert lines == [""]
