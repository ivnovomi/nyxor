"""NyxScript: a small, safe scripting language for batch-driving NYXOR modules.

Pipeline: :mod:`lexer` → :mod:`parser` (produces the :mod:`ast_nodes` tree)
→ either :mod:`linter` (static analysis, no execution) or
:mod:`interpreter` (runs it for real). See docs/architecture.md for the
language reference and grammar.
"""

from __future__ import annotations

from nyxor.core.scripting.ast_nodes import Program
from nyxor.core.scripting.errors import LexError, ParseError, RuntimeScriptError, ScriptError
from nyxor.core.scripting.interpreter import Interpreter, run_script
from nyxor.core.scripting.linter import LintIssue, lint_program, lint_source
from nyxor.core.scripting.parser import parse, parse_expression
from nyxor.core.scripting.stdlib import MODULE_RUNNERS
from nyxor.core.scripting.template import TEMPLATE

__all__ = [
    "TEMPLATE",
    "MODULE_RUNNERS",
    "Program",
    "Interpreter",
    "LintIssue",
    "ScriptError",
    "LexError",
    "ParseError",
    "RuntimeScriptError",
    "run_script",
    "lint_program",
    "lint_source",
    "parse",
    "parse_expression",
]
