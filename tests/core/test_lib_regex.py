from __future__ import annotations

from pathlib import Path

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_regex_module_lints_clean() -> None:
    source = (_REPO_ROOT / "lib" / "regex.nyx").read_text(encoding="utf-8")
    assert lint_source(source) == []


async def _run(body: str) -> list[str]:
    lines: list[str] = []
    source = 'import "lib/regex.nyx" as re\n' + body
    await run_script(source, load_config(), output=lines.append, base_dir=_REPO_ROOT)
    return lines


async def test_extract_ips_finds_dotted_quads() -> None:
    lines = await _run(
        'print re.extract_ips("server at 10.0.0.5 and 192.168.1.1 responded")\n'
    )
    assert lines == ["[10.0.0.5, 192.168.1.1]"]


async def test_extract_emails_finds_addresses() -> None:
    lines = await _run(
        'print re.extract_emails("contact admin@example.com or ops@corp.io")\n'
    )
    assert lines == ["[admin@example.com, ops@corp.io]"]


async def test_extract_urls_stops_at_whitespace() -> None:
    lines = await _run(
        'print re.extract_urls("see https://example.com/report and stop here")\n'
    )
    assert lines == ["[https://example.com/report]"]


async def test_matches_any_true_and_false() -> None:
    lines = await _run(
        """
print re.matches_any("hello world", ["nomatch", "wor"])
print re.matches_any("hello world", ["nomatch", "still no match"])
"""
    )
    assert lines == ["true", "false"]


async def test_quantifier_braces_survive_interpolation_when_doubled() -> None:
    # Regression: every NyxScript string literal is interpolated, so a
    # regex quantifier like {1,3} looks exactly like an {expr} span and
    # gets silently mangled unless the braces are doubled ({{1,3}}) — this
    # is exactly the pattern lib/regex.nyx's own extract_ips relies on.
    lines = await _run('print regex_match("aaa", "a{{2,3}}")\n')
    assert lines == ["true"]
