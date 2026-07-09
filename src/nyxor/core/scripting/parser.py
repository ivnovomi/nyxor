"""A recursive-descent parser turning NyxScript tokens into an AST.

Expression precedence, loosest to tightest binding: ``or`` → ``and`` →
``not`` → comparisons (``== != < <= > >=``) → ``+ -`` → ``* /`` → unary
``-`` → primaries (literals, lists, parens, variables).
"""

from __future__ import annotations

import re
import textwrap

from nyxor.core.scripting.ast_nodes import (
    AssertStmt,
    BinOp,
    Expr,
    FailStmt,
    ForeachStmt,
    IfStmt,
    ListLiteral,
    Literal,
    PipStmt,
    PrintStmt,
    Program,
    PythonStmt,
    RunStmt,
    SaveStmt,
    SetStmt,
    SleepStmt,
    Stmt,
    UnaryOp,
    VarRef,
)
from nyxor.core.scripting.errors import ParseError
from nyxor.core.scripting.lexer import Token, tokenize

_COMPARISON_OPS = ("==", "!=", "<", "<=", ">", ">=")
_ADDITIVE_OPS = ("+", "-")
_MULTIPLICATIVE_OPS = ("*", "/")

_PYTHON_BLOCK_HEADER = re.compile(r"^python\s*:$")


def _extract_python_blocks(source: str) -> tuple[str, list[str]]:
    """Pull ``python: ... end`` blocks out of the source textually.

    NyxScript's own grammar can't tokenize arbitrary Python, so each block
    is replaced with a single ``pyblock N`` statement referencing its raw
    code by index — and every line the block occupied is preserved (as a
    blank line) so line numbers after it stay accurate.
    """
    lines = source.splitlines()
    out: list[str] = []
    blocks: list[str] = []
    i = 0
    n = len(lines)
    while i < n:
        if _PYTHON_BLOCK_HEADER.match(lines[i].strip()):
            header_line = i
            i += 1
            code_lines: list[str] = []
            while i < n and lines[i].strip() != "end":
                code_lines.append(lines[i])
                i += 1
            if i >= n:
                raise ParseError("'python' block is missing a matching 'end'", line=header_line + 1)
            blocks.append(textwrap.dedent("\n".join(code_lines)))
            out.append(f"pyblock {len(blocks) - 1}")
            out.extend("" for _ in code_lines)
            out.append("")  # the consumed 'end' line
            i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out), blocks


