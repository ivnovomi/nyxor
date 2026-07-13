"""Executes a parsed NyxScript :class:`Program`.

Everything — expressions included — is evaluated through ``async def``
now: a call expression can invoke a user-defined function whose body runs
``run``/``sleep``/``ui.*`` (all real I/O), so expression evaluation can no
longer be assumed synchronous the way it could before functions existed.

Scoping is intentionally simple (no closures): the interpreter has exactly
one global scope (``self.env``) plus, while a function call is on the
stack, exactly one local scope for it (``self.call_stack[-1]``). ``set``
inside a function always writes local; reads check local first, then fall
through to global. That's "lightweight" on purpose — it covers everything
a security-automation script needs without asking the author to think
about closures.
"""

from __future__ import annotations

import asyncio
import difflib
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nyxor.core.config import NyxorConfig
from nyxor.core.models import ModuleResult
from nyxor.core.reporting import ReportDocument, get_writer
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
    UnsafeStmt,
    VarRef,
    WhileStmt,
    function_docstring,
)
from nyxor.core.scripting.builtins import BUILTIN_FUNCTIONS, HIGHER_ORDER_FUNCTIONS, format_value
from nyxor.core.scripting.errors import RuntimeScriptError, ScriptError
from nyxor.core.scripting.parser import parse, parse_expression
from nyxor.core.scripting.stdlib import MODULE_RUNNERS
from nyxor.core.scripting.ui import UI_FUNCTIONS, ScriptUI

OutputFn = Callable[[str], None]

_FORMAT_BY_SUFFIX = {
    "json": "json",
    "md": "markdown",
    "markdown": "markdown",
    "html": "html",
    "htm": "html",
    "sarif": "sarif",
}

# `[x] * n` / `"x" * n` (sequence repetition) can allocate an arbitrarily
# large result from a single multiplication of two tiny operands — unlike
# `+`, which can only ever produce something as big as its two operands
# combined. Same class of danger as an unbounded `while` loop, so cap it
# the same order of magnitude as MAX_LOOP_ITERATIONS.
_MAX_SEQUENCE_LEN = 1_000_000


def _multiply(a: Any, b: Any) -> Any:
    for seq, factor in ((a, b), (b, a)):
        is_sequence = isinstance(seq, list | str)
        is_plain_int = isinstance(factor, int) and not isinstance(factor, bool)
        if is_sequence and is_plain_int and len(seq) * max(factor, 0) > _MAX_SEQUENCE_LEN:
            raise ValueError(
                f"'*' would produce a sequence of {len(seq) * factor:,} items "
                f"(limit {_MAX_SEQUENCE_LEN:,})"
            )
    return a * b


_BIN_OPS: dict[str, Callable[[Any, Any], Any]] = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": _multiply,
    "/": lambda a, b: a / b,
    "==": lambda a, b: a == b,
    "!=": lambda a, b: a != b,
    "<": lambda a, b: a < b,
    "<=": lambda a, b: a <= b,
    ">": lambda a, b: a > b,
    ">=": lambda a, b: a >= b,
}


def _truthy(value: Any) -> bool:
    return bool(value)


_format_value = format_value


@dataclass(frozen=True)
class NyxFunction:
    """A user-defined ``func`` — a value like any other, stored in a scope.

    ``home_env`` is the (global-level) scope dict the function was defined
    in — the main script's globals, or a library's own members dict. It's
    not a full lexical closure (functions don't capture local variables),
    just enough so a library function can call a sibling function by its
    bare name and have that resolve against *its own* library instead of
    whatever script happened to import it.
    """

    name: str
    params: list[str]
    body: list[Stmt]
    home_env: dict[str, Any]
    doc: str | None = None

    def __str__(self) -> str:
        return f"<func {self.name}({', '.join(self.params)})>"


