from __future__ import annotations

from pathlib import Path

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script
from nyxor.core.scripting.errors import RuntimeScriptError

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULES = ("hash", "csv")


def test_new_lib_modules_lint_clean() -> None:
    for name in _MODULES:
        source = (_REPO_ROOT / "lib" / f"{name}.nyx").read_text(encoding="utf-8")
        assert lint_source(source) == [], f"lib/{name}.nyx has lint issues"


async def _run(body: str) -> list[str]:
    lines: list[str] = []
    imports = "".join(f'import "lib/{name}.nyx" as {name}\n' for name in _MODULES)
    await run_script(imports + body, load_config(), output=lines.append, base_dir=_REPO_ROOT)
    return lines


# ---------- sha256()/md5() builtins ----------


async def test_sha256_matches_a_known_digest() -> None:
    lines = await _run('print sha256("hello")\n')
    assert lines == ["2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"]


async def test_md5_matches_a_known_digest() -> None:
    lines = await _run('print md5("hello")\n')
    assert lines == ["5d41402abc4b2a76b9719d911017c592"]


async def test_sha256_is_deterministic_and_input_sensitive() -> None:
    lines = await _run(
        """
print sha256("a") == sha256("a")
print sha256("a") == sha256("b")
"""
    )
    assert lines == ["true", "false"]


async def test_sha256_rejects_wrong_arity() -> None:
    with pytest.raises(RuntimeScriptError, match="sha256"):
        await _run('print sha256("a", "b")\n')


# ---------- lib/hash.nyx ----------


async def test_short_hash_truncates_the_full_digest() -> None:
    lines = await _run('print hash.short_hash("hello", 8)\n')
    assert lines == ["2cf24dba"]


async def test_fingerprint_is_order_sensitive() -> None:
    lines = await _run(
        """
print hash.fingerprint(["a", "b"]) == hash.fingerprint(["a", "b"])
print hash.fingerprint(["a", "b"]) == hash.fingerprint(["b", "a"])
"""
    )
    assert lines == ["true", "false"]


async def test_has_changed_detects_a_difference() -> None:
    lines = await _run(
        """
set original = sha256("x")
print hash.has_changed(original, "x")
print hash.has_changed(original, "y")
"""
    )
    assert lines == ["false", "true"]


# ---------- lib/csv.nyx ----------


async def test_parse_csv_splits_simple_rows() -> None:
    lines = await _run('print csv.parse_csv("a,b,c\\n1,2,3\\n")\n')
    assert lines == ["[[a, b, c], [1, 2, 3]]"]


async def test_parse_csv_handles_a_quoted_comma() -> None:
    lines = await _run('print csv.parse_csv("name,note\\nAlice,\\"hi, there\\"\\n")\n')
    assert lines == ["[[name, note], [Alice, hi, there]]"]


async def test_parse_csv_handles_an_escaped_quote() -> None:
    lines = await _run('print csv.parse_csv("note\\n\\"she said \\"\\"hey\\"\\"\\"\\n")\n')
    assert lines == ['[[note], [she said "hey"]]']


async def test_parse_csv_handles_a_trailing_row_without_a_newline() -> None:
    lines = await _run('print csv.parse_csv("a,b\\n1,2")\n')
    assert lines == ["[[a, b], [1, 2]]"]


async def test_to_csv_quotes_fields_that_need_it() -> None:
    lines = await _run('print csv.to_csv([["a", "has, comma"], ["b", "has \\"quote\\""]])\n')
    assert lines == ['a,"has, comma"\nb,"has ""quote"""']


async def test_csv_round_trips_through_parse_and_write() -> None:
    lines = await _run(
        """
set original = [["name", "note"], ["Alice", "hi, there"], ["Bob", "she said \\"hey\\""]]
set text = csv.to_csv(original)
set parsed = csv.parse_csv(text)
print parsed == original
"""
    )
    assert lines == ["true"]
