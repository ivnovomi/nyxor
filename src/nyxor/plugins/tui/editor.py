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
from typing import ClassVar

from rich.style import Style
from textual.widgets import OptionList, TextArea
from textual.widgets.text_area import TextAreaTheme

from nyxor.core.scripting.lexer import KEYWORDS, tokenize
from nyxor.core.scripting.stdlib import MODULE_RUNNERS

NYX_THEME = TextAreaTheme(
    name="nyxor",
    syntax_styles={
        "keyword": Style(color="#b98cff", bold=True),
        "module": Style(color="#7ee7e1", bold=True),
        "string": Style(color="#f5d76e"),
        "comment": Style(color="#5b6a8c", italic=True),
        "number": Style(color="#ff9f43"),
        "boolean": Style(color="#ff9f43", bold=True),
        "operator": Style(color="#7f95b3"),
    },
)

_CONTROL_KEYWORDS = {"if", "else", "end", "foreach", "in", "as", "to", "and", "or", "not"}
_ACTION_KEYWORDS = {"set", "run", "save", "print", "sleep", "assert", "fail"}
_BOOL_KEYWORDS = {"true", "false"}

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")


def _highlight_line(text: str) -> list[tuple[int, int | None, str]]:
    """Tokenize a single NyxScript line into ``(start, end, style_name)`` spans."""
    spans: list[tuple[int, int | None, str]] = []
    try:
        tokens = tokenize(text)
    except Exception:
        return spans

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
            spans.append((start, end, "string"))
        elif token.type == "NUMBER":
            spans.append((start, start + len(token.value), "number"))
        elif token.type == "IDENT":
            if token.value in _BOOL_KEYWORDS:
                spans.append((start, start + len(token.value), "boolean"))
            elif token.value in _ACTION_KEYWORDS or token.value in _CONTROL_KEYWORDS:
                spans.append((start, start + len(token.value), "keyword"))
            elif token.value in MODULE_RUNNERS:
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

    _COMPLETION_WORDS: ClassVar[list[str]] = sorted(KEYWORDS | set(MODULE_RUNNERS))

    def on_mount(self) -> None:
        self.register_theme(NYX_THEME)
        self.theme = "nyxor"
        self._build_highlight_map()

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
        if not prefix or (col < len(line) and re.match(r"[A-Za-z0-9_.]", line[col])):
            return "", []

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
