"""A NyxScript-aware ``TextArea``: syntax highlighting + inline autocomplete.

Textual's `TextArea` normally gets syntax highlighting from a compiled
tree-sitter grammar (via `language=`). NyxScript doesn't have one, so this
widget builds the highlight map itself from our own lexer instead of
tree-sitter, and reuses `TextArea`'s built-in ghost-text suggestion
mechanism (the same one used for shell-style inline completions) for
autocomplete — accept with the Right arrow key.

Both hooks (`_build_highlight_map`, `update_suggestion`) are the documented
extension points `TextArea` itself calls internally; if a future Textual
version renames them, this widget just falls back to plain, uncolored
editing rather than crashing.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from rich.style import Style
from textual import events
from textual.widgets import OptionList, TextArea
from textual.widgets.text_area import TextAreaTheme

from nyxor.core.scripting.builtins import BUILTIN_FUNCTIONS
from nyxor.core.scripting.lexer import KEYWORDS, tokenize
from nyxor.core.scripting.sockets import SOCKET_FUNCTIONS
from nyxor.core.scripting.stdlib import MODULE_RUNNERS
from nyxor.core.scripting.ui import UI_FUNCTIONS
from nyxor.lsp.analysis import (
    parse_best_effort,
    resolve_import_path,
    scan_imports,
    top_level_functions,
)

NYX_THEME = TextAreaTheme(
    name="nyxor",
    syntax_styles={
        "keyword": Style(color="#b98cff", bold=True),
        "module": Style(color="#7ee7e1", bold=True),
        "string": Style(color="#f5d76e"),
        "docstring": Style(color="#8fd6ff", italic=True),
        "comment": Style(color="#5b6a8c", italic=True),
        "number": Style(color="#ff9f43"),
        "boolean": Style(color="#ff9f43", bold=True),
        "operator": Style(color="#7f95b3"),
    },
)

_CONTROL_KEYWORDS = {
    "if",
    "else",
    "end",
    "foreach",
    "while",
    "break",
    "continue",
    "try",
    "except",
    "in",
    "as",
    "to",
    "and",
    "or",
    "not",
    "return",
}
_ACTION_KEYWORDS = {
    "set",
    "run",
    "save",
    "print",
    "sleep",
    "assert",
    "fail",
    "func",
    "lambda",
    "import",
    "unsafe",
}
_BOOL_KEYWORDS = {"true", "false"}

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")

#: Don't suggest anything until the user's typed at least this many
#: characters — completions firing after a single keystroke is what makes
#: an editor feel like it's fighting you instead of helping.
MIN_COMPLETION_PREFIX = 3

#: Lines whose *entire* content, once complete, belongs one indent level
#: back from wherever the cursor currently sits.
_DEDENT_LINES = frozenset({"end", "else", "else:"})


def _highlight_line(text: str) -> list[tuple[int, int | None, str]]:
    """Tokenize a single NyxScript line into ``(start, end, style_name)`` spans."""
    spans: list[tuple[int, int | None, str]] = []
    try:
        tokens = tokenize(text)
    except Exception:
        return spans

    # A line whose only content is a string literal is a docstring (see the
    # grammar's `DocStmt`) — style it distinctly from an ordinary string.
    real_tokens = [t for t in tokens if t.type not in ("NEWLINE", "EOF")]
    is_docstring_line = len(real_tokens) == 1 and real_tokens[0].type == "STRING"

    for token in tokens:
        if token.type in ("NEWLINE", "EOF"):
            continue
        start = token.col
        if token.type == "STRING":
            # Strings may contain escapes, so re-measure against the raw source
            # by scanning forward from the opening quote to its closing quote.
            quote = text[start] if start < len(text) else '"'
            end = start + 1
            while end < len(text) and text[end] != quote:
                end += 2 if text[end] == "\\" else 1
            end = min(end + 1, len(text))
            spans.append((start, end, "docstring" if is_docstring_line else "string"))
        elif token.type == "RAWSTRING":
            # Same idea, but the quote sits one character later (after the
            # leading `r`), and only a backslash right before the closing
            # quote is special — everything else in a raw string is literal.
            quote = text[start + 1] if start + 1 < len(text) else '"'
            end = start + 2
            while end < len(text) and text[end] != quote:
                if text[end] == "\\" and end + 1 < len(text) and text[end + 1] == quote:
                    end += 2
                else:
                    end += 1
            end = min(end + 1, len(text))
            spans.append((start, end, "string"))
        elif token.type == "NUMBER":
            spans.append((start, start + len(token.value), "number"))
        elif token.type == "IDENT":
            if token.value in _BOOL_KEYWORDS:
                spans.append((start, start + len(token.value), "boolean"))
            elif token.value in _ACTION_KEYWORDS or token.value in _CONTROL_KEYWORDS:
                spans.append((start, start + len(token.value), "keyword"))
            elif (
                token.value in MODULE_RUNNERS
                or token.value in BUILTIN_FUNCTIONS
                or (token.value.startswith("ui.") and token.value[3:] in UI_FUNCTIONS)
                or (token.value.startswith("socket.") and token.value[7:] in SOCKET_FUNCTIONS)
            ):
                spans.append((start, start + len(token.value), "module"))
        elif token.type in ("=", "==", "!=", "<", "<=", ">", ">=", "+", "-", "*", "/"):
            spans.append((start, start + len(token.value), "operator"))

    # Comments aren't tokens (the lexer strips them); find them separately.
    in_string = False
    quote = ""
    i = 0
    while i < len(text):
        ch = text[i]
        if in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                in_string = False
            i += 1
            continue
        if ch in "'\"":
            in_string = True
            quote = ch
        elif ch == "#":
            spans.append((i, None, "comment"))
            break
        i += 1

    return spans


class CompletionPopup(OptionList):
    """A small floating box of completion candidates.

    Positioned by the app via `absolute_offset` (the same mechanism Textual
    uses for tooltips), right under the editor's cursor. It never takes
    keyboard focus — the editor keeps it, so typing isn't interrupted —
    but it still receives clicks, so an item can be picked with the mouse.
    Keyboard users accept the top suggestion with the → arrow (ghost text).
    """

    can_focus = False

    DEFAULT_CSS = """
    CompletionPopup {
        layer: popup;
        width: 34;
        max-height: 8;
        border: round #7c3aed;
        background: #10141f;
        display: none;
    }
    """


class NyxScriptEditor(TextArea):
    """A `TextArea` pre-wired with NyxScript highlighting and completion."""

    _COMPLETION_WORDS: ClassVar[list[str]] = sorted(
        KEYWORDS
        | set(MODULE_RUNNERS)
        | set(BUILTIN_FUNCTIONS)
        | {f"ui.{name}" for name in UI_FUNCTIONS}
        | {f"socket.{name}" for name in SOCKET_FUNCTIONS}
    )

    def on_mount(self) -> None:
        self.register_theme(NYX_THEME)
        self.theme = "nyxor"
        self.show_line_numbers = True
        self._build_highlight_map()

    def _indent_unit(self) -> str:
        return "\t" if self.indent_type == "tabs" else " " * self.indent_width

    def action_delete_left(self) -> None:
        """Backspace inside leading whitespace deletes a whole indent level

        (up to the previous tab stop) instead of one space at a time — the
        indentation is spaces under the hood (`indent_type == "spaces"`),
        but it should behave like it was a single tab character either way.
        """
        if self.read_only or not self.selection.is_empty or self.indent_type == "tabs":
            super().action_delete_left()
            return

        row, col = self.cursor_location
        line = self.document.get_line(row)
        before_cursor = line[:col]

        unit_width = self.indent_width
        if col > 0 and before_cursor == " " * col and unit_width > 0:
            remainder = col % unit_width
            delete_count = min(remainder or unit_width, col)
            self.delete((row, col - delete_count), (row, col))
            return

        super().action_delete_left()

    async def _on_key(self, event: events.Key) -> None:
        if not self.read_only and event.key == "enter":
            event.stop()
            event.prevent_default()
            try:
                self._auto_indent_newline()
            except Exception:
                self.insert("\n")  # never let a broken heuristic eat a keystroke
            return
        await super()._on_key(event)

    def _auto_indent_newline(self) -> None:
        """Continue the current line's indentation onto the new one — deeper

        after a line ending in ``:``, one level back for a line that's just
        ``end``/``else``/``else:`` (which also gets snapped back into place
        first, in case it was still sitting at the body's indent level).
        """
        row, col = self.cursor_location
        line = self.document.get_line(row)
        indent_len = len(line) - len(line.lstrip(" \t"))
        indent = line[:indent_len]
        stripped = line.strip()
        unit = self._indent_unit()

        is_dedent_line = stripped in _DEDENT_LINES or (
            stripped.startswith("except ") and stripped.endswith(":")
        )
        if is_dedent_line and len(indent) >= len(unit):
            target_indent = indent[: -len(unit)]
            if target_indent != indent:
                new_line = target_indent + line[indent_len:]
                self.replace(new_line, (row, 0), (row, len(line)))
                col = max(col - (len(indent) - len(target_indent)), len(target_indent))
                indent = target_indent
                line = new_line

        before_cursor = line[:col].strip()
        next_indent = indent + unit if before_cursor.endswith(":") else indent
        self.move_cursor((row, col))
        self.insert("\n" + next_indent)

    def _build_highlight_map(self) -> None:
        """Populate ``self._highlights`` from our own lexer (no tree-sitter)."""
        try:
            self._line_cache.clear()
            highlights = self._highlights
            highlights.clear()
            for row in range(self.document.line_count):
                line_text = self.document.get_line(row)
                highlights[row] = _highlight_line(line_text)
            self.refresh()
        except Exception:
            pass  # Never let cosmetic highlighting break the editor.

    def _on_text_area_changed(self, event: TextArea.Changed) -> None:
        self._build_highlight_map()

    def _known_variables(self) -> set[str]:
        names: set[str] = set()
        for pattern in (r"\bset\s+(\w+)\s*=", r"\bforeach\s+(\w+)\s+in\b", r"\bas\s+(\w+)\b"):
            names.update(re.findall(pattern, self.text))
        return names

    def _imported_functions(self) -> dict[str, list[str]]:
        """Alias -> sorted function names for every `import "..." as alias`

        in the buffer that resolves to a real, parseable .nyx file — so
        typing `asset.` offers `by_kind`, `kinds`, etc. instead of nothing,
        the same dynamic resolution `nyx script lsp` does for editors that
        talk LSP. Resolved against the current working directory, matching
        how the interpreter itself resolves imports (never relative to the
        editor's own open file).

        This runs on every keystroke (see ``completion_context``), so each
        imported file's read + parse is cached by path and invalidated on
        mtime change — otherwise typing anywhere in a script with imports
        would re-read and re-parse every one of them per character typed.
        """
        cache: dict[Path, tuple[float, list[str]]] | None = getattr(self, "_import_fn_cache", None)
        if cache is None:
            cache = {}
            self._import_fn_cache = cache

        out: dict[str, list[str]] = {}
        for alias, path in scan_imports(self.text).items():
            target = resolve_import_path(Path.cwd(), path)
            if not target.is_file():
                continue
            try:
                mtime = target.stat().st_mtime
            except OSError:
                continue

            cached = cache.get(target)
            if cached is not None and cached[0] == mtime:
                out[alias] = cached[1]
                continue

            try:
                content = target.read_text(encoding="utf-8")
                lib_program = parse_best_effort(content)
            except (OSError, UnicodeDecodeError):
                lib_program = None

            # Cache the result either way — including a syntax error in the
            # imported file (lib_program is None) — or an editor actively
            # mid-edit on a broken import would re-read and re-parse it on
            # every single keystroke, defeating the point of this cache.
            functions = sorted(top_level_functions(lib_program)) if lib_program else []
            cache[target] = (mtime, functions)
            out[alias] = functions
        return out

    def completion_context(self) -> tuple[str, list[str]]:
        """Return ``(prefix, matches)`` for the word under the cursor, if any.

        Empty prefix / no matches means "don't show anything" — used by both
        the ghost-text suggestion and the app's floating completion box.
        """
        try:
            row, col = self.cursor_location
            line = self.document.get_line(row)
        except Exception:
            return "", []

        prefix_match = re.search(r"[A-Za-z0-9_.]*$", line[:col])
        prefix = prefix_match.group(0) if prefix_match else ""

        # Don't suggest mid-word (e.g. cursor inside "fore|ach") — only at the tail.
        # And don't suggest at all until there's enough typed to actually narrow
        # things down; firing after one keystroke is just noise.
        if len(prefix) < MIN_COMPLETION_PREFIX or (
            col < len(line) and re.match(r"[A-Za-z0-9_.]", line[col])
        ):
            return "", []

        alias = prefix.rpartition(".")[0] if "." in prefix else ""
        if alias == "ui":
            candidates = [f"ui.{name}" for name in sorted(UI_FUNCTIONS)]
        elif alias == "socket":
            candidates = [f"socket.{name}" for name in sorted(SOCKET_FUNCTIONS)]
        elif alias and alias in (imported := self._imported_functions()):
            candidates = [f"{alias}.{name}" for name in imported[alias]]
        else:
            candidates = sorted(self._COMPLETION_WORDS + sorted(self._known_variables()))

        matches = [c for c in candidates if c.startswith(prefix) and c != prefix]
        return prefix, matches

    def update_suggestion(self) -> None:
        """Show a ghost-text completion for the word the cursor is inside."""
        _prefix, matches = self.completion_context()
        self.suggestion = matches[0][len(_prefix) :] if matches else ""

    def insert_completion(self, word: str) -> None:
        """Replace the current word-prefix at the cursor with ``word``."""
        prefix, _matches = self.completion_context()
        if prefix and word.startswith(prefix):
            self.insert(word[len(prefix) :])
        else:
            self.insert(word)