@dataclass(frozen=True)
class NyxModule:
    """The result of ``import "lib.nyx" as alias`` — a bag of the library's

    top-level names (functions and constants), reached as ``alias.member``.
    """

    name: str
    members: dict[str, Any]

    def __str__(self) -> str:
        return f"<module {self.name}>"


class _ReturnSignal(Exception):
    def __init__(self, value: Any) -> None:
        self.value = value


class _BreakSignal(Exception):
    pass


class _ContinueSignal(Exception):
    pass


class Interpreter:
    """Holds the running script's variable environment and I/O sinks."""

    MAX_CALL_DEPTH = 200
    MAX_LOOP_ITERATIONS = 1_000_000
    MAX_IMPORT_DEPTH = 20

    def __init__(
        self,
        config: NyxorConfig,
        *,
        output: OutputFn = print,
        base_dir: Path | None = None,
        unsafe: bool = False,
        ui: ScriptUI | None = None,
    ) -> None:
        self.config = config
        self.output = output
        self.base_dir = base_dir or Path.cwd()
        self.unsafe = unsafe
        self.ui = ui or ScriptUI()
        self._env_stack: list[dict[str, Any]] = [{}]
        self.call_stack: list[dict[str, Any]] = []
        self._importing: set[Path] = set()

    @property
    def env(self) -> dict[str, Any]:
        """The "global" scope currently in effect.

        Normally the top-level script's own globals — but while executing
        inside a function, this is that function's *home* environment
        (see :class:`NyxFunction`), not necessarily the caller's.
        """
        return self._env_stack[-1]

    # -- scope helpers --------------------------------------------------------

    def _set_var(self, name: str, value: Any) -> None:
        if self.call_stack:
            self.call_stack[-1][name] = value
        else:
            self.env[name] = value

    def _get_var(self, name: str, line: int) -> Any:
        # A dotted VarRef only happens via the lexer's identifier merge
        # (`lib.member` typed with no surrounding brackets/spaces) — walk
        # each `.part` the same way the `.` postfix operator does, so
        # `lib.a.b` and `Attr(Attr(lib, "a"), "b")` behave identically.
        root, *parts = name.split(".")
        value = self._lookup_optional(root)
        if value is None and not self._is_bound(root):
            raise RuntimeScriptError(f"undefined variable '{root}'", line=line)
        for part in parts:
            value = self._get_member(value, part, line)
        return value

    def _is_bound(self, name: str) -> bool:
        if self.call_stack and name in self.call_stack[-1]:
            return True
        return name in self.env

    def _lookup_optional(self, name: str) -> Any:
        if self.call_stack and name in self.call_stack[-1]:
            return self.call_stack[-1][name]
        return self.env.get(name)

    def _get_member(self, value: Any, member: str, line: int) -> Any:
        if isinstance(value, NyxModule):
            if member not in value.members:
                raise RuntimeScriptError(f"'{value.name}' has no member '{member}'", line=line)
            return value.members[member]
        try:
            return getattr(value, member)
        except AttributeError as exc:
            raise RuntimeScriptError(
                f"'{type(value).__name__}' object has no attribute '{member}'", line=line
            ) from exc

    # -- expressions ---------------------------------------------------------

    async def eval_expr(self, expr: Expr) -> Any:
        match expr:
            case Literal(value=str() as raw, line=line):
                return await self._interpolate(raw, line)
            case Literal(value=value):
                return value
            case ListLiteral(items=items):
                return [await self.eval_expr(item) for item in items]
            case DictLiteral(pairs=pairs, line=line):
                result: dict[Any, Any] = {}
                for key_expr, value_expr in pairs:
                    key = await self.eval_expr(key_expr)
                    value = await self.eval_expr(value_expr)
                    try:
                        result[key] = value
                    except TypeError as exc:
                        raise RuntimeScriptError(
                            f"cannot use a {type(key).__name__} as a dict key", line=line
                        ) from exc
                return result
            case VarRef(name=name, line=line):
                return self._get_var(name, line)
            case Index(target=target, index=index_expr, line=line):
                return await self._eval_index(target, index_expr, line)
            case Slice(target=target, start=start_expr, stop=stop_expr, line=line):
                return await self._eval_slice(target, start_expr, stop_expr, line)
            case Lambda(params=params, body=body, line=line):
                captured = dict(self.env)
                if self.call_stack:
                    captured.update(self.call_stack[-1])
                return NyxFunction(
                    name="<lambda>",
                    params=params,
                    body=[ReturnStmt(value=body, line=line)],
                    home_env=captured,
                )
            case Attr(target=target, name=name, line=line):
                return self._get_member(await self.eval_expr(target), name, line)
            case Call() as call:
                return await self._eval_call(call)
            case UnaryOp(op="-", operand=operand, line=line):
                value = await self.eval_expr(operand)
                try:
                    return -value
                except TypeError as exc:
                    raise RuntimeScriptError(
                        f"cannot negate a {type(value).__name__}", line=line
                    ) from exc
            case UnaryOp(op="not", operand=operand):
                return not _truthy(await self.eval_expr(operand))
            case BinOp(op="and", left=left, right=right):
                left_value = await self.eval_expr(left)
                return await self.eval_expr(right) if _truthy(left_value) else left_value
            case BinOp(op="or", left=left, right=right):
                left_value = await self.eval_expr(left)
                return left_value if _truthy(left_value) else await self.eval_expr(right)
            case BinOp(op=op, left=left, right=right, line=line):
                left_value = await self.eval_expr(left)
                right_value = await self.eval_expr(right)
                try:
                    return _BIN_OPS[op](left_value, right_value)
                except TypeError as exc:
                    lt, rt = type(left_value).__name__, type(right_value).__name__
                    raise RuntimeScriptError(
                        f"cannot apply '{op}' to {lt} and {rt}", line=line
                    ) from exc
                except ZeroDivisionError as exc:
                    raise RuntimeScriptError("division by zero", line=line) from exc
                except ValueError as exc:
                    raise RuntimeScriptError(str(exc), line=line) from exc
        raise RuntimeScriptError(f"cannot evaluate expression: {expr!r}")

    async def _eval_index(self, target: Expr, index_expr: Expr, line: int) -> Any:
        container = await self.eval_expr(target)
        idx = await self.eval_expr(index_expr)
        try:
            return container[idx]
        except TypeError as exc:
            raise RuntimeScriptError(
                f"cannot index a {type(container).__name__} with a {type(idx).__name__}", line=line
            ) from exc
        except (IndexError, KeyError) as exc:
            raise RuntimeScriptError(f"index {idx!r} out of range", line=line) from exc

    async def _eval_slice(
        self, target: Expr, start_expr: Expr | None, stop_expr: Expr | None, line: int
    ) -> Any:
        container = await self.eval_expr(target)
        if not isinstance(container, list | str):
            raise RuntimeScriptError(f"cannot slice a {type(container).__name__}", line=line)
        start = await self.eval_expr(start_expr) if start_expr is not None else None
        stop = await self.eval_expr(stop_expr) if stop_expr is not None else None
        try:
            return container[start:stop]
        except TypeError as exc:
            raise RuntimeScriptError("slice bounds must be integers", line=line) from exc

    async def _call_higher_order(self, name: str, args: list[Any], line: int) -> Any:
        def check_list(value: Any) -> None:
            if not isinstance(value, list):
                raise RuntimeScriptError(
                    f"{name}() expects a list, got {type(value).__name__}", line=line
                )

        def check_function(value: Any) -> None:
            if not isinstance(value, NyxFunction):
                raise RuntimeScriptError(
                    f"{name}() expects a function, got {type(value).__name__}", line=line
                )

        if name in ("map", "filter", "sort_by"):
            if len(args) != 2:
                raise RuntimeScriptError(f"{name}() expects 2 arguments (list, fn)", line=line)
            items, fn = args
            check_list(items)
            check_function(fn)
            if name == "map":
                return [await self._call_function(fn, [item], line) for item in items]
            if name == "filter":
                out = []
                for item in items:
                    if _truthy(await self._call_function(fn, [item], line)):
                        out.append(item)
                return out
            keyed = [(await self._call_function(fn, [item], line), item) for item in items]
            keyed.sort(key=lambda pair: pair[0])
            return [item for _key, item in keyed]

        # reduce(list, fn, initial)
        if len(args) != 3:
            raise RuntimeScriptError("reduce() expects 3 arguments (list, fn, initial)", line=line)
        items, fn, acc = args
        check_list(items)
        check_function(fn)
        for item in items:
            acc = await self._call_function(fn, [acc, item], line)
        return acc

    async def _eval_call(self, call: Call) -> Any:
        args = [await self.eval_expr(arg) for arg in call.args]

        if call.callee in HIGHER_ORDER_FUNCTIONS:
            return await self._call_higher_order(call.callee, args, call.line)

        if "." in call.callee:
            module_name, member = call.callee.split(".", 1)

            if module_name == "ui":
                if member not in UI_FUNCTIONS:
                    raise RuntimeScriptError(f"unknown function 'ui.{member}'", line=call.line)
                try:
                    return await getattr(self.ui, member)(args)
                except TypeError as exc:
                    raise RuntimeScriptError(str(exc), line=call.line) from exc

            module_value = self._lookup_optional(module_name)
            if isinstance(module_value, NyxModule):
                fn = module_value.members.get(member)
                if not isinstance(fn, NyxFunction):
                    raise RuntimeScriptError(
                        f"'{module_name}' has no function '{member}'", line=call.line
                    )
                return await self._call_function(fn, args, call.line)

            raise RuntimeScriptError(f"unknown function '{call.callee}'", line=call.line)

        if call.callee in BUILTIN_FUNCTIONS:
            try:
                return BUILTIN_FUNCTIONS[call.callee](args)
            except (TypeError, ValueError, IndexError, ZeroDivisionError) as exc:
                raise RuntimeScriptError(str(exc), line=call.line) from exc

        value = self._lookup_optional(call.callee)
        if isinstance(value, NyxFunction):
            return await self._call_function(value, args, call.line)

        candidates = (
            list(BUILTIN_FUNCTIONS)
            + list(HIGHER_ORDER_FUNCTIONS)
            + [k for k, v in self.env.items() if isinstance(v, NyxFunction)]
        )
        suggestions = difflib.get_close_matches(call.callee, candidates, n=1)
        hint = f" Did you mean '{suggestions[0]}'?" if suggestions else ""
        raise RuntimeScriptError(f"unknown function '{call.callee}'.{hint}", line=call.line)

    async def _call_function(self, fn: NyxFunction, args: list[Any], line: int) -> Any:
        if len(args) != len(fn.params):
            raise RuntimeScriptError(
                f"'{fn.name}' expects {len(fn.params)} argument(s), got {len(args)}", line=line
            )
        if len(self.call_stack) >= self.MAX_CALL_DEPTH:
            raise RuntimeScriptError(
                f"call stack too deep calling '{fn.name}' (possible infinite recursion)", line=line
            )

        frame = dict(zip(fn.params, args, strict=True))
        self.call_stack.append(frame)
        self._env_stack.append(fn.home_env)
        try:
            await self.exec_block(fn.body)
            return None
        except _ReturnSignal as ret:
            return ret.value
        except _BreakSignal:
            raise RuntimeScriptError(
                f"'break' used outside of a loop (inside '{fn.name}')", line=line
            ) from None
        except _ContinueSignal:
            raise RuntimeScriptError(
                f"'continue' used outside of a loop (inside '{fn.name}')", line=line
            ) from None
        finally:
            self.call_stack.pop()
            self._env_stack.pop()

    async def _interpolate(self, raw: str, line: int) -> str:
        """Resolve ``{expr}`` spans inside a string literal. ``{{``/``}}`` escape."""
        out: list[str] = []
        i = 0
        n = len(raw)
        while i < n:
            ch = raw[i]
            if ch == "{" and i + 1 < n and raw[i + 1] == "{":
                out.append("{")
                i += 2
                continue
            if ch == "}" and i + 1 < n and raw[i + 1] == "}":
                out.append("}")
                i += 2
                continue
            if ch == "{":
                end = raw.find("}", i + 1)
                if end == -1:
                    raise RuntimeScriptError("unterminated '{' in string interpolation", line=line)
                inner = raw[i + 1 : end]
                try:
                    expr = parse_expression(inner, line=line)
                except ScriptError as exc:
                    raise RuntimeScriptError(
                        f"invalid expression {inner!r} in string interpolation: {exc.message}",
                        line=line,
                    ) from exc
                out.append(_format_value(await self.eval_expr(expr)))
                i = end + 1
                continue
            out.append(ch)
            i += 1
        return "".join(out)

    # -- statements ------------------------------------------------------------

    async def run(self, program: Program) -> None:
        try:
            await self.exec_block(program.body)
        except _ReturnSignal:
            raise RuntimeScriptError("'return' used outside of a function") from None
        except _BreakSignal:
            raise RuntimeScriptError("'break' used outside of a loop") from None
        except _ContinueSignal:
            raise RuntimeScriptError("'continue' used outside of a loop") from None

    async def exec_block(self, statements: list[Stmt]) -> None:
        for statement in statements:
            await self.exec_stmt(statement)

    async def exec_stmt(self, statement: Stmt) -> None:
        match statement:
            case SetStmt(name=name, value=value):
                self._set_var(name, await self.eval_expr(value))
            case IndexSetStmt(target=target, index=index_expr, value=value_expr, line=line):
                container = await self.eval_expr(target)
                idx = await self.eval_expr(index_expr)
                new_value = await self.eval_expr(value_expr)
                if not isinstance(container, list | dict):
                    raise RuntimeScriptError(
                        f"cannot assign into a {type(container).__name__}", line=line
                    )
                try:
                    container[idx] = new_value
                except TypeError as exc:
                    raise RuntimeScriptError(
                        f"cannot index a {type(container).__name__} with a {type(idx).__name__}",
                        line=line,
                    ) from exc
                except IndexError as exc:
                    raise RuntimeScriptError(f"index {idx!r} out of range", line=line) from exc
            case ExprStmt(value=value):
                await self.eval_expr(value)
            case PrintStmt(value=value):
                self.output(_format_value(await self.eval_expr(value)))
            case SleepStmt(value=value, line=line):
                duration = await self.eval_expr(value)
                if not isinstance(duration, int | float) or isinstance(duration, bool):
                    raise RuntimeScriptError(
                        f"'sleep' expects a number, got {type(duration).__name__}", line=line
                    )
                await asyncio.sleep(float(duration))
            case AssertStmt(condition=condition, message=message, line=line):
                if not _truthy(await self.eval_expr(condition)):
                    text = (
                        _format_value(await self.eval_expr(message))
                        if message
                        else "assertion failed"
                    )
                    raise RuntimeScriptError(text, line=line)
            case FailStmt(message=message, line=line):
                raise RuntimeScriptError(_format_value(await self.eval_expr(message)), line=line)
            case RunStmt(module=module, target=target, var_name=var_name, line=line):
                await self._exec_run(module, target, var_name, line)
            case SaveStmt(var_name=var_name, path=path, line=line):
                await self._exec_save(var_name, path, line)
            case IfStmt(condition=condition, then_body=then_body, else_body=else_body):
                if _truthy(await self.eval_expr(condition)):
                    await self.exec_block(then_body)
                else:
                    await self.exec_block(else_body)
            case ForeachStmt(var_name=var_name, iterable=iterable, body=body, line=line):
                values = await self.eval_expr(iterable)
                if not isinstance(values, list):
                    raise RuntimeScriptError(
                        f"'foreach' needs a list, got {type(values).__name__}", line=line
                    )
                for item in values:
                    self._set_var(var_name, item)
                    try:
                        await self.exec_block(body)
                    except _BreakSignal:
                        break
                    except _ContinueSignal:
                        continue
            case WhileStmt(condition=condition, body=body, line=line):
                iterations = 0
                while _truthy(await self.eval_expr(condition)):
                    iterations += 1
                    if iterations > self.MAX_LOOP_ITERATIONS:
                        raise RuntimeScriptError(
                            f"'while' exceeded {self.MAX_LOOP_ITERATIONS:,} iterations "
                            "— likely infinite",
                            line=line,
                        )
                    try:
                        await self.exec_block(body)
                    except _BreakSignal:
                        break
                    except _ContinueSignal:
                        continue
            case BreakStmt():
                raise _BreakSignal
            case ContinueStmt():
                raise _ContinueSignal
            case UnsafeStmt():
                self.unsafe = True
            case FuncDef(name=name, params=params, body=body):
                self.env[name] = NyxFunction(
                    name=name,
                    params=params,
                    body=body,
                    home_env=self.env,
                    doc=function_docstring(body),
                )
            case DocStmt():
                pass
            case ReturnStmt(value=value):
                raise _ReturnSignal(await self.eval_expr(value) if value is not None else None)
            case ImportStmt(path=path, alias=alias, line=line):
                await self._exec_import(path, alias, line)
            case TryStmt(body=body, error_var=error_var, except_body=except_body):
                try:
                    await self.exec_block(body)
                except RuntimeScriptError as exc:
                    self._set_var(error_var, exc.reason)
                    await self.exec_block(except_body)
            case PythonStmt(code=code, line=line):
                await self._exec_python(code, line)
            case PipStmt(package=package, line=line):
                await self._exec_pip(package, line)

    async def _exec_run(
        self, module: str, target_expr: Expr, var_name: str | None, line: int
    ) -> None:
        runner = MODULE_RUNNERS.get(module)
        if runner is None:
            suggestions = difflib.get_close_matches(module, MODULE_RUNNERS, n=1)
            hint = f" Did you mean '{suggestions[0]}'?" if suggestions else ""
            raise RuntimeScriptError(f"unknown module '{module}'.{hint}", line=line)

        target = _format_value(await self.eval_expr(target_expr))
        self.output(f"→ run {module} {target}")
        results = await runner(target, self.config)
        total = sum(len(r.findings) for r in results)
        self.output(f"  {total} finding(s) across {len(results)} module result(s)")
        if var_name:
            self._set_var(var_name, results)

    async def _exec_save(self, var_name: str, path_expr: Expr, line: int) -> None:
        results = self._get_var(var_name, line)
        if isinstance(results, ModuleResult):
            results = [results]
        if not isinstance(results, list) or not all(isinstance(r, ModuleResult) for r in results):
            raise RuntimeScriptError(
                f"'{var_name}' doesn't hold scan results — did you mean 'run ... as {var_name}'?",
                line=line,
            )

        path_str = _format_value(await self.eval_expr(path_expr))
        base = self.base_dir.resolve()
        # `Path.__truediv__` silently discards `base` if `path_str` is
        # absolute (e.g. "/etc/cron.d/x" or "C:\Windows\x"), and ".."
        # segments can walk out of `base` even when it isn't — so resolve
        # and check containment explicitly. Scripts run without --unsafe
        # must not be able to write outside their own working directory.
        path = (base / path_str).resolve()
        if not path.is_relative_to(base):
            raise RuntimeScriptError(
                f"'save ... as {path_str!r}' would write outside the script's "
                f"working directory ({base}) — not allowed.",
                line=line,
            )
        fmt = _FORMAT_BY_SUFFIX.get(path.suffix.lstrip(".").lower(), "json")
        document = ReportDocument(title="NYXOR Script Report", results=results)
        get_writer(fmt).write(document, path)
        self.output(f"  saved -> {path}")

    async def _exec_import(self, path_expr: Expr, alias: str, line: int) -> None:
        path_str = _format_value(await self.eval_expr(path_expr))
        path = (self.base_dir / path_str).resolve()

        if not path.is_file():
            raise RuntimeScriptError(f"cannot import {path_str!r}: file not found", line=line)
        if path in self._importing:
            raise RuntimeScriptError(f"circular import of {path_str!r}", line=line)
        if len(self._importing) >= self.MAX_IMPORT_DEPTH:
            raise RuntimeScriptError("import depth exceeded — likely a circular import", line=line)

        try:
            source = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeScriptError(f"cannot read {path_str!r}: {exc}", line=line) from exc

        try:
            program = parse(source)
        except ScriptError as exc:
            raise RuntimeScriptError(
                f"error importing {path_str!r}: {exc.reason}", line=line
            ) from exc

        self._importing.add(path)
        saved_stack, self.call_stack = self.call_stack, []
        self._env_stack.append({})
        try:
            await self.exec_block(program.body)
            members = self._env_stack[-1]
        finally:
            self._env_stack.pop()
            self.call_stack = saved_stack
            self._importing.discard(path)

        self._set_var(alias, NyxModule(name=alias, members=members))

    def _require_unsafe(self, feature: str, line: int) -> None:
        if not self.unsafe:
            raise RuntimeScriptError(
                f"'{feature}' is disabled by default (it runs arbitrary code / installs "
                f"packages). Re-run with --unsafe (CLI) or enable the Unsafe toggle (TUI).",
                line=line,
            )

    async def _exec_python(self, code: str, line: int) -> None:
        self._require_unsafe("python", line)

        local_scope = self.call_stack[-1] if self.call_stack else {}
        namespace: dict[str, Any] = {**self.env, **local_scope}
        namespace["print"] = self.output
        namespace["config"] = self.config
        try:
            await asyncio.to_thread(exec, code, namespace)  # noqa: S102 - opt-in, gated by --unsafe
        except Exception as exc:
            raise RuntimeScriptError(
                f"python block raised {type(exc).__name__}: {exc}", line=line
            ) from exc

        for key, value in namespace.items():
            if key in ("__builtins__", "print", "config"):
                continue
            self._set_var(key, value)

    async def _exec_pip(self, package_expr: Expr, line: int) -> None:
        self._require_unsafe("pip", line)

        package = _format_value(await self.eval_expr(package_expr))
        uv_path = shutil.which("uv")
        # Prefer `uv pip install`: it works in uv-managed venvs, which don't
        # ship a `pip` module at all. Fall back to `python -m pip` otherwise.
        args = (
            [uv_path, "pip", "install", package]
            if uv_path
            else [sys.executable, "-m", "pip", "install", package]
        )
        self.output(f"→ {' '.join(args)}")
        process = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert process.stdout is not None
        async for raw_line in process.stdout:
            self.output("  " + raw_line.decode(errors="replace").rstrip())
        returncode = await process.wait()
        if returncode != 0:
            raise RuntimeScriptError(
                f"pip install {package!r} failed (exit {returncode})", line=line
            )
        self.output(f"  installed {package}")


async def run_script(
    source: str,
    config: NyxorConfig,
    *,
    output: OutputFn = print,
    base_dir: Path | None = None,
    unsafe: bool = False,
    ui: ScriptUI | None = None,
) -> None:
    """Parse and execute a NyxScript source string end to end."""
    program = parse(source)
    await Interpreter(config, output=output, base_dir=base_dir, unsafe=unsafe, ui=ui).run(program)
