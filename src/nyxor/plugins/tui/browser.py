"""A visual file browser for picking a `.nyx` script — the Script tab's
"Browse…" button pushes this instead of making people type a path by hand.

Built on Textual's `DirectoryTree`, filtered to directories and `.nyx`
files. Navigating *up* past the tree's root isn't something `DirectoryTree`
supports on its own (it only ever expands downward), so "up a level"
re-roots the whole tree at the parent directory instead.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Label


class NyxFileTree(DirectoryTree):
    """A `DirectoryTree` that only shows directories and `.nyx` files."""

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [path for path in paths if path.is_dir() or path.suffix == ".nyx"]


class ScriptBrowserScreen(ModalScreen[Path | None]):
    """Pick a `.nyx` file. Dismisses with the chosen path, or `None` on cancel."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=True),
        Binding("backspace", "up_dir", "Up a level", show=True),
    ]

    DEFAULT_CSS = """
    ScriptBrowserScreen {
        align: center middle;
    }
    #browser-panel {
        width: 72;
        height: 28;
        border: round #7c3aed;
        background: #10141f;
        padding: 1 2;
    }
    #browser-title {
        color: #7ee7e1;
        text-style: bold;
        margin-bottom: 1;
    }
    #browser-path {
        color: #8b93a7;
        margin-bottom: 1;
    }
    #browser-tree {
        height: 1fr;
        border: round #2a3550;
        background: #0b0e14;
    }
    #browser-toolbar {
        height: auto;
        margin-top: 1;
        align: right middle;
    }
    #browser-toolbar Button {
        margin-left: 1;
    }
    """

    def __init__(self, start_dir: Path) -> None:
        super().__init__()
        self._root = start_dir.resolve()

    def compose(self) -> ComposeResult:
        with Vertical(id="browser-panel"):
            yield Label("Open a NyxScript file", id="browser-title")
            yield Label(str(self._root), id="browser-path")
            yield NyxFileTree(self._root, id="browser-tree")
            with Horizontal(id="browser-toolbar"):
                yield Button("Up ⬆", id="browser-up")
                yield Button("Cancel", id="browser-cancel")

    def on_mount(self) -> None:
        self.query_one("#browser-tree", NyxFileTree).focus()

    def _reroot(self, new_root: Path) -> None:
        self._root = new_root.resolve()
        self.query_one("#browser-path", Label).update(str(self._root))
        # Reassigning `.path` (a reactive) makes DirectoryTree repopulate
        # itself from the new root automatically — see its `watch_path`.
        self.query_one("#browser-tree", NyxFileTree).path = self._root

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "browser-up":
            self.action_up_dir()
        elif event.button.id == "browser-cancel":
            self.action_cancel()

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_up_dir(self) -> None:
        parent = self._root.parent
        if parent != self._root:
            self._reroot(parent)

    def on_directory_tree_directory_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        # A double-click/Enter on a directory node descends into it, mirroring
        # "Up" — makes deep navigation possible without leaving the keyboard.
        self._reroot(event.path)

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        self.dismiss(event.path)
