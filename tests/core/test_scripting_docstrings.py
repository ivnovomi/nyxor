from __future__ import annotations

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, parse
from nyxor.core.scripting.ast_nodes import DocStmt, FuncDef, function_docstring
from nyxor.core.scripting.interpreter import Interpreter


def test_bare_string_parses_as_a_doc_statement() -> None:
    program = parse('"hello"\n')
    assert len(program.body) == 1
    assert isinstance(program.body[0], DocStmt)
    assert program.body[0].text == "hello"


def test_function_docstring_extracts_the_first_statement() -> None:
    program = parse(
        """
func square(x):
    "Returns x squared."
    return x * x
end
"""
    )
    funcdef = program.body[0]
    assert isinstance(funcdef, FuncDef)
    assert function_docstring(funcdef.body) == "Returns x squared."


def test_function_docstring_is_none_without_one() -> None:
    program = parse(
        """
func square(x):
    return x * x
end
"""
    )
    funcdef = program.body[0]
    assert isinstance(funcdef, FuncDef)
    assert function_docstring(funcdef.body) is None


def test_docstring_only_body_is_not_flagged_as_empty_by_the_linter() -> None:
    issues = lint_source(
        """
func placeholder():
    "Not implemented yet."
end
"""
    )
    assert issues == []


async def test_docstring_is_a_no_op_at_runtime() -> None:
    outputs: list[str] = []
    interpreter = Interpreter(load_config(), output=outputs.append)
    await interpreter.run(
        parse(
            """
func square(x):
    "Returns x squared."
    return x * x
end

print square(4)
"""
        )
    )
    assert outputs == ["16"]


async def test_nyx_function_carries_its_docstring() -> None:
    interpreter = Interpreter(load_config())
    await interpreter.run(
        parse(
            """
func square(x):
    "Returns x squared."
    return x * x
end
"""
        )
    )
    from nyxor.core.scripting.interpreter import NyxFunction

    fn = interpreter.env["square"]
    assert isinstance(fn, NyxFunction)
    assert fn.doc == "Returns x squared."
