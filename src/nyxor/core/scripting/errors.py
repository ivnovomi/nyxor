"""NyxScript's exception hierarchy — every error carries a source line so
the CLI and TUI can point straight at the offending statement."""

from __future__ import annotations

from nyxor.core.errors import NyxorError


class ScriptError(NyxorError):
    """Base class for all NyxScript lexing, parsing, and runtime errors.

    ``reason`` is the bare message (what a linter would show next to a line
    number it already knows); ``message`` (set on the base class) includes
    the ``line N:`` prefix, for contexts — like a bare traceback — that only
    have the exception to work with.
    """

    def __init__(self, message: str, *, line: int | None = None) -> None:
        self.line = line
        self.reason = message
        located = f"line {line}: {message}" if line is not None else message
        super().__init__(located)


class LexError(ScriptError):
    """Raised when the source contains a character the lexer can't tokenize."""


class ParseError(ScriptError):
    """Raised when the token stream doesn't match the grammar."""


class RuntimeScriptError(ScriptError):
    """Raised while executing an otherwise well-formed script."""