class Parser:
    def __init__(self, tokens: list[Token], python_blocks: list[str] | None = None) -> None:
        self._tokens = tokens
        self._pos = 0
        self._python_blocks = python_blocks or []

    # -- low-level helpers -------------------------------------------------

    def _peek(self, offset: int = 0) -> Token:
        index = min(self._pos + offset, len(self._tokens) - 1)
        return self._tokens[index]

    def _advance(self) -> Token:
        token = self._peek()
        self._pos += 1
        return token

    def _at_ident(self, *values: str) -> bool:
        token = self._peek()
        return token.type == "IDENT" and token.value in values

    def _expect_type(self, type_: str, what: str) -> Token:
        token = self._peek()
        if token.type != type_:
            raise ParseError(f"expected {what}, got {token.value!r}", line=token.line)
        return self._advance()

    def _expect_op(self, symbol: str) -> Token:
        token = self._peek()
        if token.type != symbol:
            raise ParseError(f"expected {symbol!r}, got {token.value!r}", line=token.line)
        return self._advance()

    def _expect_ident(self, value: str) -> Token:
        if not self._at_ident(value):
            token = self._peek()
            raise ParseError(f"expected {value!r}, got {token.value!r}", line=token.line)
        return self._advance()

    def _skip_newlines(self) -> None:
        while self._peek().type == "NEWLINE":
            self._advance()

    def _end_statement(self) -> None:
        if self._peek().type == "NEWLINE":
            self._advance()
        elif self._peek().type == "EOF":
            pass
        else:
            token = self._peek()
            raise ParseError(f"expected end of line, got {token.value!r}", line=token.line)

    # -- program / statements ----------------------------------------------

    def parse_program(self) -> Program:
        self._skip_newlines()
        body: list[Stmt] = []
        while self._peek().type != "EOF":
            body.append(self._parse_statement())
            self._skip_newlines()
        return Program(body=body)

    def _parse_block(self, enders: set[str]) -> list[Stmt]:
        self._skip_newlines()
        body: list[Stmt] = []
        while not self._at_ident(*enders) and self._peek().type != "EOF":
            body.append(self._parse_statement())
            self._skip_newlines()
        return body

    _STATEMENT_KEYWORDS = (
        "set",
        "if",
        "foreach",
        "run",
        "save",
        "print",
        "sleep",
        "assert",
        "fail",
        "pip",
        "pyblock",
    )

    def _parse_statement(self) -> Stmt:
        token = self._peek()
        if token.type != "IDENT" or token.value not in self._STATEMENT_KEYWORDS:
            raise ParseError(f"expected a statement, got {token.value!r}", line=token.line)
        return getattr(self, f"_parse_{token.value}")()  # type: ignore[no-any-return]

    def _parse_set(self) -> SetStmt:
        line = self._advance().line
        name = self._expect_type("IDENT", "a variable name").value
        self._expect_op("=")
        value = self.parse_expr()
        self._end_statement()
        return SetStmt(name=name, value=value, line=line)

    def _parse_if(self) -> IfStmt:
        line = self._advance().line
        condition = self.parse_expr()
        self._expect_op(":")
        self._end_statement()
        then_body = self._parse_block({"else", "end"})
        else_body: list[Stmt] = []
        if self._at_ident("else"):
            self._advance()
            self._expect_op(":")
            self._end_statement()
            else_body = self._parse_block({"end"})
        self._expect_ident("end")
        self._end_statement()
        return IfStmt(condition=condition, then_body=then_body, else_body=else_body, line=line)

    def _parse_foreach(self) -> ForeachStmt:
        line = self._advance().line
        var_name = self._expect_type("IDENT", "a loop variable").value
        self._expect_ident("in")
        iterable = self.parse_expr()
        self._expect_op(":")
        self._end_statement()
        body = self._parse_block({"end"})
        self._expect_ident("end")
        self._end_statement()
        return ForeachStmt(var_name=var_name, iterable=iterable, body=body, line=line)

    def _parse_run(self) -> RunStmt:
        line = self._advance().line
        module = self._expect_type("IDENT", "a module name").value
        target = self.parse_expr()
        var_name = None
        if self._at_ident("as"):
            self._advance()
            var_name = self._expect_type("IDENT", "a variable name").value
        self._end_statement()
        return RunStmt(module=module, target=target, var_name=var_name, line=line)

    def _parse_save(self) -> SaveStmt:
        line = self._advance().line
        var_name = self._expect_type("IDENT", "a variable name").value
        self._expect_ident("to")
        path = self.parse_expr()
        self._end_statement()
        return SaveStmt(var_name=var_name, path=path, line=line)

    def _parse_print(self) -> PrintStmt:
        line = self._advance().line
        value = self.parse_expr()
        self._end_statement()
        return PrintStmt(value=value, line=line)

    def _parse_sleep(self) -> SleepStmt:
        line = self._advance().line
        value = self.parse_expr()
        self._end_statement()
        return SleepStmt(value=value, line=line)

    def _parse_assert(self) -> AssertStmt:
        line = self._advance().line
        condition = self.parse_expr()
        message: Expr | None = None
        if self._peek().type == ",":
            self._advance()
            message = self.parse_expr()
        self._end_statement()
        return AssertStmt(condition=condition, message=message, line=line)

    def _parse_fail(self) -> FailStmt:
        line = self._advance().line
        message = self.parse_expr()
        self._end_statement()
        return FailStmt(message=message, line=line)

    def _parse_pip(self) -> PipStmt:
        line = self._advance().line
        package = self.parse_expr()
        self._end_statement()
        return PipStmt(package=package, line=line)

    def _parse_pyblock(self) -> PythonStmt:
        line = self._advance().line
        index_tok = self._expect_type("NUMBER", "a python block index")
        self._end_statement()
        index = int(index_tok.value)
        code = self._python_blocks[index] if index < len(self._python_blocks) else ""
        return PythonStmt(code=code, line=line)

    # -- expressions ---------------------------------------------------------

    def parse_expr(self) -> Expr:
        return self._parse_or()

    def _parse_or(self) -> Expr:
        left = self._parse_and()
        while self._at_ident("or"):
            line = self._advance().line
            left = BinOp("or", left, self._parse_and(), line)
        return left

    def _parse_and(self) -> Expr:
        left = self._parse_not()
        while self._at_ident("and"):
            line = self._advance().line
            left = BinOp("and", left, self._parse_not(), line)
        return left

    def _parse_not(self) -> Expr:
        if self._at_ident("not"):
            line = self._advance().line
            return UnaryOp("not", self._parse_not(), line)
        return self._parse_comparison()

    def _parse_comparison(self) -> Expr:
        left = self._parse_additive()
        if self._peek().type in _COMPARISON_OPS:
            token = self._advance()
            return BinOp(token.type, left, self._parse_additive(), token.line)
        return left

    def _parse_additive(self) -> Expr:
        left = self._parse_multiplicative()
        while self._peek().type in _ADDITIVE_OPS:
            token = self._advance()
            left = BinOp(token.type, left, self._parse_multiplicative(), token.line)
        return left

    def _parse_multiplicative(self) -> Expr:
        left = self._parse_unary()
        while self._peek().type in _MULTIPLICATIVE_OPS:
            token = self._advance()
            left = BinOp(token.type, left, self._parse_unary(), token.line)
        return left

    def _parse_unary(self) -> Expr:
        if self._peek().type == "-":
            line = self._advance().line
            return UnaryOp("-", self._parse_unary(), line)
        return self._parse_primary()

    def _parse_primary(self) -> Expr:
        token = self._peek()

        if token.type == "NUMBER":
            self._advance()
            value: float | int = float(token.value) if "." in token.value else int(token.value)
            return Literal(value, token.line)

        if token.type == "STRING":
            self._advance()
            return Literal(token.value, token.line)

        if token.type == "IDENT" and token.value == "true":
            self._advance()
            return Literal(True, token.line)
        if token.type == "IDENT" and token.value == "false":
            self._advance()
            return Literal(False, token.line)

        if token.type == "[":
            self._advance()
            items: list[Expr] = []
            if self._peek().type != "]":
                items.append(self.parse_expr())
                while self._peek().type == ",":
                    self._advance()
                    items.append(self.parse_expr())
            self._expect_op("]")
            return ListLiteral(items, token.line)

        if token.type == "(":
            self._advance()
            expr = self.parse_expr()
            self._expect_op(")")
            return expr

        if token.type == "IDENT":
            self._advance()
            return VarRef(token.value, token.line)

        raise ParseError(f"unexpected token {token.value!r}", line=token.line)


def parse(source: str) -> Program:
    """Tokenize and parse a full NyxScript source string."""
    transformed, python_blocks = _extract_python_blocks(source)
    return Parser(tokenize(transformed), python_blocks=python_blocks).parse_program()


def parse_expression(text: str, line: int = 1) -> Expr:
    """Parse a standalone expression (used for ``{...}`` string interpolation)."""
    return Parser(tokenize(text, start_line=line)).parse_expr()
