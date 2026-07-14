"""The NyxScript AST — what the parser produces and the interpreter/linter walk."""

from __future__ import annotations

from dataclasses import dataclass, field

# --- expressions ---------------------------------------------------------


@dataclass(frozen=True)
class Literal:
    value: object  # str (interpolated at eval time unless is_raw), int, float, or bool
    line: int
    is_raw: bool = False  # from r"..."/r'...' — no {expr} interpolation, no escapes


@dataclass(frozen=True)
class ListLiteral:
    items: list[Expr]
    line: int


@dataclass(frozen=True)
class DictLiteral:
    pairs: list[tuple[Expr, Expr]]
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


@dataclass(frozen=True)
class Call:
    """A function call: a plain name (``square(4)``) or a dotted one

    (``math.square(4)`` — a library member, or ``ui.confirm(...)``). The
    lexer already merges ``name.member`` into a single dotted IDENT token,
    so ``callee`` is just that string, split on ``.`` at call time.
    """

    callee: str
    args: list[Expr]
    line: int


@dataclass(frozen=True)
class Index:
    target: Expr
    index: Expr
    line: int


@dataclass(frozen=True)
class Slice:
    """``target[start:stop]`` — either bound may be omitted (``list[1:]``,

    ``list[:3]``, ``list[:]``). Works on lists and strings, same semantics
    as Python slicing.
    """

    target: Expr
    start: Expr | None
    stop: Expr | None
    line: int


@dataclass(frozen=True)
class Lambda:
    """``lambda(params): expr`` — an anonymous, single-expression function

    value. Unlike ``func``, a lambda captures a *snapshot* of every
    variable visible where it's defined (locals and globals both) at
    definition time — not a live reference, and not NyxScript's usual
    "no closures" rule for top-level functions. That's what makes
    ``filter(items, lambda(x): x > threshold)`` see ``threshold`` from the
    enclosing scope.
    """

    params: list[str]
    body: Expr
    line: int


@dataclass(frozen=True)
class Attr:
    """``expr.name`` where ``expr`` isn't a bare identifier (so the lexer's

    dotted-identifier merge doesn't apply) — e.g. ``result[0].module`` or
    a future ``some_call().field``. Plain ``lib.member``/``r.field`` still
    goes through :class:`VarRef` via that lexer merge; this node only
    exists for the postfix case.
    """

    target: Expr
    name: str
    line: int


Expr = (
    Literal
    | ListLiteral
    | DictLiteral
    | VarRef
    | UnaryOp
    | BinOp
    | Call
    | Index
    | Slice
    | Attr
    | Lambda
)

# --- statements ------------------------------------------------------------


@dataclass(frozen=True)
class SetStmt:
    name: str
    value: Expr
    line: int


@dataclass(frozen=True)
class IndexSetStmt:
    """``set NAME[index]... = expr`` — mutates a list or dict in place.

    ``target`` is the container expression (evaluated normally, so nested
    indexing like ``set d["a"]["b"] = 1`` works via the same postfix chain
    the parser already builds for reads).
    """

    target: Expr
    index: Expr
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
class WhileStmt:
    condition: Expr
    body: list[Stmt]
    line: int


@dataclass(frozen=True)
class BreakStmt:
    line: int


@dataclass(frozen=True)
class ContinueStmt:
    line: int


@dataclass(frozen=True)
class UnsafeStmt:
    """`unsafe` — self-enables python:/pip for the rest of this script,

    regardless of whether --unsafe was passed on the CLI.
    """

    line: int


@dataclass(frozen=True)
class FuncDef:
    name: str
    params: list[str]
    body: list[Stmt]
    line: int


@dataclass(frozen=True)
class ReturnStmt:
    value: Expr | None
    line: int


@dataclass(frozen=True)
class ImportStmt:
    path: Expr
    alias: str
    line: int


@dataclass(frozen=True)
class TryStmt:
    """``try: ... except VAR: ... end`` — catches a NyxScript runtime error.

    ``error_var`` holds the failed statement's error message (a string) for
    the duration of the ``except`` body only.
    """

    body: list[Stmt]
    error_var: str
    except_body: list[Stmt]
    line: int


@dataclass(frozen=True)
class ExprStmt:
    """A bare call used for its side effect, e.g. ``ui.confirm("...")`` on its own line."""

    value: Expr
    line: int


@dataclass(frozen=True)
class DocStmt:
    """A bare string literal used as a statement — a docstring.

    Purely documentation: a no-op at run time. By convention it's the first
    statement in a ``func`` body; :func:`function_docstring` is how callers
    (the interpreter, the LSP) pull it back out.
    """

    text: str
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
    | IndexSetStmt
    | PrintStmt
    | SleepStmt
    | AssertStmt
    | FailStmt
    | RunStmt
    | SaveStmt
    | IfStmt
    | ForeachStmt
    | WhileStmt
    | BreakStmt
    | ContinueStmt
    | FuncDef
    | ReturnStmt
    | ImportStmt
    | TryStmt
    | ExprStmt
    | DocStmt
    | PythonStmt
    | PipStmt
    | UnsafeStmt
)


@dataclass(frozen=True)
class Program:
    body: list[Stmt] = field(default_factory=list)


def function_docstring(body: list[Stmt]) -> str | None:
    """The docstring a function body starts with, if it has one."""
    if body and isinstance(body[0], DocStmt):
        return body[0].text
    return None
