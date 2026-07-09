from __future__ import annotations

import pytest

from nyxor.plugins.tui.app import NyxorApp
from nyxor.plugins.tui.editor import MIN_COMPLETION_PREFIX, NyxScriptEditor


async def _type(pilot, text: str) -> None:
    keys = {" ": "space", ":": "colon", '"': "quotation_mark"}
    for ch in text:
        await pilot.press(keys.get(ch, ch))


@pytest.mark.asyncio
async def test_line_numbers_are_shown() -> None:
    app = NyxorApp()
    async with app.run_test():
        editor = app.query_one("#script-editor", NyxScriptEditor)
        assert editor.show_line_numbers is True


@pytest.mark.asyncio
async def test_short_prefixes_suggest_nothing() -> None:
    app = NyxorApp()
    async with app.run_test():
        editor = app.query_one("#script-editor", NyxScriptEditor)
        editor.text = "pr"
        editor.move_cursor((0, 2))
        _prefix, matches = editor.completion_context()
        assert matches == []


@pytest.mark.asyncio
async def test_prefix_at_the_minimum_length_suggests() -> None:
    app = NyxorApp()
    async with app.run_test():
        editor = app.query_one("#script-editor", NyxScriptEditor)
        assert MIN_COMPLETION_PREFIX == 3, "test below assumes a 3-char minimum"
        editor.text = "pri"
        editor.move_cursor((0, 3))
        _prefix, matches = editor.completion_context()
        assert "print" in matches


@pytest.mark.asyncio
async def test_enter_after_a_colon_indents_the_next_line() -> None:
    app = NyxorApp()
    async with app.run_test() as pilot:
        await pilot.press("4")
        await pilot.pause()
        editor = app.query_one("#script-editor", NyxScriptEditor)
        editor.text = ""
        editor.focus()
        await pilot.pause()

        await _type(pilot, "if true:")
        await pilot.press("enter")
        await pilot.pause()

        assert editor.text == "if true:\n    "


@pytest.mark.asyncio
async def test_end_snaps_back_to_the_enclosing_indent_on_enter() -> None:
    app = NyxorApp()
    async with app.run_test() as pilot:
        await pilot.press("4")
        await pilot.pause()
        editor = app.query_one("#script-editor", NyxScriptEditor)
        editor.text = ""
        editor.focus()
        await pilot.pause()

        await _type(pilot, "func square(x):")
        await pilot.press("enter")
        await _type(pilot, "return x * x")
        await pilot.press("enter")
        await _type(pilot, "end")
        await pilot.press("enter")
        await pilot.pause()

        assert editor.text == "func square(x):\n    return x * x\nend\n"


@pytest.mark.asyncio
async def test_backspace_in_leading_whitespace_deletes_a_full_indent_level() -> None:
    app = NyxorApp()
    async with app.run_test() as pilot:
        await pilot.press("4")
        await pilot.pause()
        editor = app.query_one("#script-editor", NyxScriptEditor)
        editor.focus()

        editor.text = " " * 8
        editor.move_cursor((0, 8))
        await pilot.pause()

        await pilot.press("backspace")
        await pilot.pause()
        assert editor.text == " " * 4

        await pilot.press("backspace")
        await pilot.pause()
        assert editor.text == ""


@pytest.mark.asyncio
async def test_backspace_aligns_to_the_previous_tab_stop() -> None:
    app = NyxorApp()
    async with app.run_test() as pilot:
        await pilot.press("4")
        await pilot.pause()
        editor = app.query_one("#script-editor", NyxScriptEditor)
        editor.focus()

        editor.text = " " * 6  # not a multiple of the 4-space indent width
        editor.move_cursor((0, 6))
        await pilot.pause()

        await pilot.press("backspace")
        await pilot.pause()
        assert editor.text == " " * 4


@pytest.mark.asyncio
async def test_backspace_on_real_text_still_deletes_one_character() -> None:
    app = NyxorApp()
    async with app.run_test() as pilot:
        await pilot.press("4")
        await pilot.pause()
        editor = app.query_one("#script-editor", NyxScriptEditor)
        editor.focus()

        editor.text = "print hello"
        editor.move_cursor((0, 11))
        await pilot.pause()

        await pilot.press("backspace")
        await pilot.pause()
        assert editor.text == "print hell"


@pytest.mark.asyncio
async def test_nested_blocks_indent_and_dedent_correctly() -> None:
    app = NyxorApp()
    async with app.run_test() as pilot:
        await pilot.press("4")
        await pilot.pause()
        editor = app.query_one("#script-editor", NyxScriptEditor)
        editor.text = ""
        editor.focus()
        await pilot.pause()

        for line in ["foreach x in items:", "if x:", "print x", "else:", "print 0", "end", "end"]:
            await _type(pilot, line)
            await pilot.press("enter")
        await pilot.pause()

        assert editor.text == (
            "foreach x in items:\n"
            "    if x:\n"
            "        print x\n"
            "    else:\n"
            "        print 0\n"
            "    end\n"
            "end\n"
        )
