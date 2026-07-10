from __future__ import annotations

from rich.console import Console
from rich.markup import escape as escape_markup


def test_console_print_with_markup_true_eats_bracketed_script_output() -> None:
    """Pins the bug: Rich treats a NyxScript-printed list/dict's "[...]" as a

    style tag by default, silently dropping its contents. `nyx script
    run`/`repl` print raw script output through `emit()`, which must not
    do this — see the markup=False fix in plugins/script/plugin.py and the
    escape_markup() fix in plugins/tui/app.py.
    """
    console = Console(record=True, width=80)
    console.print("[a, b, c]")
    assert "[a, b, c]" not in console.export_text()


def test_console_print_with_markup_false_preserves_a_literal_list() -> None:
    console = Console(record=True, width=80)
    console.print("[a, b, c]", markup=False)
    assert "[a, b, c]" in console.export_text()


def test_escape_markup_preserves_a_literal_list_under_markup_true() -> None:
    console = Console(record=True, width=80)
    console.print(escape_markup("[a, b, c]"))
    assert "[a, b, c]" in console.export_text()
