from __future__ import annotations

from pathlib import Path

from nyxor.lsp.analysis import (
    find_nyx_files,
    function_hover_text,
    parse_best_effort,
    resolve_import_path,
    top_level_functions,
    top_level_imports,
)


def test_parse_best_effort_returns_none_on_syntax_error() -> None:
    assert parse_best_effort("if true\n") is None  # missing ':'


def test_parse_best_effort_returns_a_program_for_valid_source() -> None:
    program = parse_best_effort("print 1\n")
    assert program is not None
    assert len(program.body) == 1


def test_top_level_functions_finds_params_and_docstring() -> None:
    program = parse_best_effort(
        """
func square(x):
    "Returns x squared."
    return x * x
end
"""
    )
    assert program is not None
    functions = top_level_functions(program)
    assert set(functions) == {"square"}
    assert functions["square"].params == ["x"]
    assert functions["square"].doc == "Returns x squared."
    assert functions["square"].line == 2


def test_top_level_functions_ignores_nested_defs() -> None:
    # Only the top-level scan is used for import/hover resolution — a func
    # defined inside another func's body isn't importable as a library member.
    program = parse_best_effort(
        """
func outer():
    func inner():
        return 1
    end
end
"""
    )
    assert program is not None
    assert set(top_level_functions(program)) == {"outer"}


def test_top_level_imports_only_captures_string_literal_paths() -> None:
    program = parse_best_effort('import "lib/mathlib.nyx" as math\n')
    assert program is not None
    imports = top_level_imports(program)
    assert imports["math"].path == "lib/mathlib.nyx"
    assert imports["math"].line == 1


def test_resolve_import_path_is_relative_to_the_given_base(tmp_path: Path) -> None:
    resolved = resolve_import_path(tmp_path, "lib/mathlib.nyx")
    assert resolved == (tmp_path / "lib" / "mathlib.nyx").resolve()


def test_find_nyx_files_only_returns_nyx_extension(tmp_path: Path) -> None:
    (tmp_path / "a.nyx").write_text("print 1\n")
    (tmp_path / "b.py").write_text("print(1)\n")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.nyx").write_text("print 2\n")

    found = {p.name for p in find_nyx_files(tmp_path)}
    assert found == {"a.nyx", "c.nyx"}


def test_find_nyx_files_on_a_nonexistent_root_returns_nothing(tmp_path: Path) -> None:
    assert find_nyx_files(tmp_path / "does-not-exist") == []


def test_function_hover_text_includes_signature_and_doc() -> None:
    program = parse_best_effort(
        """
func greet(name):
    "Says hello."
    print name
end
"""
    )
    assert program is not None
    info = top_level_functions(program)["greet"]
    text = function_hover_text(info)
    assert "func greet(name)" in text
    assert "Says hello." in text


def test_function_hover_text_notes_missing_docstring() -> None:
    program = parse_best_effort("func greet(name):\n    print name\nend\n")
    assert program is not None
    info = top_level_functions(program)["greet"]
    assert "no docstring" in function_hover_text(info)


def test_function_hover_text_includes_source_label_when_given() -> None:
    program = parse_best_effort("func square(x):\n    return x * x\nend\n")
    assert program is not None
    info = top_level_functions(program)["square"]
    text = function_hover_text(info, source_label="lib/mathlib.nyx")
    assert "lib/mathlib.nyx" in text
