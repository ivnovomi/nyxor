from __future__ import annotations

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script


async def _run(source: str) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append)
    return lines


@pytest.mark.asyncio
async def test_lambda_can_be_called_directly_via_a_variable() -> None:
    lines = await _run(
        """
set sq = lambda(x): x * x
print sq(5)
"""
    )
    assert lines == ["25"]


@pytest.mark.asyncio
async def test_map_applies_a_lambda_to_every_item() -> None:
    lines = await _run(
        """
set nums = [1, 2, 3]
print map(nums, lambda(x): x * 2)
"""
    )
    assert lines == ["[2, 4, 6]"]


@pytest.mark.asyncio
async def test_filter_keeps_only_truthy_items() -> None:
    lines = await _run(
        """
set nums = [1, 2, 3, 4, 5]
print filter(nums, lambda(x): x > 2)
"""
    )
    assert lines == ["[3, 4, 5]"]


@pytest.mark.asyncio
async def test_sort_by_orders_by_the_lambda_key() -> None:
    lines = await _run(
        """
set words = ["banana", "kiwi", "fig"]
print sort_by(words, lambda(w): len(w))
"""
    )
    assert lines == ["[fig, kiwi, banana]"]


@pytest.mark.asyncio
async def test_reduce_folds_over_a_list() -> None:
    lines = await _run(
        """
set nums = [1, 2, 3, 4]
print reduce(nums, lambda(acc, x): acc + x, 0)
"""
    )
    assert lines == ["10"]


@pytest.mark.asyncio
async def test_lambda_captures_a_locally_scoped_variable_at_creation_time() -> None:
    # This is the whole reason lambdas capture more than `func` does: a
    # lambda built *inside* a function needs to see that function's own
    # locals (threshold here), not just the top-level script's globals.
    lines = await _run(
        """
func find_big(items, threshold):
    return filter(items, lambda(x): x > threshold)
end

print find_big([1, 2, 3, 4, 5], 3)
"""
    )
    assert lines == ["[4, 5]"]


@pytest.mark.asyncio
async def test_map_rejects_a_non_function_second_argument() -> None:
    with pytest.raises(Exception, match="expects a function"):
        await _run("print map([1, 2], 5)")


@pytest.mark.asyncio
async def test_map_rejects_a_non_list_first_argument() -> None:
    with pytest.raises(Exception, match="expects a list"):
        await _run("print map(5, lambda(x): x)")


@pytest.mark.asyncio
async def test_list_slicing() -> None:
    lines = await _run(
        """
set nums = [1, 2, 3, 4, 5]
print nums[1:3]
print nums[:2]
print nums[3:]
print nums[:]
"""
    )
    assert lines == ["[2, 3]", "[1, 2]", "[4, 5]", "[1, 2, 3, 4, 5]"]


@pytest.mark.asyncio
async def test_string_slicing() -> None:
    lines = await _run('print "hello world"[0:5]')
    assert lines == ["hello"]


@pytest.mark.asyncio
async def test_slicing_a_dict_is_a_runtime_error() -> None:
    with pytest.raises(Exception, match="cannot slice"):
        await _run('set d = {"a": 1}\nprint d[0:1]')


@pytest.mark.asyncio
async def test_new_string_builtins() -> None:
    lines = await _run(
        """
print replace("hello world", "world", "nyxor")
print starts_with("nyxor", "ny")
print ends_with("nyxor", "or")
print find("hello", "ll")
print find("hello", "zz")
"""
    )
    assert lines == ["hello nyxor", "true", "true", "2", "-1"]


@pytest.mark.asyncio
async def test_zip_pairs_two_lists() -> None:
    lines = await _run('print zip([1, 2, 3], ["a", "b", "c"])')
    assert lines == ["[[1, a], [2, b], [3, c]]"]


@pytest.mark.asyncio
async def test_json_round_trip() -> None:
    lines = await _run(
        """
set encoded = to_json({"a": 1, "b": [1, 2, 3]})
print encoded
set decoded = parse_json(encoded)
print decoded["a"]
print decoded["b"]
"""
    )
    assert lines[0] in (
        '{"a": 1, "b": [1, 2, 3]}',
        '{"b": [1, 2, 3], "a": 1}',
    )
    assert lines[1] == "1"
    assert lines[2] == "[1, 2, 3]"


@pytest.mark.asyncio
async def test_parse_json_rejects_null() -> None:
    # {{ / }} escape literal braces — NyxScript's own string interpolation
    # would otherwise try to parse a bare "{...}" as a {expr} span.
    with pytest.raises(Exception, match="null"):
        await _run("print parse_json('{{\"a\": null}}')")


@pytest.mark.asyncio
async def test_type_of_a_lambda_is_function() -> None:
    lines = await _run(
        """
set f = lambda(x): x
print type_of(f)
"""
    )
    assert lines == ["function"]


def test_dict_and_lambda_lint_clean() -> None:
    issues = lint_source(
        """
set sq = lambda(x): x * x
print sq(5)
print map([1, 2, 3], lambda(x): x + 1)

func find_big(items, threshold):
    return filter(items, lambda(x): x > threshold)
end
"""
    )
    assert issues == []
