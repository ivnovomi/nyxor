"""The NyxScript AST — what the parser produces and the interpreter/linter walk."""

from __future__ import annotations

from dataclasses import dataclass, field

# --- expressions ---------------------------------------------------------


@dataclass(frozen=True)
class Literal:
    value: object  # str (raw, interpolated at eval time), int, float, or bool
    line: int


@dataclass(frozen=True)
class ListLiteral:
    items: list[Expr]
    line: int


@dataclass(frozen=True)
class VarRef:
    name: str
    line: int


@dataclass(frozen=True)
class UnaryOp:
    op: str  # "-" | "not"
    operand: Expr
    line: int


@dataclass(frozen=True)
class BinOp:
    op: str  # "+" "-" "*" "/" "==" "!=" "<" "<=" ">" ">=" "and" "or"
    left: Expr
    right: Expr
    line: int


Expr = Literal | ListLiteral | VarRef | UnaryOp | BinOp

# --- statements ------------------------------------------------------------


@dataclass(frozen=True)
class SetStmt:
    name: str
    value: Expr
    line: int


@dataclass(frozen=True)
class PrintStmt:
    value: Expr
    line: int


@dataclass(frozen=True)
class SleepStmt:
    value: Expr
    line: int


@dataclass(frozen=True)
class AssertStmt:
    condition: Expr
    message: Expr | None
    line: int


@dataclass(frozen=True)
class FailStmt:
    message: Expr
    line: int


@dataclass(frozen=True)
class RunStmt:
    module: str
    target: Expr
    var_name: str | None
    line: int


@dataclass(frozen=True)
class SaveStmt:
    var_name: str
    path: Expr
    line: int


@dataclass(frozen=True)
class IfStmt:
    condition: Expr
    then_body: list[Stmt]
    else_body: list[Stmt]
    line: int


@dataclass(frozen=True)
class ForeachStmt:
    var_name: str
    iterable: Expr
    body: list[Stmt]
    line: int


@dataclass(frozen=True)
class PythonStmt:
    """A ``python: ... end`` block — raw Python, only runs with ``unsafe=True``."""

    code: str
    line: int


@dataclass(frozen=True)
class PipStmt:
    """A ``pip EXPR`` statement — installs a package, only runs with ``unsafe=True``."""

    package: Expr
    line: int


Stmt = (
    SetStmt
    | PrintStmt
    | SleepStmt
    | AssertStmt
    | FailStmt
    | RunStmt
    | SaveStmt
    | IfStmt
    | ForeachStmt
    | PythonStmt
    | PipStmt
)


@dataclass(frozen=True)
class Program:
    body: list[Stmt] = field(default_factory=list)
