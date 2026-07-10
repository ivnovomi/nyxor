from __future__ import annotations

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script


async def _run(source: str) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append)
    return lines


@pytest.mark.asyncio
async def test_dict_literal_and_index_read() -> None:
    lines = await _run(
        """
set d = {"a": 1, "b": 2}
print d["a"]
print len(d)
"""
    )
    assert lines == ["1", "2"]


@pytest.mark.asyncio
async def test_index_assignment_mutates_a_dict_in_place() -> None:
    lines = await _run(
        """
set d = {"count": 0}
set d["count"] = d["count"] + 1
set d["count"] = d["count"] + 1
print d["count"]
"""
    )
    assert lines == ["2"]


@pytest.mark.asyncio
async def test_index_assignment_mutates_a_list_in_place() -> None:
    lines = await _run(
        """
set items = [1, 2, 3]
set items[1] = 99
print items
"""
    )
    assert lines == ["[1, 99, 3]"]


@pytest.mark.asyncio
async def test_keys_values_items_get_builtins() -> None:
    lines = await _run(
        """
set d = {"x": 1, "y": 2}
print sorted(keys(d))
print sorted(values(d))
print get(d, "x", 0)
print get(d, "missing", -1)
"""
    )
    assert lines == ["[x, y]", "[1, 2]", "1", "-1"]


@pytest.mark.asyncio
async def test_try_except_catches_a_runtime_error_and_binds_the_message() -> None:
    lines = await _run(
        """
try:
    fail "boom"
except err:
    print "caught: {err}"
end
print "after"
"""
    )
    assert lines == ["caught: boom", "after"]


@pytest.mark.asyncio
async def test_try_except_does_not_catch_when_body_succeeds() -> None:
    lines = await _run(
        """
try:
    print "fine"
except err:
    print "should not run"
end
"""
    )
    assert lines == ["fine"]


def test_dict_and_try_lint_clean() -> None:
    issues = lint_source(
        """
set d = {"a": 1}
set d["b"] = 2

try:
    fail "x"
except err:
    print err
end
"""
    )
    assert issues == []


def test_try_reports_error_var_only_defined_inside_except_body() -> None:
    issues = lint_source(
        """
try:
    print "ok"
except err:
    print "ok"
end
print err
"""
    )
    assert any("undefined variable 'err'" in issue.message for issue in issues)
