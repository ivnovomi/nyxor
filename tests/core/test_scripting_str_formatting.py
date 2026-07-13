from __future__ import annotations

from nyxor.core.config import load_config
from nyxor.core.scripting import run_script


async def _run(source: str) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append)
    return lines


async def test_str_of_a_bool_matches_prints_own_formatting() -> None:
    # Regression: str(x) used to call Python's raw str(), so str(true)
    # gave "True" while `print true` (via the interpreter's own
    # formatting) showed "true" — the same value printing two different
    # ways depending on how you asked for its string form.
    lines = await _run(
        """
print str(true)
print true
"""
    )
    assert lines == ["true", "true"]


async def test_str_of_a_list_or_dict_containing_bools_is_consistent() -> None:
    lines = await _run('print str([1, true, {"a": false}])\n')
    assert lines == ["[1, true, {a: false}]"]


async def test_string_concatenation_with_str_of_a_bool() -> None:
    lines = await _run('print "result: " + str(false)\n')
    assert lines == ["result: false"]
