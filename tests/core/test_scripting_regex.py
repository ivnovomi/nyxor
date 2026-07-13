from __future__ import annotations

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import builtins as builtins_module
from nyxor.core.scripting import run_script
from nyxor.core.scripting.errors import RuntimeScriptError


async def _run(source: str) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append)
    return lines


async def test_common_regex_escapes_survive_a_string_literal() -> None:
    # Regression: the lexer used to silently drop the backslash from any
    # escape it didn't recognize (\w -> w, \d -> d, ...), which made the
    # character classes regex patterns rely on most unwritable. An unknown
    # escape must now keep both characters, like Python's own strings.
    lines = await _run(
        r"""
print regex_match("word123", "\w+")
print regex_match("42", "\d+")
"""
    )
    assert lines == ["true", "true"]


async def test_regex_match_true_and_false() -> None:
    lines = await _run(
        """
print regex_match("hello123", "[0-9]+")
print regex_match("hello", "[0-9]+")
"""
    )
    assert lines == ["true", "false"]


async def test_regex_find_returns_the_first_match_or_a_default() -> None:
    lines = await _run(
        """
print regex_find("port: 8080", "[0-9]+", "none")
print regex_find("no digits here", "[0-9]+", "none")
"""
    )
    assert lines == ["8080", "none"]


async def test_regex_find_all_returns_every_match() -> None:
    lines = await _run('print regex_find_all("a1 b22 c333", "[0-9]+")\n')
    assert lines == ["[1, 22, 333]"]


async def test_regex_find_all_normalizes_capture_groups_to_lists() -> None:
    # re.findall() returns tuples when the pattern has capture groups —
    # NyxScript has no tuple type, only list, so this must come back as
    # nested lists, matching zip()'s convention.
    lines = await _run(r'print regex_find_all("key=val", "(\w+)=(\w+)")' + "\n")
    assert lines == ["[[key, val]]"]


async def test_regex_replace_substitutes_all_matches() -> None:
    lines = await _run('print regex_replace("hello world", "o", "0")\n')
    assert lines == ["hell0 w0rld"]


async def test_an_invalid_pattern_raises_a_script_error() -> None:
    with pytest.raises(RuntimeScriptError, match="invalid regex"):
        await _run('print regex_match("x", "(unterminated")\n')


async def test_regex_functions_reject_wrong_arity() -> None:
    with pytest.raises(RuntimeScriptError, match="regex_match"):
        await _run('print regex_match("x")\n')


async def test_regex_input_length_is_capped() -> None:
    with pytest.raises(RuntimeScriptError, match="regex input is"):
        # Comfortably over _REGEX_MAX_INPUT_LEN without actually needing a
        # slow pattern — this guards allocation/scan cost, not backtracking.
        await _run(f'print regex_match("{"a" * 200_000}", "b")\n')


async def test_regex_evaluation_that_exceeds_the_timeout_raises_cleanly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A timeout this tiny (1ms) is tripped by the cost of spawning/talking
    # to the worker process alone, for *any* pattern — no genuine
    # catastrophic-backtracking regex needed to exercise the kill-and-raise
    # path deterministically and fast.
    monkeypatch.setattr(builtins_module, "_REGEX_TIMEOUT_SECONDS", 0.001)
    builtins_module._kill_regex_worker()  # start from a clean slate
    try:
        with pytest.raises(RuntimeScriptError, match="exceeded 0.001s"):
            await _run('print regex_match("hello", "h")\n')
    finally:
        builtins_module._kill_regex_worker()  # don't leak a process into other tests


async def test_a_genuinely_catastrophic_pattern_times_out_instead_of_hanging() -> None:
    # The real thing, at the real default timeout: `(a+)+b` against a long
    # run of a's with no trailing b is the textbook catastrophic-
    # backtracking case. This is the actual property being defended —
    # the interpreter must get an error back, not hang.
    with pytest.raises(RuntimeScriptError, match="catastrophic backtracking"):
        await _run('print regex_match("' + "a" * 40 + '!", "(a+)+b")\n')
