"""Static analysis for NyxScript, run before (or instead of) execution.

Catches the mistakes that would otherwise only surface partway through a
live run against real infrastructure: undefined variables (including
inside ``"{...}"`` string interpolation), unknown ``run`` modules and
unknown function calls (both with a "did you mean" suggestion), stray
``break``/``continue``/``return``, and empty control-flow bodies. It never
executes anything — no network access, no side effects.

One deliberate limitation: importing a ``.nyx`` library (``import "x.nyx"
as lib``) isn't followed cross-file — the linter only has the source text
it was given, not a filesystem to resolve paths against. ``lib`` is
registered as a defined name so ``lib.member(...)`` calls don't false-
positive on the module name itself; the interpreter still catches a
genuinely missing member at run time.
"""

from __future__ import annotations

import contextlib
import difflib
from dataclasses import dataclass

from nyxor.core.scripting.ast_nodes import (
    AssertStmt,
    Attr,
    BinOp,
    BreakStmt,
    Call,
    ContinueStmt,
    DictLiteral,
    DocStmt,
    Expr,
    ExprStmt,
    FailStmt,
    ForeachStmt,
    FuncDef,
    IfStmt,
    ImportStmt,
    Index,
    IndexSetStmt,
    Lambda,
    ListLiteral,
    Literal,
    PipStmt,
    PrintStmt,
    Program,
    PythonStmt,
    ReturnStmt,
    RunStmt,
    SaveStmt,
    SetStmt,
    SleepStmt,
    Slice,
    Stmt,
    TryStmt,
    UnaryOp,
    VarRef,
    WhileStmt,
)
from nyxor.core.scripting.builtins import BUILTIN_FUNCTIONS, HIGHER_ORDER_FUNCTIONS
from nyxor.core.scripting.errors import ScriptError
from nyxor.core.scripting.parser import parse, parse_expression
from nyxor.core.scripting.stdlib import MODULE_RUNNERS
from nyxor.core.scripting.ui import UI_FUNCTIONS

#: Sentinel added to a scope's "defined" set once a `python:` block has run in
#: it — from that point on we can't know what variables exist, so undefined-
#: variable checks are suppressed for the rest of that scope (not a valid
#: NyxScript identifier, so it never collides with a real variable name).
_PERMISSIVE = "*"


@dataclass(frozen=True)
class LintIssue:
    severity: str  # "error" | "warning"
    line: int
    message: str

    def __str__(self) -> str:
        return f"line {self.line}: {self.message}"


def _interpolated_exprs(raw: str, line: int) -> list[Expr]:
    """Best-effort extraction of ``{expr}`` spans from a string literal.

    Malformed interpolation is silently skipped here — the interpreter
    raises a proper error for it at runtime, and the linter's job is to
    catch what it can without needing the source to be perfectly valid.
    """
    exprs: list[Expr] = []
    i = 0
    n = len(raw)
    while i < n:
        ch = raw[i]
        if ch == "{" and i + 1 < n and raw[i + 1] == "{":
            i += 2
            continue
        if ch == "}" and i + 1 < n and raw[i + 1] == "}":
            i += 2
            continue
        if ch == "{":
            end = raw.find("}", i + 1)
            if end == -1:
                break
            with contextlib.suppress(ScriptError):
                exprs.append(parse_expression(raw[i + 1 : end], line=line))
            i = end + 1
            continue
        i += 1
    return exprs


def _collect_function_names(statements: list[Stmt]) -> set[str]:
    """Pre-scan every ``func`` in the program so forward/mutual calls lint clean."""
    names: set[str] = set()
    for statement in statements:
        match statement:
            case FuncDef(name=name, body=body):
                names.add(name)
                names |= _collect_function_names(body)
            case IfStmt(then_body=then_body, else_body=else_body):
                names |= _collect_function_names(then_body)
                names |= _collect_function_names(else_body)
            case ForeachStmt(body=body) | WhileStmt(body=body):
                names |= _collect_function_names(body)
    return names


def _check_call(
    call: Call, defined: set[str], functions: set[str], issues: list[LintIssue]
) -> None:
    for arg in call.args:
        _check_expr(arg, defined, functions, issues)

    if "." in call.callee:
        module_name, member = call.callee.split(".", 1)
        if module_name == "ui":
            if member not in UI_FUNCTIONS:
                options = ", ".join(sorted(UI_FUNCTIONS))
                issues.append(
                    LintIssue(
                        "error", call.line, f"unknown function 'ui.{member}'. Options: {options}"
                    )
                )
            return
        if _PERMISSIVE not in defined and module_name not in defined:
            issues.append(LintIssue("error", call.line, f"undefined variable '{module_name}'"))
        return

    if call.callee in BUILTIN_FUNCTIONS or call.callee in HIGHER_ORDER_FUNCTIONS:
        return
    if call.callee in functions:
        return
    if _PERMISSIVE in defined:
        return
    if call.callee in defined:
        # A plain variable — could hold a lambda/function value (e.g. `set
        # sq = lambda(x): x * x` then `sq(5)`). The linter can't statically
        # know it's callable; the interpreter raises a clear error at run
        # time if it isn't.
        return

    candidates = list(BUILTIN_FUNCTIONS) + list(HIGHER_ORDER_FUNCTIONS) + sorted(functions)
    suggestions = difflib.get_close_matches(call.callee, candidates, n=1)
    hint = f" Did you mean '{suggestions[0]}'?" if suggestions else ""
    issues.append(LintIssue("error", call.line, f"unknown function '{call.callee}'.{hint}"))


