from __future__ import annotations

from pathlib import Path

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script

_REPO_ROOT = Path(__file__).resolve().parents[2]


async def _run(body: str) -> list[str]:
    lines: list[str] = []
    source = f'import "lib/lambdas.nyx" as fn\n{body}'
    await run_script(source, load_config(), output=lines.append, base_dir=_REPO_ROOT)
    return lines


def test_lambdas_module_lints_clean() -> None:
    source = (_REPO_ROOT / "lib" / "lambdas.nyx").read_text(encoding="utf-8")
    assert lint_source(source) == []


async def test_compose_applies_right_to_left() -> None:
    lines = await _run(
        """
set inc = lambda(x): x + 1
set double = lambda(x): x * 2
set inc_then_double = fn.compose(double, inc)
print inc_then_double(3)
"""
    )
    assert lines == ["8"]  # double(inc(3)) == double(4) == 8


async def test_pipe_applies_left_to_right() -> None:
    lines = await _run(
        """
set inc = lambda(x): x + 1
set double = lambda(x): x * 2
set inc_then_double = fn.pipe(inc, double)
print inc_then_double(3)
"""
    )
    assert lines == ["8"]  # double(inc(3)) == double(4) == 8


async def test_partial_fixes_the_first_argument() -> None:
    lines = await _run(
        """
set add = lambda(a, b): a + b
set add5 = fn.partial(add, 5)
print add5(10)
"""
    )
    assert lines == ["15"]


async def test_flip_swaps_the_first_two_arguments() -> None:
    lines = await _run(
        """
set sub = lambda(a, b): a - b
set flipped = fn.flip(sub)
print flipped(3, 10)
"""
    )
    assert lines == ["7"]  # sub(10, 3)


async def test_predicate_combinators() -> None:
    lines = await _run(
        """
set nums = [1, 2, 3, 4, 5]
print fn.any_of(nums, lambda(x): x > 4)
print fn.all_of(nums, lambda(x): x > 0)
print fn.none_of(nums, lambda(x): x > 10)
print fn.count_where(nums, lambda(x): x > 2)
"""
    )
    assert lines == ["true", "true", "true", "3"]


async def test_find_where_returns_default_when_nothing_matches() -> None:
    lines = await _run(
        """
set nums = [1, 2, 3]
print fn.find_where(nums, lambda(x): x > 1, -1)
print fn.find_where(nums, lambda(x): x > 99, -1)
"""
    )
    assert lines == ["2", "-1"]


async def test_flat_map_flattens_one_level() -> None:
    lines = await _run(
        """
print fn.flat_map([1, 2, 3], lambda(x): [x, x * 10])
"""
    )
    assert lines == ["[1, 10, 2, 20, 3, 30]"]


async def test_group_by_buckets_items_by_key() -> None:
    lines = await _run(
        """
set words = ["fig", "kiwi", "pear", "plum"]
set grouped = fn.group_by(words, lambda(w): len(w))
print grouped[3]
print grouped[4]
"""
    )
    assert lines == ["[fig]", "[kiwi, pear, plum]"]


async def test_times_calls_fn_with_each_index() -> None:
    lines = await _run(
        """
print fn.times(4, lambda(i): i * i)
"""
    )
    assert lines == ["[0, 1, 4, 9]"]


async def test_identity_and_constant() -> None:
    lines = await _run(
        """
print fn.identity(42)
set always_hi = fn.constant("hi")
print always_hi(1)
print always_hi("anything")
"""
    )
    assert lines == ["42", "hi", "hi"]


async def test_negate_inverts_a_predicate() -> None:
    lines = await _run(
        """
set is_positive = lambda(x): x > 0
set is_not_positive = fn.negate(is_positive)
print is_not_positive(5)
print is_not_positive(-5)
"""
    )
    assert lines == ["false", "true"]
