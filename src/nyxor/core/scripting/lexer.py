"""Tokenizer for NyxScript.

Turns source text into a flat stream of :class:`Token` objects, including
an explicit ``NEWLINE`` token at the end of every line that produced at
least one other token. The parser treats statements as newline-terminated,
so it never has to reason about raw line numbers itself.
"""

from __future__ import annotations

from dataclasses import dataclass

from nyxor.core.scripting.errors import LexError

KEYWORDS = frozenset(
    {
        "set",
        "if",
        "else",
        "end",
        "foreach",
        "while",
        "break",
        "continue",
        "in",
        "run",
        "as",
        "to",
        "save",
        "print",
        "sleep",
        "assert",
        "fail",
        "pip",
        "pyblock",
        "unsafe",
        "func",
        "return",
        "import",
        "try",
        "except",
        "lambda",
        "true",
        "false",
        "and",
        "or",
        "not",
    }
)

_TWO_CHAR_OPS = {"==": "==", "!=": "!=", "<=": "<=", ">=": ">="}
_ONE_CHAR_OPS = set("=<>+-*/:()[]{},.")
_ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "'": "'"}


@dataclass(frozen=True)
class Token:
    type: str  # "IDENT" | "NUMBER" | "STRING" | "NEWLINE" | "EOF" | an operator symbol
    value: str
    line: int
    col: int

    def is_keyword(self, *keywords: str) -> bool:
        return self.type == "IDENT" and self.value in keywords


def _is_ident_start(ch: str) -> bool:
    return ch.isalpha() or ch == "_"


def _is_ident_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def tokenize(source: str, start_line: int = 1) -> list[Token]:
    tokens: list[Token] = []
    line = start_line
    i = 0
    n = len(source)
    line_has_token = False

    while i < n:
        ch = source[i]

        if ch == "\n":
            if line_has_token:
                tokens.append(Token("NEWLINE", "\\n", line, i))
                line_has_token = False
            line += 1
            i += 1
            continue

        if ch in " \t\r":
            i += 1
            continue

        if ch == "#":
            while i < n and source[i] != "\n":
                i += 1
            continue

        col = i

        if ch in "'\"":
            quote = ch
            i += 1
            chars: list[str] = []
            closed = False
            while i < n:
                c = source[i]
                if c == "\n":
                    break
                if c == "\\" and i + 1 < n:
                    nxt = source[i + 1]
                    # An unrecognized escape (not in _ESCAPES) keeps *both*
                    # characters — "\w" stays "\w", matching Python's own
                    # behavior for an unknown escape in a string literal.
                    # Silently dropping the backslash (the old behavior)
                    # made regex patterns like "\d+"/"\w+" unwritable: the
                    # backslash the pattern actually needs would vanish
                    # before the regex engine ever saw it.
                    chars.append(_ESCAPES.get(nxt, "\\" + nxt))
                    i += 2
                    continue
                if c == quote:
                    closed = True
                    i += 1
                    break
                chars.append(c)
                i += 1
            if not closed:
                raise LexError(f"unterminated string starting at column {col + 1}", line=line)
            tokens.append(Token("STRING", "".join(chars), line, col))
            line_has_token = True
            continue

        if ch.isdigit():
            start = i
            seen_dot = False
            while i < n and (source[i].isdigit() or (source[i] == "." and not seen_dot)):
                if source[i] == ".":
                    seen_dot = True
                i += 1
            tokens.append(Token("NUMBER", source[start:i], line, col))
            line_has_token = True
            continue

        if _is_ident_start(ch):
            start = i
            i += 1
            while i < n and _is_ident_char(source[i]):
                i += 1
            # allow dotted paths for module names, e.g. network.discover
            while i < n and source[i] == "." and i + 1 < n and _is_ident_start(source[i + 1]):
                i += 1
                while i < n and _is_ident_char(source[i]):
                    i += 1
            tokens.append(Token("IDENT", source[start:i], line, col))
            line_has_token = True
            continue

        two = source[i : i + 2]
        if two in _TWO_CHAR_OPS:
            tokens.append(Token(two, two, line, col))
            i += 2
            line_has_token = True
            continue

        if ch in _ONE_CHAR_OPS:
            tokens.append(Token(ch, ch, line, col))
            i += 1
            line_has_token = True
            continue

        raise LexError(f"unexpected character {ch!r}", line=line)

    if line_has_token:
        tokens.append(Token("NEWLINE", "\\n", line, len(source)))
    tokens.append(Token("EOF", "", line, len(source)))
    return tokens
