"""Pure NyxScript analysis for editor tooling — hover, go-to-definition,
and import-path completion.

Deliberately has no `pygls`/`lsprotocol` import: it only depends on
`nyxor.core.scripting`, which is always installed (the `lsp` extra is
optional). That keeps this module testable and reusable without needing
the LSP stack at all, and keeps `server.py` itself a thin adapter over it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from nyxor.core.scripting import FuncDef, ImportStmt, Program, function_docstring, parse
from nyxor.core.scripting.ast_nodes import Literal
from nyxor.core.scripting.errors import ScriptError


@dataclass(frozen=True)
class FunctionInfo:
    name: str
    params: list[str]
    doc: str | None
    line: int  # 1-indexed, matches every other line number in NyxScript


@dataclass(frozen=True)
class ImportInfo:
    alias: str
    path: str
    line: int


def parse_best_effort(source: str) -> Program | None:
    """Like `parse()`, but a syntax error means "no info available", not a crash."""
    try:
        return parse(source)
    except ScriptError:
        return None


def top_level_functions(program: Program) -> dict[str, FunctionInfo]:
    """Every `func` defined at the top level of a program (not nested ones)."""
    functions: dict[str, FunctionInfo] = {}
    for stmt in program.body:
        if isinstance(stmt, FuncDef):
            functions[stmt.name] = FunctionInfo(
                name=stmt.name,
                params=stmt.params,
                doc=function_docstring(stmt.body),
                line=stmt.line,
            )
    return functions


def top_level_imports(program: Program) -> dict[str, ImportInfo]:
    """Every `import "..." as alias` whose path is a literal string.

    (The only form the interpreter itself actually supports at runtime —
    `import` requires a string, even though the grammar technically allows
    any expression there.)
    """
    imports: dict[str, ImportInfo] = {}
    for stmt in program.body:
        if (
            isinstance(stmt, ImportStmt)
            and isinstance(stmt.path, Literal)
            and isinstance(stmt.path.value, str)
        ):
            imports[stmt.alias] = ImportInfo(alias=stmt.alias, path=stmt.path.value, line=stmt.line)
    return imports


def function_signature(info: FunctionInfo) -> str:
    return f"func {info.name}({', '.join(info.params)})"


def function_hover_text(info: FunctionInfo, *, source_label: str | None = None) -> str:
    heading = f"```nyxscript\n{function_signature(info)}\n```"
    body = info.doc or "*(no docstring)*"
    if source_label:
        return f"{heading}\n\n{body}\n\n*from `{source_label}`*"
    return f"{heading}\n\n{body}"


def resolve_import_path(base_dir: Path, import_path: str) -> Path:
    """Where `import "import_path" as x` actually reads from.

    Matches the interpreter's own resolution rule (`Interpreter._exec_import`):
    always relative to the running script's base_dir, never to the
    importing file's own directory. For editor tooling, `base_dir` is the
    workspace root — the same convention this project's own example
    libraries use (`import "lib/foo.nyx" as foo`, run from the repo root).
    """
    return (base_dir / import_path).resolve()


def find_nyx_files(root: Path, *, limit: int = 200) -> list[Path]:
    """Every `.nyx` file under `root`, for import-path completion."""
    if not root.is_dir():
        return []
    return sorted(root.rglob("*.nyx"))[:limit]
