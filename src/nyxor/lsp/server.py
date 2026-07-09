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

import re

from lsprotocol import types
from pygls.lsp.server import LanguageServer
from pygls.workspace import TextDocument

from nyxor.core.scripting.lexer import KEYWORDS
from nyxor.core.scripting.linter import LintIssue, lint_source
from nyxor.core.scripting.stdlib import MODULE_RUNNERS

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
_VAR_DEF_RE = re.compile(r"\b(?:set|foreach|as)\s+(\w+)\b")


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


@server.feature(
    types.TEXT_DOCUMENT_COMPLETION,
    types.CompletionOptions(trigger_characters=list("abcdefghijklmnopqrstuvwxyz")),
)
def completions(ls: LanguageServer, params: types.CompletionParams) -> types.CompletionList:
    document = ls.workspace.get_text_document(params.text_document.uri)
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
        types.CompletionItem(label=name, kind=types.CompletionItemKind.Variable)
        for name in variables
    ]
    return types.CompletionList(is_incomplete=False, items=items)


@server.feature(types.TEXT_DOCUMENT_HOVER)
def hover(ls: LanguageServer, params: types.HoverParams) -> types.Hover | None:
    document = ls.workspace.get_text_document(params.text_document.uri)
    lines = document.source.splitlines()
    if params.position.line >= len(lines):
        return None
    line = lines[params.position.line]

    word = None
    for match in _WORD_RE.finditer(line):
        if match.start() <= params.position.character <= match.end():
            word = match.group(0)
            break
    if word is None:
        return None

    doc_text = _ACTION_DOCS.get(word) or (
        f"NYXOR module: {_MODULE_DOCS[word]}" if word in _MODULE_DOCS else None
    )
    if doc_text is None:
        return None
    return types.Hover(contents=types.MarkupContent(kind=types.MarkupKind.Markdown, value=doc_text))


def main() -> None:
    """Run the server over stdio — the transport editors expect."""
    server.start_io()


if __name__ == "__main__":
    main()
