from __future__ import annotations

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script


async def _run(source: str) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append)
    return lines


async def test_raw_string_does_not_process_escapes() -> None:
    lines = await _run(r'print r"a\wb\nc"' + "\n")
    assert lines == [r"a\wb\nc"]


async def test_raw_string_does_not_interpolate() -> None:
    lines = await _run(r'print r"literal {1 + 1} braces"' + "\n")
    assert lines == ["literal {1 + 1} braces"]


async def test_raw_string_regex_quantifier_needs_no_doubled_braces() -> None:
    # The whole point: a normal string needs "{{2,4}}" to survive
    # interpolation; a raw string doesn't, because it never interpolates.
    lines = await _run(r'print regex_match("hello 42", r"\w+ \d{2,4}")' + "\n")
    assert lines == ["true"]


async def test_raw_string_single_quotes() -> None:
    lines = await _run(r"print r'a\wb {not interpolated}'" + "\n")
    assert lines == [r"a\wb {not interpolated}"]


async def test_raw_string_windows_path_needs_no_escaping() -> None:
    lines = await _run(r'print r"C:\Users\test\file.txt"' + "\n")
    assert lines == [r"C:\Users\test\file.txt"]


async def test_raw_string_can_contain_an_escaped_closing_quote() -> None:
    lines = await _run('print r"a\\"b"\n')
    assert lines == ['a\\"b']


async def test_normal_strings_still_interpolate_and_escape() -> None:
    lines = await _run('print "a\\nb {1 + 1}"\n')
    assert lines == ["a\nb 2"]


async def test_raw_string_lints_clean_and_skips_interpolation_checks() -> None:
    # A raw string containing something that looks like {undefined_var}
    # must not trip the linter's undefined-variable check, since it's
    # never actually interpolated.
    issues = lint_source(r'print r"{totally_undefined}"' + "\n")
    assert issues == []


async def test_raw_string_as_a_regex_pattern_variable() -> None:
    lines = await _run(
        r"""
set pattern = r"\d{3}-\d{4}"
print regex_find("call 555-1234 now", pattern, "no match")
"""
    )
    assert lines == ["555-1234"]