def _check_expr(
    expr: Expr, defined: set[str], functions: set[str], issues: list[LintIssue]
) -> None:
    match expr:
        case VarRef(name=name, line=line):
            if "." in name:
                root = name.split(".", 1)[0]
                if root == "ui":
                    return
                if _PERMISSIVE not in defined and root not in defined:
                    issues.append(LintIssue("error", line, f"undefined variable '{root}'"))
                return
            if _PERMISSIVE not in defined and name not in defined:
                issues.append(LintIssue("error", line, f"undefined variable '{name}'"))
        case BinOp(left=left, right=right):
            _check_expr(left, defined, functions, issues)
            _check_expr(right, defined, functions, issues)
        case UnaryOp(operand=operand):
            _check_expr(operand, defined, functions, issues)
        case ListLiteral(items=items):
            for item in items:
                _check_expr(item, defined, functions, issues)
        case DictLiteral(pairs=pairs):
            for key, value in pairs:
                _check_expr(key, defined, functions, issues)
                _check_expr(value, defined, functions, issues)
        case Index(target=target, index=index_expr):
            _check_expr(target, defined, functions, issues)
            _check_expr(index_expr, defined, functions, issues)
        case Slice(target=target, start=start_expr, stop=stop_expr):
            _check_expr(target, defined, functions, issues)
            if start_expr is not None:
                _check_expr(start_expr, defined, functions, issues)
            if stop_expr is not None:
                _check_expr(stop_expr, defined, functions, issues)
        case Lambda(params=params, body=body):
            _check_expr(body, defined | set(params), functions, issues)
        case Attr(target=target):
            # The member itself can't be statically checked — it depends on
            # the runtime type of `target`, which the linter doesn't infer.
            _check_expr(target, defined, functions, issues)
        case Call() as call:
            _check_call(call, defined, functions, issues)
        case Literal(value=str() as raw, line=line):
            for inner in _interpolated_exprs(raw, line):
                _check_expr(inner, defined, functions, issues)
        case Literal():
            pass


def _always_exits(statements: list[Stmt]) -> bool:
    """True if this block can never fall off its end normally — every path

    through it hits ``return``/``fail``/``break``/``continue``. Used to
    decide whether a ``try``'s ``except`` body "always exits": if it does,
    reaching the statement after the whole ``try``/``except`` means the
    ``try`` body ran to completion, so its variables are safe to consider
    defined there (unlike the general case, where they're only guaranteed
    if both branches define them).
    """
    if not statements:
        return False
    match statements[-1]:
        case ReturnStmt() | FailStmt() | BreakStmt() | ContinueStmt():
            return True
        case IfStmt(then_body=then_body, else_body=else_body):
            return bool(else_body) and _always_exits(then_body) and _always_exits(else_body)
        case TryStmt(body=body, except_body=except_body):
            return _always_exits(body) and _always_exits(except_body)
        case _:
            return False


def _check_module(module: str, line: int, issues: list[LintIssue]) -> None:
    if module in MODULE_RUNNERS:
        return
    suggestions = difflib.get_close_matches(module, MODULE_RUNNERS, n=1)
    hint = f" Did you mean '{suggestions[0]}'?" if suggestions else ""
    options = ", ".join(sorted(MODULE_RUNNERS))
    issues.append(LintIssue("error", line, f"unknown module '{module}'.{hint} Options: {options}"))


