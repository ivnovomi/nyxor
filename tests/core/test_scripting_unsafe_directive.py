from __future__ import annotations

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import run_script
from nyxor.core.scripting.errors import RuntimeScriptError

_SOURCE = 'unsafe\npython:\n    result = 6 * 7\nend\nprint result\n'


async def _run(*, unsafe: bool = False, allow_unsafe_directive: bool = True) -> list[str]:
    lines: list[str] = []
    await run_script(
        _SOURCE,
        load_config(),
        output=lines.append,
        unsafe=unsafe,
        allow_unsafe_directive=allow_unsafe_directive,
    )
    return lines


async def test_unsafe_statement_self_enables_python_by_default() -> None:
    # The CLI/TUI path: allow_unsafe_directive defaults True, so a script's
    # own `unsafe` statement works without --unsafe on the command line.
    lines = await _run()
    assert lines == ["42"]


async def test_unsafe_statement_is_refused_when_the_caller_locks_it_out() -> None:
    # The MCP path: allow_unsafe_directive=False must be a hard ceiling —
    # unsafe=False alone is not enough, since the script itself could raise
    # self.unsafe to True at runtime via the `unsafe` statement otherwise.
    with pytest.raises(RuntimeScriptError, match="disabled by the caller"):
        await _run(allow_unsafe_directive=False)


async def test_unsafe_statement_is_a_noop_when_already_unsafe() -> None:
    lines = await _run(unsafe=True, allow_unsafe_directive=False)
    assert lines == ["42"]
