from __future__ import annotations

from pathlib import Path

from lsprotocol import types
from pygls.workspace import Workspace

from nyxor.lsp.server import completions, definition, hover


def _workspace_with(base: Path, files: dict[str, str]) -> Workspace:
    ws = Workspace(base.as_uri())
    for relative, text in files.items():
        path = base / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        ws.put_text_document(
            types.TextDocumentItem(uri=path.as_uri(), language_id="nyxscript", version=1, text=text)
        )
    return ws


def _pos(line: int, char: int) -> types.Position:
    return types.Position(line=line, character=char)


def test_hover_on_a_local_function_shows_its_docstring(server, tmp_path: Path) -> None:
    main_source = (
        'func triple(x):\n    "Multiplies x by three."\n    return x * 3\nend\n\nprint triple(5)\n'
    )
    ws = _workspace_with(tmp_path, {"main.nyx": main_source})
    server.protocol._workspace = ws
    uri = (tmp_path / "main.nyx").as_uri()

    result = hover(
        server,
        types.HoverParams(text_document=types.TextDocumentIdentifier(uri=uri), position=_pos(5, 8)),
    )

    assert result is not None
    assert "func triple(x)" in result.contents.value
    assert "Multiplies x by three." in result.contents.value


def test_hover_on_an_imported_function_shows_its_docstring_and_source(
    server, tmp_path: Path
) -> None:
    main_source = 'import "lib/mathlib.nyx" as math\n\nprint math.square(4)\n'
    lib_source = 'func square(x):\n    "Returns x squared."\n    return x * x\nend\n'
    ws = _workspace_with(tmp_path, {"main.nyx": main_source, "lib/mathlib.nyx": lib_source})
    server.protocol._workspace = ws
    uri = (tmp_path / "main.nyx").as_uri()

    result = hover(
        server,
        types.HoverParams(
            text_document=types.TextDocumentIdentifier(uri=uri), position=_pos(2, 11)
        ),
    )

    assert result is not None
    assert "func square(x)" in result.contents.value
    assert "Returns x squared." in result.contents.value
    assert "mathlib.nyx" in result.contents.value


def test_hover_still_works_for_keywords(server, tmp_path: Path) -> None:
    ws = _workspace_with(tmp_path, {"main.nyx": "set x = 1\n"})
    server.protocol._workspace = ws
    uri = (tmp_path / "main.nyx").as_uri()

    result = hover(
        server,
        types.HoverParams(text_document=types.TextDocumentIdentifier(uri=uri), position=_pos(0, 1)),
    )
    assert result is not None
    assert "set NAME" in result.contents.value


def test_definition_on_a_local_function_points_at_its_func_line(server, tmp_path: Path) -> None:
    main_source = "func triple(x):\n    return x * 3\nend\n\nprint triple(5)\n"
    ws = _workspace_with(tmp_path, {"main.nyx": main_source})
    server.protocol._workspace = ws
    uri = (tmp_path / "main.nyx").as_uri()

    location = definition(
        server,
        types.DefinitionParams(
            text_document=types.TextDocumentIdentifier(uri=uri), position=_pos(4, 8)
        ),
    )

    assert location is not None
    assert location.uri == uri
    assert location.range.start.line == 0  # `func triple(x):` is line 1 (0-indexed: 0)


def test_definition_on_an_imported_function_points_at_the_library_file(
    server, tmp_path: Path
) -> None:
    main_source = 'import "lib/mathlib.nyx" as math\n\nprint math.square(4)\n'
    lib_source = "func square(x):\n    return x * x\nend\n"
    ws = _workspace_with(tmp_path, {"main.nyx": main_source, "lib/mathlib.nyx": lib_source})
    server.protocol._workspace = ws
    uri = (tmp_path / "main.nyx").as_uri()

    location = definition(
        server,
        types.DefinitionParams(
            text_document=types.TextDocumentIdentifier(uri=uri), position=_pos(2, 11)
        ),
    )

    assert location is not None
    assert location.uri == (tmp_path / "lib" / "mathlib.nyx").as_uri()
    assert location.range.start.line == 0


def test_definition_on_a_non_function_word_returns_none(server, tmp_path: Path) -> None:
    ws = _workspace_with(tmp_path, {"main.nyx": "set x = 1\n"})
    server.protocol._workspace = ws
    uri = (tmp_path / "main.nyx").as_uri()

    location = definition(
        server,
        types.DefinitionParams(
            text_document=types.TextDocumentIdentifier(uri=uri), position=_pos(0, 5)
        ),
    )
    assert location is None


def test_import_path_completion_lists_nyx_files_relative_to_the_root(
    server, tmp_path: Path
) -> None:
    ws = _workspace_with(
        tmp_path,
        {
            "main.nyx": 'import "',
            "lib/mathlib.nyx": "func square(x):\n    return x * x\nend\n",
        },
    )
    server.protocol._workspace = ws
    uri = (tmp_path / "main.nyx").as_uri()

    result = completions(
        server,
        types.CompletionParams(
            text_document=types.TextDocumentIdentifier(uri=uri), position=_pos(0, len('import "'))
        ),
    )

    labels = {item.label for item in result.items}
    assert "lib/mathlib.nyx" in labels
    assert "main.nyx" not in labels  # importing the file you're editing makes no sense


def test_normal_completion_is_unaffected_outside_an_import_statement(
    server, tmp_path: Path
) -> None:
    ws = _workspace_with(tmp_path, {"main.nyx": "pri"})
    server.protocol._workspace = ws
    uri = (tmp_path / "main.nyx").as_uri()

    result = completions(
        server,
        types.CompletionParams(
            text_document=types.TextDocumentIdentifier(uri=uri), position=_pos(0, 3)
        ),
    )
    labels = {item.label for item in result.items}
    assert "print" in labels
