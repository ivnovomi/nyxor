from __future__ import annotations

from rich.console import Console

from nyxor.core.scripting.errors import RuntimeScriptError
from nyxor.plugins.script.plugin import _print_script_error


def test_prints_the_offending_source_line_and_a_caret() -> None:
    console = Console(record=True, width=120)
    source = 'set x = 5\nset y = "hello"\nprint x + y\n'
    exc = RuntimeScriptError("cannot apply '+' to int and str", line=3)

    _print_script_error(console, source, exc)

    text = console.export_text()
    assert "cannot apply '+' to int and str" in text
    assert "print x + y" in text
    assert "^" in text


def test_points_the_caret_past_leading_indentation() -> None:
    console = Console(record=True, width=120)
    source = 'func f():\n    fail "boom"\nend\n'
    exc = RuntimeScriptError("boom", line=2)

    _print_script_error(console, source, exc)

    lines = console.export_text().splitlines()
    code_line = next(line for line in lines if "fail" in line)
    caret_line = lines[lines.index(code_line) + 1]
    # the caret should land under "fail", not under the leading spaces
    assert caret_line.index("^") == code_line.index("fail")


def test_out_of_range_line_number_does_not_crash() -> None:
    console = Console(record=True, width=120)
    exc = RuntimeScriptError("something broke", line=999)

    _print_script_error(console, "set x = 1\n", exc)  # should not raise

    assert "something broke" in console.export_text()


def test_no_line_number_just_prints_the_message() -> None:
    console = Console(record=True, width=120)
    exc = RuntimeScriptError("something broke")

    _print_script_error(console, "set x = 1\n", exc)

    text = console.export_text()
    assert "something broke" in text
    assert "^" not in text
