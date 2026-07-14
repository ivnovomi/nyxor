from __future__ import annotations

from pathlib import Path

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULES = ("random", "text", "table")


def test_new_lib_modules_lint_clean() -> None:
    for name in _MODULES:
        source = (_REPO_ROOT / "lib" / f"{name}.nyx").read_text(encoding="utf-8")
        assert lint_source(source) == [], f"lib/{name}.nyx has lint issues"


async def _run(body: str) -> list[str]:
    lines: list[str] = []
    imports = "".join(f'import "lib/{name}.nyx" as {name}\n' for name in _MODULES)
    await run_script(imports + body, load_config(), output=lines.append, base_dir=_REPO_ROOT)
    return lines


# ---------- lib/random.nyx ----------


async def test_shuffle_returns_a_permutation_without_mutating_the_input() -> None:
    lines = await _run(
        """
set original = [1, 2, 3, 4, 5]
set shuffled = random.shuffle(original)
print original
print sorted(shuffled) == original
"""
    )
    assert lines == ["[1, 2, 3, 4, 5]", "true"]


async def test_random_int_respects_inclusive_bounds() -> None:
    lines = await _run("print random.random_int(7, 7)\n")
    assert lines == ["7"]


async def test_choice_from_a_single_item_list() -> None:
    lines = await _run("print random.choice([42])\n")
    assert lines == ["42"]


async def test_sample_returns_the_requested_count() -> None:
    lines = await _run("print len(random.sample([1, 2, 3, 4, 5], 3))\n")
    assert lines == ["3"]


async def test_jitter_with_zero_spread_is_exact() -> None:
    # random() is always a float, so the result is 10.0, not the int 10,
    # even with zero spread — arithmetic, not a bug.
    lines = await _run("print random.jitter(10, 0)\n")
    assert lines == ["10.0"]


# ---------- lib/text.nyx ----------


async def test_capitalize() -> None:
    lines = await _run('print text.capitalize("hELLO")\n')
    assert lines == ["Hello"]


async def test_center_pads_both_sides() -> None:
    lines = await _run('print text.center("hi", 6, "-")\n')
    assert lines == ["--hi--"]


async def test_center_leaves_a_too_long_string_alone() -> None:
    lines = await _run('print text.center("toolong", 3, "-")\n')
    assert lines == ["toolong"]


async def test_reverse() -> None:
    lines = await _run('print text.reverse("abcde")\n')
    assert lines == ["edcba"]


async def test_contains_ignore_case() -> None:
    lines = await _run(
        """
print text.contains_ignore_case("Hello World", "WORLD")
print text.contains_ignore_case("Hello World", "xyz")
"""
    )
    assert lines == ["true", "false"]


async def test_count_occurrences() -> None:
    lines = await _run('print text.count_occurrences("abcabcabc", "abc")\n')
    assert lines == ["3"]


async def test_is_blank() -> None:
    lines = await _run(
        """
print text.is_blank("   ")
print text.is_blank("x")
print text.is_blank("")
"""
    )
    assert lines == ["true", "false", "true"]


async def test_words_splits_on_whitespace_runs() -> None:
    lines = await _run('print text.words("  the   quick brown  fox ")\n')
    assert lines == ["[the, quick, brown, fox]"]


async def test_lines_splits_on_newlines() -> None:
    lines = await _run('print text.lines("a\\nb\\nc")\n')
    assert lines == ["[a, b, c]"]


async def test_slugify() -> None:
    lines = await _run('print text.slugify("Hello, World! 2024")\n')
    assert lines == ["hello-world-2024"]


# ---------- lib/table.nyx ----------


async def test_table_render_aligns_columns() -> None:
    lines = await _run('print table.render(["name", "grade"], [["a", "A"], ["bb", "B+"]])\n')
    assert lines == ["| name | grade |\n+------+-------+\n| a    | A     |\n| bb   | B+    |"]


async def test_table_render_with_no_rows() -> None:
    lines = await _run('print table.render(["only"], [])\n')
    assert lines == ["| only |\n+------+"]
