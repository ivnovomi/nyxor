from __future__ import annotations

from pathlib import Path

import pytest
from textual.widgets import Input, TextArea

from nyxor.plugins.tui.app import NyxorApp
from nyxor.plugins.tui.browser import NyxFileTree, ScriptBrowserScreen


def test_filter_paths_keeps_only_directories_and_nyx_files(tmp_path: Path) -> None:
    nyx_file = tmp_path / "audit.nyx"
    py_file = tmp_path / "script.py"
    subdir = tmp_path / "scripts"
    nyx_file.write_text("print 1\n")
    py_file.write_text("print(1)\n")
    subdir.mkdir()

    tree = NyxFileTree(tmp_path)
    filtered = {p.name for p in tree.filter_paths([nyx_file, py_file, subdir])}

    assert filtered == {"audit.nyx", "scripts"}


@pytest.mark.asyncio
async def test_up_dir_reroots_to_parent(tmp_path: Path) -> None:
    child = tmp_path / "child"
    child.mkdir()
    screen = ScriptBrowserScreen(child)

    app = NyxorApp()
    async with app.run_test() as pilot:
        await app.push_screen(screen)
        await pilot.pause()
        await pilot.pause()
        assert screen._root == child.resolve()

        screen.action_up_dir()
        await pilot.pause()
        await pilot.pause()
        assert screen._root == tmp_path.resolve()


@pytest.mark.asyncio
async def test_choosing_a_script_loads_it_into_the_editor(tmp_path: Path) -> None:
    script = tmp_path / "hello.nyx"
    script.write_text('print "hello from the browser"\n', encoding="utf-8")

    app = NyxorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("4")  # Script tab
        await pilot.pause()

        app.browse_for_script()
        await pilot.pause()
        assert isinstance(app.screen, ScriptBrowserScreen)

        app.screen.dismiss(script)
        await pilot.pause()

        assert app.query_one("#script-editor", TextArea).text == 'print "hello from the browser"\n'
        assert "hello.nyx" in app.query_one("#script-path", Input).value


@pytest.mark.asyncio
async def test_cancelling_the_browser_leaves_the_editor_untouched() -> None:
    app = NyxorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("4")
        await pilot.pause()

        before = app.query_one("#script-editor", TextArea).text
        app.browse_for_script()
        await pilot.pause()
        app.screen.dismiss(None)
        await pilot.pause()

        assert app.query_one("#script-editor", TextArea).text == before
