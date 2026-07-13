from __future__ import annotations

from pathlib import Path

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script
from nyxor.core.scripting.errors import RuntimeScriptError

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_time_module_lints_clean() -> None:
    source = (_REPO_ROOT / "lib" / "time.nyx").read_text(encoding="utf-8")
    assert lint_source(source) == []


async def _run(body: str) -> list[str]:
    lines: list[str] = []
    source = f'import "lib/time.nyx" as time\n{body}'
    await run_script(source, load_config(), output=lines.append, base_dir=_REPO_ROOT)
    return lines


async def test_now_returns_a_plausible_unix_timestamp() -> None:
    # No fixed expected value (it's the wall clock) — just sanity-check
    # it's in the right ballpark: after 2020-01-01, before the year 2100.
    lines = await _run("print now() > 1577836800 and now() < 4102444800\n")
    assert lines == ["true"]


async def test_to_iso8601_formats_a_known_epoch() -> None:
    lines = await _run("print to_iso8601(0)\n")
    assert lines == ["1970-01-01T00:00:00+00:00"]


async def test_to_iso8601_rejects_a_non_numeric_argument() -> None:
    with pytest.raises(RuntimeScriptError, match="to_iso8601"):
        await _run('print to_iso8601("not a number")\n')


async def test_elapsed_and_is_older_than() -> None:
    lines = await _run(
        """
set start = now() - 100
print time.elapsed(start) >= 100
print time.is_older_than(start, 50)
print time.is_older_than(start, 1000)
"""
    )
    assert lines == ["true", "true", "false"]


async def test_humanize_delegates_to_format_human_duration() -> None:
    lines = await _run("print time.humanize(3725)\n")
    assert lines == ["1h 2m 5s"]


async def test_now_iso_returns_an_iso8601_string() -> None:
    lines = await _run("print starts_with(time.now_iso(), \"20\")\n")
    assert lines == ["true"]


async def test_backoff_delay_doubles_per_attempt() -> None:
    lines = await _run(
        """
print time.backoff_delay(0, 1)
print time.backoff_delay(1, 1)
print time.backoff_delay(3, 1)
print time.backoff_delay(2, 5)
"""
    )
    assert lines == ["1", "2", "8", "20"]


async def test_time_it_returns_the_result_and_a_nonnegative_duration() -> None:
    lines = await _run(
        """
set timed = time.time_it(lambda(): 2 + 2)
print timed[0]
print timed[1] >= 0
"""
    )
    assert lines == ["4", "true"]