def _walk(
    statements: list[Stmt],
    defined: set[str],
    functions: set[str],
    issues: list[LintIssue],
    *,
    in_loop: bool = False,
    in_function: bool = False,
) -> set[str]:
    defined = set(defined)
    for statement in statements:
        match statement:
            case SetStmt(name=name, value=value):
                _check_expr(value, defined, functions, issues)
                defined.add(name)
            case IndexSetStmt(target=target, index=index_expr, value=value):
                _check_expr(target, defined, functions, issues)
                _check_expr(index_expr, defined, functions, issues)
                _check_expr(value, defined, functions, issues)
            case ExprStmt(value=value):
                _check_expr(value, defined, functions, issues)
            case PrintStmt(value=value) | SleepStmt(value=value):
                _check_expr(value, defined, functions, issues)
            case AssertStmt(condition=condition, message=message):
                _check_expr(condition, defined, functions, issues)
                if message is not None:
                    _check_expr(message, defined, functions, issues)
            case FailStmt(message=message):
                _check_expr(message, defined, functions, issues)
            case RunStmt(module=module, target=target, var_name=var_name, line=line):
                _check_module(module, line, issues)
                _check_expr(target, defined, functions, issues)
                if var_name:
                    defined.add(var_name)
            case SaveStmt(var_name=var_name, path=path, line=line):
                if _PERMISSIVE not in defined and var_name not in defined:
                    issues.append(LintIssue("error", line, f"undefined variable '{var_name}'"))
                _check_expr(path, defined, functions, issues)
            case IfStmt(condition=condition, then_body=then_body, else_body=else_body, line=line):
                _check_expr(condition, defined, functions, issues)
                if not then_body:
                    issues.append(LintIssue("warning", line, "empty 'if' body"))
                then_defined = _walk(
                    then_body, defined, functions, issues, in_loop=in_loop, in_function=in_function
                )
                else_defined = (
                    _walk(
                        else_body,
                        defined,
                        functions,
                        issues,
                        in_loop=in_loop,
                        in_function=in_function,
                    )
                    if else_body
                    else set(defined)
                )
                defined |= then_defined & else_defined
                if _PERMISSIVE in then_defined or _PERMISSIVE in else_defined:
                    defined.add(_PERMISSIVE)
            case ForeachStmt(var_name=var_name, iterable=iterable, body=body, line=line):
                _check_expr(iterable, defined, functions, issues)
                if not body:
                    issues.append(LintIssue("warning", line, "empty 'foreach' body"))
                body_defined = _walk(
                    body,
                    defined | {var_name},
                    functions,
                    issues,
                    in_loop=True,
                    in_function=in_function,
                )
                if _PERMISSIVE in body_defined:
                    defined.add(_PERMISSIVE)
            case WhileStmt(condition=condition, body=body, line=line):
                _check_expr(condition, defined, functions, issues)
                if not body:
                    issues.append(LintIssue("warning", line, "empty 'while' body"))
                body_defined = _walk(
                    body, defined, functions, issues, in_loop=True, in_function=in_function
                )
                if _PERMISSIVE in body_defined:
                    defined.add(_PERMISSIVE)
            case BreakStmt(line=line):
                if not in_loop:
                    issues.append(LintIssue("error", line, "'break' used outside of a loop"))
            case ContinueStmt(line=line):
                if not in_loop:
                    issues.append(LintIssue("error", line, "'continue' used outside of a loop"))
            case FuncDef(name=name, params=params, body=body, line=line):
                if not body:
                    issues.append(LintIssue("warning", line, f"empty function body for '{name}'"))
                # A function's body can read whatever's already `set`/`import`ed
                # in the enclosing scope at this point (see NyxFunction.home_env
                # in the interpreter) — not just its own parameters. Losing
                # that was a real false-positive: `import ... as lib` followed
                # by `lib.member(...)` *inside* a function used to get flagged
                # as an undefined variable even though it runs fine.
                _walk(
                    body, defined | set(params), functions, issues, in_loop=False, in_function=True
                )
                defined.add(name)
            case ReturnStmt(value=value, line=line):
                if not in_function:
                    issues.append(LintIssue("error", line, "'return' used outside of a function"))
                if value is not None:
                    _check_expr(value, defined, functions, issues)
            case ImportStmt(path=path, alias=alias):
                _check_expr(path, defined, functions, issues)
                defined.add(alias)
            case TryStmt(body=body, error_var=error_var, except_body=except_body, line=line):
                if not body:
                    issues.append(LintIssue("warning", line, "empty 'try' body"))
                body_defined = _walk(
                    body, defined, functions, issues, in_loop=in_loop, in_function=in_function
                )
                except_defined = _walk(
                    except_body,
                    defined | {error_var},
                    functions,
                    issues,
                    in_loop=in_loop,
                    in_function=in_function,
                )
                if _always_exits(except_body):
                    defined |= body_defined
                else:
                    defined |= body_defined & except_defined
                if _PERMISSIVE in body_defined or _PERMISSIVE in except_defined:
                    defined.add(_PERMISSIVE)
            case PythonStmt(line=line):
                issues.append(
                    LintIssue(
                        "warning",
                        line,
                        "'python' block — variables it may set aren't tracked by the linter; "
                        "requires --unsafe to run",
                    )
                )
                defined = defined | {_PERMISSIVE}
            case PipStmt(package=package, line=line):
                _check_expr(package, defined, functions, issues)
                issues.append(
                    LintIssue(
                        "warning",
                        line,
                        "'pip' installs a package at run time; requires --unsafe to run",
                    )
                )
            case DocStmt():
                pass
    return defined


def lint_program(program: Program) -> list[LintIssue]:
    """Static-check an already-parsed program."""
    issues: list[LintIssue] = []
    functions = _collect_function_names(program.body)
    _walk(program.body, set(), functions, issues)
    return sorted(issues, key=lambda issue: issue.line)


def lint_source(source: str) -> list[LintIssue]:
    """Lex, parse, and static-check a NyxScript source string.

    Never raises — a lex/parse failure becomes a single ``error`` issue at
    the offending line instead, so callers always get a uniform report.
    """
    try:
        program = parse(source)
    except ScriptError as exc:
        return [LintIssue("error", exc.line or 0, exc.reason)]
    return lint_program(program)


__all__ = ["LintIssue", "lint_program", "lint_source", "UI_FUNCTIONS"]
