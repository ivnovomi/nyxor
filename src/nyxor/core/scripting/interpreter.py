"""Executes a parsed NyxScript :class:`Program`.

Expression evaluation is synchronous (nothing in the expression grammar
needs I/O); statement execution is async because ``run`` and ``sleep`` do.
"""

from __future__ import annotations

import asyncio
import difflib
import shutil
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from nyxor.core.config import NyxorConfig
from nyxor.core.models import ModuleResult
from nyxor.core.reporting import ReportDocument, get_writer
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
from nyxor.core.scripting.errors import RuntimeScriptError, ScriptError
from nyxor.core.scripting.parser import parse, parse_expression
from nyxor.core.scripting.stdlib import MODULE_RUNNERS

OutputFn = Callable[[str], None]

_FORMAT_BY_SUFFIX = {
    "json": "json",
    "md": "markdown",
    "markdown": "markdown",
    "html": "html",
    "htm": "html",
}

_BIN_OPS: dict[str, Callable[[Any, Any], Any]] = {
    "+": lambda a, b: a + b,
    "-": lambda a, b: a - b,
    "*": lambda a, b: a * b,
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


def _format_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return "[" + ", ".join(_format_value(v) for v in value) + "]"
    return str(value)


class Interpreter:
    """Holds the running script's variable environment and I/O sinks."""

    def __init__(
        self,
        config: NyxorConfig,
        *,
        output: OutputFn = print,
        base_dir: Path | None = None,
        unsafe: bool = False,
    ) -> None:
        self.config = config
        self.output = output
        self.base_dir = base_dir or Path.cwd()
        self.unsafe = unsafe
        self.env: dict[str, Any] = {}

    # -- expressions ---------------------------------------------------------

    def eval_expr(self, expr: Expr) -> Any:
        match expr:
            case Literal(value=str() as raw, line=line):
                return self._interpolate(raw, line)
            case Literal(value=value):
                return value
            case ListLiteral(items=items):
                return [self.eval_expr(item) for item in items]
            case VarRef(name=name, line=line):
                if name not in self.env:
                    raise RuntimeScriptError(f"undefined variable '{name}'", line=line)
                return self.env[name]
            case UnaryOp(op="-", operand=operand, line=line):
                value = self.eval_expr(operand)
                try:
                    return -value
                except TypeError as exc:
                    raise RuntimeScriptError(
                        f"cannot negate a {type(value).__name__}", line=line
                    ) from exc
            case UnaryOp(op="not", operand=operand):
                return not _truthy(self.eval_expr(operand))
            case BinOp(op="and", left=left, right=right):
                left_value = self.eval_expr(left)
                return self.eval_expr(right) if _truthy(left_value) else left_value
            case BinOp(op="or", left=left, right=right):
                left_value = self.eval_expr(left)
                return left_value if _truthy(left_value) else self.eval_expr(right)
            case BinOp(op=op, left=left, right=right, line=line):
                left_value = self.eval_expr(left)
                right_value = self.eval_expr(right)
                try:
                    return _BIN_OPS[op](left_value, right_value)
                except TypeError as exc:
                    lt, rt = type(left_value).__name__, type(right_value).__name__
                    raise RuntimeScriptError(
                        f"cannot apply '{op}' to {lt} and {rt}", line=line
                    ) from exc
                except ZeroDivisionError as exc:
                    raise RuntimeScriptError("division by zero", line=line) from exc
        raise RuntimeScriptError(f"cannot evaluate expression: {expr!r}")

    def _interpolate(self, raw: str, line: int) -> str:
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
                out.append(_format_value(self.eval_expr(expr)))
                i = end + 1
                continue
            out.append(ch)
            i += 1
        return "".join(out)

    # -- statements ------------------------------------------------------------

    async def run(self, program: Program) -> None:
        await self.exec_block(program.body)

    async def exec_block(self, statements: list[Stmt]) -> None:
        for statement in statements:
            await self.exec_stmt(statement)

    async def exec_stmt(self, statement: Stmt) -> None:
        match statement:
            case SetStmt(name=name, value=value):
                self.env[name] = self.eval_expr(value)
            case PrintStmt(value=value):
                self.output(_format_value(self.eval_expr(value)))
            case SleepStmt(value=value, line=line):
                duration = self.eval_expr(value)
                if not isinstance(duration, int | float) or isinstance(duration, bool):
                    raise RuntimeScriptError(
                        f"'sleep' expects a number, got {type(duration).__name__}", line=line
                    )
                await asyncio.sleep(float(duration))
            case AssertStmt(condition=condition, message=message, line=line):
                if not _truthy(self.eval_expr(condition)):
                    text = _format_value(self.eval_expr(message)) if message else "assertion failed"
                    raise RuntimeScriptError(text, line=line)
            case FailStmt(message=message, line=line):
                raise RuntimeScriptError(_format_value(self.eval_expr(message)), line=line)
            case RunStmt(module=module, target=target, var_name=var_name, line=line):
                await self._exec_run(module, target, var_name, line)
            case SaveStmt(var_name=var_name, path=path, line=line):
                self._exec_save(var_name, path, line)
            case IfStmt(condition=condition, then_body=then_body, else_body=else_body):
                if _truthy(self.eval_expr(condition)):
                    await self.exec_block(then_body)
                else:
                    await self.exec_block(else_body)
            case ForeachStmt(var_name=var_name, iterable=iterable, body=body, line=line):
                values = self.eval_expr(iterable)
                if not isinstance(values, list):
                    raise RuntimeScriptError(
                        f"'foreach' needs a list, got {type(values).__name__}", line=line
                    )
                for item in values:
                    self.env[var_name] = item
                    await self.exec_block(body)
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

        target = _format_value(self.eval_expr(target_expr))
        self.output(f"→ run {module} {target}")
        results = await runner(target, self.config)
        total = sum(len(r.findings) for r in results)
        self.output(f"  {total} finding(s) across {len(results)} module result(s)")
        if var_name:
            self.env[var_name] = results

    def _exec_save(self, var_name: str, path_expr: Expr, line: int) -> None:
        if var_name not in self.env:
            raise RuntimeScriptError(f"undefined variable '{var_name}'", line=line)
        results = self.env[var_name]
        if isinstance(results, ModuleResult):
            results = [results]
        if not isinstance(results, list) or not all(isinstance(r, ModuleResult) for r in results):
            raise RuntimeScriptError(
                f"'{var_name}' doesn't hold scan results — did you mean 'run ... as {var_name}'?",
                line=line,
            )

        path_str = _format_value(self.eval_expr(path_expr))
        path = self.base_dir / path_str
        fmt = _FORMAT_BY_SUFFIX.get(path.suffix.lstrip(".").lower(), "json")
        document = ReportDocument(title="NYXOR Script Report", results=results)
        get_writer(fmt).write(document, path)
        self.output(f"  saved -> {path}")

    def _require_unsafe(self, feature: str, line: int) -> None:
        if not self.unsafe:
            raise RuntimeScriptError(
                f"'{feature}' is disabled by default (it runs arbitrary code / installs "
                f"packages). Re-run with --unsafe (CLI) or enable the Unsafe toggle (TUI).",
                line=line,
            )

    async def _exec_python(self, code: str, line: int) -> None:
        self._require_unsafe("python", line)

        namespace: dict[str, Any] = dict(self.env)
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
            self.env[key] = value

    async def _exec_pip(self, package_expr: Expr, line: int) -> None:
        self._require_unsafe("pip", line)

        package = _format_value(self.eval_expr(package_expr))
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
) -> None:
    """Parse and execute a NyxScript source string end to end."""
    program = parse(source)
    await Interpreter(config, output=output, base_dir=base_dir, unsafe=unsafe).run(program)
