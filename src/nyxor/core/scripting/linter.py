"""Static analysis for NyxScript, run before (or instead of) execution.

Catches the mistakes that would otherwise only surface partway through a
live run against real infrastructure: undefined variables (including
inside ``"{...}"`` string interpolation), unknown ``run`` modules (with a
"did you mean" suggestion), and empty control-flow bodies. It never
executes anything — no network access, no side effects.
"""

from __future__ import annotations

import contextlib
import difflib
from dataclasses import dataclass

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
from nyxor.core.scripting.errors import ScriptError
from nyxor.core.scripting.parser import parse, parse_expression
from nyxor.core.scripting.stdlib import MODULE_RUNNERS

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


def _check_expr(expr: Expr, defined: set[str], issues: list[LintIssue]) -> None:
    match expr:
        case VarRef(name=name, line=line):
            if _PERMISSIVE not in defined and name not in defined:
                issues.append(LintIssue("error", line, f"undefined variable '{name}'"))
        case BinOp(left=left, right=right):
            _check_expr(left, defined, issues)
            _check_expr(right, defined, issues)
        case UnaryOp(operand=operand):
            _check_expr(operand, defined, issues)
        case ListLiteral(items=items):
            for item in items:
                _check_expr(item, defined, issues)
        case Literal(value=str() as raw, line=line):
            for inner in _interpolated_exprs(raw, line):
                _check_expr(inner, defined, issues)
        case Literal():
            pass


def _check_module(module: str, line: int, issues: list[LintIssue]) -> None:
    if module in MODULE_RUNNERS:
        return
    suggestions = difflib.get_close_matches(module, MODULE_RUNNERS, n=1)
    hint = f" Did you mean '{suggestions[0]}'?" if suggestions else ""
    options = ", ".join(sorted(MODULE_RUNNERS))
    issues.append(LintIssue("error", line, f"unknown module '{module}'.{hint} Options: {options}"))


def _walk(statements: list[Stmt], defined: set[str], issues: list[LintIssue]) -> set[str]:
    defined = set(defined)
    for statement in statements:
        match statement:
            case SetStmt(name=name, value=value):
                _check_expr(value, defined, issues)
                defined.add(name)
            case PrintStmt(value=value) | SleepStmt(value=value):
                _check_expr(value, defined, issues)
            case AssertStmt(condition=condition, message=message):
                _check_expr(condition, defined, issues)
                if message is not None:
                    _check_expr(message, defined, issues)
            case FailStmt(message=message):
                _check_expr(message, defined, issues)
            case RunStmt(module=module, target=target, var_name=var_name, line=line):
                _check_module(module, line, issues)
                _check_expr(target, defined, issues)
                if var_name:
                    defined.add(var_name)
            case SaveStmt(var_name=var_name, path=path, line=line):
                if _PERMISSIVE not in defined and var_name not in defined:
                    issues.append(LintIssue("error", line, f"undefined variable '{var_name}'"))
                _check_expr(path, defined, issues)
            case IfStmt(condition=condition, then_body=then_body, else_body=else_body, line=line):
                _check_expr(condition, defined, issues)
                if not then_body:
                    issues.append(LintIssue("warning", line, "empty 'if' body"))
                then_defined = _walk(then_body, defined, issues)
                else_defined = _walk(else_body, defined, issues) if else_body else set(defined)
                defined |= then_defined & else_defined
                if _PERMISSIVE in then_defined or _PERMISSIVE in else_defined:
                    defined.add(_PERMISSIVE)
            case ForeachStmt(var_name=var_name, iterable=iterable, body=body, line=line):
                _check_expr(iterable, defined, issues)
                if not body:
                    issues.append(LintIssue("warning", line, "empty 'foreach' body"))
                body_defined = _walk(body, defined | {var_name}, issues)
                if _PERMISSIVE in body_defined:
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
                _check_expr(package, defined, issues)
                issues.append(
                    LintIssue(
                        "warning",
                        line,
                        "'pip' installs a package at run time; requires --unsafe to run",
                    )
                )
    return defined


def lint_program(program: Program) -> list[LintIssue]:
    """Static-check an already-parsed program."""
    issues: list[LintIssue] = []
    _walk(program.body, set(), issues)
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
