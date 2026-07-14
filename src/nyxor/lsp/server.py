"""A real Language Server for NyxScript, built on `pygls`.

Any LSP-capable editor (Neovim, VS Code, Helix, ...) can point a generic
LSP client at ``nyx script lsp`` (which just runs this over stdio) and get
live diagnostics, completion, and hover for ``.nyx`` files — the exact same
linter and keyword/module list the CLI and TUI use, just served over the
protocol instead of printed to a terminal.

Requires the optional ``lsp`` extra (``uv sync --extra lsp``); imported
lazily by the CLI so the base install doesn't need pygls at all.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.uris import to_fs_path
from pygls.workspace import TextDocument

from nyxor.core.scripting.builtins import BUILTIN_FUNCTIONS
from nyxor.core.scripting.lexer import KEYWORDS
from nyxor.core.scripting.linter import LintIssue, lint_source
from nyxor.core.scripting.sockets import SOCKET_FUNCTIONS
from nyxor.core.scripting.stdlib import MODULE_RUNNERS
from nyxor.core.scripting.ui import UI_FUNCTIONS
from nyxor.lsp.analysis import (
    FunctionInfo,
    find_nyx_files,
    function_hover_text,
    function_signature,
    parse_best_effort,
    resolve_import_path,
    scan_imports,
    top_level_functions,
    top_level_imports,
)

server = LanguageServer("nyxscript-lsp", "v0.1.0")

_ACTION_DOCS = {
    "set": "`set NAME = EXPR` — assign a variable.",
    "if": "`if EXPR:` ... `else:` ... `end` — conditional branch.",
    "foreach": "`foreach VAR in LIST:` ... `end` — loop over a list.",
    "run": "`run MODULE TARGET [as VAR]` — run a NYXOR module against a target.",
    "save": '`save VAR to "path.ext"` — write scan results (.json/.md/.html).',
    "print": "`print EXPR` — write a line to the script's output log.",
    "assert": '`assert EXPR[, "message"]` — abort the script if EXPR is false.',
    "fail": '`fail "message"` — abort the script unconditionally.',
    "sleep": "`sleep SECONDS` — pause the script.",
    "pip": '`pip "package"` — install a package (requires --unsafe).',
    "func": "`func NAME(params):` ... `return EXPR` ... `end` — define a function.",
    "return": "`return [EXPR]` — return from the current function.",
    "while": "`while EXPR:` ... `end` — loop while EXPR is true.",
    "break": "`break` — exit the current loop.",
    "continue": "`continue` — skip to the next loop iteration.",
    "import": '`import "lib.nyx" as NAME` — load functions from another script.',
    "unsafe": "`unsafe` — self-enables 'python:'/'pip' for the rest of this script.",
}

_BUILTIN_DOCS = {
    "len": "`len(x)` — length of a list or string.",
    "range": "`range(n)` / `range(a, b)` / `range(a, b, step)` — a list of integers.",
    "upper": "`upper(s)` — uppercase a string.",
    "lower": "`lower(s)` — lowercase a string.",
    "strip": "`strip(s)` — trim whitespace from both ends.",
    "split": "`split(s, sep)` — split a string into a list.",
    "join": "`join(list, sep)` — join a list into a string.",
    "contains": "`contains(collection, item)` — membership test.",
    "str": "`str(x)` — convert to a string.",
    "int": "`int(x)` — convert to an integer.",
    "float": "`float(x)` — convert to a float.",
    "abs": "`abs(x)` — absolute value.",
    "round": "`round(x[, digits])` — round a number.",
    "sorted": "`sorted(list)` — a new sorted list.",
    "reversed": "`reversed(list)` — a new reversed list.",
    "min": "`min(list)` / `min(a, b, ...)` — smallest value.",
    "max": "`max(list)` / `max(a, b, ...)` — largest value.",
    "sum": "`sum(list)` — total of a list of numbers.",
    "type_of": "`type_of(x)` — the runtime type name as a string.",
    "now": "`now()` — the current time as Unix epoch seconds (a float).",
    "to_iso8601": "`to_iso8601(epoch)` — formats epoch seconds as an ISO 8601 UTC string.",
    "sha256": "`sha256(s)` — the SHA-256 hex digest of s.",
    "md5": "`md5(s)` — the MD5 hex digest of s (fingerprinting/dedup, not password hashing).",
    "regex_match": "`regex_match(text, pattern)` — true if pattern matches anywhere in text.",
    "regex_find": "`regex_find(text, pattern, default)` — first match, or default if none.",
    "regex_find_all": "`regex_find_all(text, pattern)` — every match as a list.",
    "regex_replace": "`regex_replace(text, pattern, replacement)` — substitutes every match.",
    "base64_encode": "`base64_encode(s)` — base64-encodes s (UTF-8 encoded first).",
    "base64_decode": "`base64_decode(s)` — decodes base64 s back to a UTF-8 string.",
    "random": "`random()` — a random float in [0.0, 1.0).",
    "bytes_from_hex": "`bytes_from_hex(s)` — hex string to a list of byte values (0-255).",
    "bytes_to_hex": "`bytes_to_hex(list)` — a list of byte values to a hex string.",
    "bytes_from_string": "`bytes_from_string(s)` — UTF-8 encodes s to a list of byte values.",
    "bytes_to_string": "`bytes_to_string(list)` — decodes a list of byte values as UTF-8.",
    "pack_uint16": "`pack_uint16(n)` — n as 2 big-endian bytes (a list).",
    "pack_uint32": "`pack_uint32(n)` — n as 4 big-endian bytes (a list).",
    "unpack_uint16": "`unpack_uint16(list)` — 2 big-endian bytes back to an int.",
    "unpack_uint32": "`unpack_uint32(list)` — 4 big-endian bytes back to an int.",
    "checksum": "`checksum(list)` — the Internet checksum (RFC 1071) of a list of byte values.",
    "build_ip_header": "`build_ip_header(src_ip, dst_ip, protocol, payload[, ttl][, id]"
    "[, dont_fragment])` — a 20-byte IPv4 header with checksum filled in.",
    "build_tcp_header": "`build_tcp_header(src_ip, dst_ip, src_port, dst_port, seq, ack, "
    "flags, payload[, window])` — a 20-byte TCP header with checksum filled in; flags "
    'is an int bitmask or a string like "SYN,ACK".',
    "build_udp_header": "`build_udp_header(src_ip, dst_ip, src_port, dst_port, payload)` "
    "— an 8-byte UDP header with checksum filled in.",
    "build_icmp_echo": "`build_icmp_echo(identifier, sequence, payload[, is_reply])` — "
    "an ICMP echo request/reply packet with checksum filled in.",
}

_UI_DOCS = {
    "ui.confirm": '`ui.confirm("question?")` — yes/no prompt, returns bool.',
    "ui.input": '`ui.input("prompt")` — free-text prompt, returns a string.',
    "ui.select": '`ui.select("prompt", ["a", "b"])` — choice prompt, returns a string.',
    "ui.table": "`ui.table(headers, rows)` — print a table.",
    "ui.banner": '`ui.banner("text")` — print a rule with a heading.',
    "ui.status": '`ui.status("message")` — print a status line.',
}

_SOCKET_DOCS = {
    "socket.connect": "`socket.connect(host, port[, protocol][, timeout])` — opens a TCP/UDP "
    "connection, returns a handle. Requires --unsafe.",
    "socket.send": "`socket.send(handle, data)` — sends a string or list of byte values.",
    "socket.recv": "`socket.recv(handle[, max_bytes][, timeout])` — reads bytes as a list of ints.",
    "socket.recv_text": "`socket.recv_text(handle[, max_bytes][, timeout])` — reads bytes "
    "as UTF-8.",
    "socket.close": "`socket.close(handle)` — closes the connection (also valid for a "
    "raw_recv handle).",
    "socket.raw_send": "`socket.raw_send(dst_ip, packet[, timeout])` — sends one complete "
    "IP packet via IP_HDRINCL. Needs root on Linux/macOS; not usable on Windows (blocked "
    "by the OS even for an administrator).",
    "socket.raw_recv": "`socket.raw_recv(interface_ip[, timeout])` — opens a raw capture "
    "socket bound to a local interface, returns a handle. Requires administrator/root.",
    "socket.raw_read": "`socket.raw_read(handle[, max_bytes][, timeout])` — reads one "
    "captured IP packet (header included) as a list of byte values.",
}

_MODULE_DOCS = {
    "audit": "Combined DNS + TLS + HTTP assessment for a domain.",
    "dns": "DNS record lookup, DNSSEC, and mail record checks.",
    "tls": "Certificate inspection, expiry, protocol/cipher overview.",
    "http": "Response headers, redirects, cookies, security headers.",
    "network.discover": "Host discovery via ping sweep / CIDR range.",
    "network.scan": "TCP service enumeration on a single host.",
}

_WORD_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_VAR_DEF_RE = re.compile(r"\b(?:set|foreach|as|func)\s+(\w+)\b")
_IMPORT_PATH_RE = re.compile(r'\bimport\s+"([^"]*)$')
_MEMBER_ACCESS_RE = re.compile(r"([A-Za-z_]\w*)\.\w*$")


def _word_at(document: TextDocument, position: types.Position) -> str | None:
    lines = document.source.splitlines()
    if position.line >= len(lines):
        return None
    line = lines[position.line]
    for match in _WORD_RE.finditer(line):
        if match.start() <= position.character <= match.end():
            return match.group(0)
    return None


def _resolve_function_reference(
    ls: LanguageServer, document: TextDocument, word: str
) -> tuple[str, FunctionInfo, str | None] | None:
    """Find a `func` a hover/definition word refers to — same file or an
    imported library. Returns (uri, info, a friendly relative-path label —
    or None when it's defined in this same document)."""
    program = parse_best_effort(document.source)
    if program is None:
        return None

    functions = top_level_functions(program)
    if word in functions:
        return document.uri, functions[word], None

    if "." not in word:
        return None
    alias, member = word.split(".", 1)
    imports = top_level_imports(program)
    root_path = ls.workspace.root_path
    if alias not in imports or not root_path:
        return None

    root = Path(root_path)
    target = resolve_import_path(root, imports[alias].path)
    if not target.is_file():
        return None
    lib_program = parse_best_effort(target.read_text(encoding="utf-8"))
    if lib_program is None:
        return None
    lib_functions = top_level_functions(lib_program)
    if member not in lib_functions:
        return None
    try:
        label = target.relative_to(root).as_posix()
    except ValueError:
        label = str(target)
    return target.as_uri(), lib_functions[member], label


def _severity_for(issue: LintIssue) -> types.DiagnosticSeverity:
    return (
        types.DiagnosticSeverity.Error
        if issue.severity == "error"
        else types.DiagnosticSeverity.Warning
    )


def _publish_diagnostics(ls: LanguageServer, document: TextDocument) -> None:
    issues = lint_source(document.source)
    diagnostics = [
        types.Diagnostic(
            range=types.Range(
                start=types.Position(line=max(issue.line - 1, 0), character=0),
                end=types.Position(line=max(issue.line - 1, 0), character=200),
            ),
            message=issue.message,
            severity=_severity_for(issue),
            source="nyxscript",
        )
        for issue in issues
    ]
    ls.text_document_publish_diagnostics(
        types.PublishDiagnosticsParams(uri=document.uri, diagnostics=diagnostics)
    )


@server.feature(types.TEXT_DOCUMENT_DID_OPEN)
def did_open(ls: LanguageServer, params: types.DidOpenTextDocumentParams) -> None:
    _publish_diagnostics(ls, ls.workspace.get_text_document(params.text_document.uri))


@server.feature(types.TEXT_DOCUMENT_DID_CHANGE)
def did_change(ls: LanguageServer, params: types.DidChangeTextDocumentParams) -> None:
    _publish_diagnostics(ls, ls.workspace.get_text_document(params.text_document.uri))


@server.feature(types.TEXT_DOCUMENT_DID_SAVE)
def did_save(ls: LanguageServer, params: types.DidSaveTextDocumentParams) -> None:
    _publish_diagnostics(ls, ls.workspace.get_text_document(params.text_document.uri))


def _same_file(path: Path, uri: str) -> bool:
    """Compare a filesystem path against a `file://` URI, ignoring the

    drive-letter-case differences Windows LSP clients are inconsistent
    about (`file:///C:/...` vs `file:///c:/...` refer to the same file).
    """
    fs_path = to_fs_path(uri)
    if fs_path is None:
        return False
    return os.path.normcase(str(path)) == os.path.normcase(fs_path)


def _import_path_completions(ls: LanguageServer, current_uri: str) -> types.CompletionList:
    root_path = ls.workspace.root_path
    if not root_path:
        return types.CompletionList(is_incomplete=False, items=[])
    root = Path(root_path)
    items = [
        types.CompletionItem(
            label=path.relative_to(root).as_posix(),
            kind=types.CompletionItemKind.File,
            detail="NyxScript library",
        )
        for path in find_nyx_files(root)
        if not _same_file(path, current_uri)  # importing yourself isn't a useful suggestion
    ]
    return types.CompletionList(is_incomplete=False, items=items)


def _module_member_completions(
    ls: LanguageServer, document: TextDocument, alias: str
) -> types.CompletionList | None:
    """Completions for `alias.<partial>` — the functions of an imported

    library, resolved the same way hover/go-to-definition already do (an
    editor typing `asset.` should see `by_kind`, `kinds`, etc., not the
    generic keyword/builtin soup). Returns None when `alias` isn't `ui`,
    `socket`, or a known import in this document, so the caller can fall
    back sanely.
    """
    if alias == "ui":
        return types.CompletionList(
            is_incomplete=False,
            items=[
                types.CompletionItem(
                    label=name,
                    kind=types.CompletionItemKind.Function,
                    detail=_UI_DOCS.get(f"ui.{name}", ""),
                )
                for name in sorted(UI_FUNCTIONS)
            ],
        )
    if alias == "socket":
        return types.CompletionList(
            is_incomplete=False,
            items=[
                types.CompletionItem(
                    label=name,
                    kind=types.CompletionItemKind.Function,
                    detail=_SOCKET_DOCS.get(f"socket.{name}", ""),
                )
                for name in sorted(SOCKET_FUNCTIONS)
            ],
        )

    imports = scan_imports(document.source)
    if alias not in imports:
        return None

    root_path = ls.workspace.root_path
    if not root_path:
        return None
    target = resolve_import_path(Path(root_path), imports[alias])
    if not target.is_file():
        return None
    lib_program = parse_best_effort(target.read_text(encoding="utf-8"))
    if lib_program is None:
        return None

    functions = top_level_functions(lib_program)
    return types.CompletionList(
        is_incomplete=False,
        items=[
            types.CompletionItem(
                label=name,
                kind=types.CompletionItemKind.Function,
                detail=function_signature(info),
                documentation=types.MarkupContent(
                    kind=types.MarkupKind.Markdown, value=info.doc or "*(no docstring)*"
                ),
            )
            for name, info in sorted(functions.items())
        ],
    )


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION,
    types.CompletionOptions(trigger_characters=[*"abcdefghijklmnopqrstuvwxyz", '"', "."]),
)
def completions(ls: LanguageServer, params: types.CompletionParams) -> types.CompletionList:
    document = ls.workspace.get_text_document(params.text_document.uri)

    lines = document.source.splitlines()
    if params.position.line < len(lines):
        before_cursor = lines[params.position.line][: params.position.character]
        if _IMPORT_PATH_RE.search(before_cursor):
            return _import_path_completions(ls, document.uri)

        member_match = _MEMBER_ACCESS_RE.search(before_cursor)
        if member_match:
            member_completions = _module_member_completions(ls, document, member_match.group(1))
            # A dot that isn't a recognized module/import alias (e.g. still
            # mid-typing) shouldn't fall through to the generic keyword
            # list — none of those can ever be valid there.
            return member_completions or types.CompletionList(is_incomplete=False, items=[])

    variables = sorted(set(_VAR_DEF_RE.findall(document.source)))

    items = [
        types.CompletionItem(label=word, kind=types.CompletionItemKind.Keyword)
        for word in sorted(KEYWORDS)
    ]
    items += [
        types.CompletionItem(
            label=name,
            kind=types.CompletionItemKind.Module,
            detail=_MODULE_DOCS.get(name, ""),
        )
        for name in sorted(MODULE_RUNNERS)
    ]
    items += [
        types.CompletionItem(
            label=name,
            kind=types.CompletionItemKind.Function,
            detail=_BUILTIN_DOCS.get(name, ""),
        )
        for name in sorted(BUILTIN_FUNCTIONS)
    ]
    items += [
        types.CompletionItem(
            label=f"ui.{name}",
            kind=types.CompletionItemKind.Function,
            detail=_UI_DOCS.get(f"ui.{name}", ""),
        )
        for name in sorted(UI_FUNCTIONS)
    ]
    items += [
        types.CompletionItem(
            label=f"socket.{name}",
            kind=types.CompletionItemKind.Function,
            detail=_SOCKET_DOCS.get(f"socket.{name}", ""),
        )
        for name in sorted(SOCKET_FUNCTIONS)
    ]
    items += [
        types.CompletionItem(label=name, kind=types.CompletionItemKind.Variable)
        for name in variables
    ]
    return types.CompletionList(is_incomplete=False, items=items)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(ls: LanguageServer, params: types.HoverParams) -> types.Hover | None:
    document = ls.workspace.get_text_document(params.text_document.uri)
    word = _word_at(document, params.position)
    if word is None:
        return None

    resolved = _resolve_function_reference(ls, document, word)
    if resolved is not None:
        _uri, info, source_label = resolved
        return types.Hover(
            contents=types.MarkupContent(
                kind=types.MarkupKind.Markdown,
                value=function_hover_text(info, source_label=source_label),
            )
        )

    doc_text = (
        _ACTION_DOCS.get(word)
        or _BUILTIN_DOCS.get(word)
        or _UI_DOCS.get(word)
        or _SOCKET_DOCS.get(word)
        or (f"NYXOR module: {_MODULE_DOCS[word]}" if word in _MODULE_DOCS else None)
    )
    if doc_text is None:
        return None
    return types.Hover(contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value=doc_text))


@server.feature(types.TEXT_DOCUMENT_DEFINITION)
def definition(ls: LanguageServer, params: types.DefinitionParams) -> types.Location | None:
    document = ls.workspace.get_text_document(params.text_document.uri)
    word = _word_at(document, params.position)
    if word is None:
        return None

    resolved = _resolve_function_reference(ls, document, word)
    if resolved is None:
        return None
    uri, info, _label = resolved
    target_line = max(info.line - 1, 0)
    return types.Location(
        uri=uri,
        range=types.Range(
            start=types.Position(line=target_line, character=0),
            end=types.Position(line=target_line, character=200),
        ),
    )


def main() -> None:
    """Run the server over stdio — the transport editors expect."""
    server.start_io()


if __name__ == "__main__":
    main()
