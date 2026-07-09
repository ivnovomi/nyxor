# Architecture

Three front-ends — a CLI, a full-screen TUI, and a Language Server any
editor can talk to — and every single one of them calls the *same* async
functions to do real work. Nothing is reimplemented twice. That single
decision is what makes the rest of this document short: once you understand
the Core/plugin split and the "one scan, two front-ends" pattern below,
you've understood most of how NYXOR is put together.

## Layout

```
src/nyxor/
  core/            # CLI, config, plugin loader, events, logging, interfaces, reporting, scoring
    reporting/     # ReportDocument + JSON/Markdown/HTML writers
    scripting/     # NyxScript: lexer, parser, AST, interpreter, linter
  lsp/             # NyxScript Language Server (pygls)
  plugins/         # every feature area — network, dns, tls, http, audit, watch, script, tui, ...
editors/
  vscode-nyxscript/  # the VS Code extension (syntax highlighting + LSP client)
tests/
  core/
  plugins/
docs/
scripts/
```

## The Core is small on purpose

`nyxor/core` provides exactly these things, and nothing domain-specific:

1. **CLI** (`core/cli.py`) — parses global options (`--verbose`, `--json`,
   `--yaml`, `--output`, `--profile`) and hands control to plugins.
2. **Configuration** (`core/config.py`) — TOML-based, layered override
   hierarchy (see the README).
3. **Plugin loader** (`core/plugins.py`) — discovers plugins via the
   `nyxor.plugins` Python entry-point group. No central registry file.
4. **Event system** (`core/events.py`) — an in-process pub/sub bus so
   plugins and future consumers (dashboard, telemetry) can react to scan
   lifecycle events without coupling to each other.
5. **Logging** (`core/logging.py`) — `structlog`-based structured logging,
   rendered as either a Rich console or JSON.
6. **Shared interfaces** (`core/interfaces.py`, `core/models.py`) — the
   `Plugin` protocol and the `Finding` / `Asset` / `ModuleResult` data
   models every module returns.
7. **Reporting framework** (`core/reporting/`) — renders a `ReportDocument`
   (a collection of `ModuleResult`s) to JSON, Markdown, or HTML. Adding a
   new format means implementing `ReportWriter`, nothing else changes.
8. **Scoring** (`core/scoring.py`) — turns a list of findings into a 0–100
   score, a letter grade, and (optionally) an SVG badge. Used by `audit`
   and `watch`; nothing about it is specific to either.

**No feature should require modifying the Core.** If you find yourself
editing `core/` to add a capability, it likely belongs in a new or existing
plugin instead. NyxScript is the proof of this: an entire language —
lexer, parser, interpreter, linter — lives in `core/scripting/` as a
self-contained unit the Core doesn't know exists.

## Data flow

```
CLI parses --profile/--json/... -> NyxorContext
                                      |
                                      v
                          plugin command (e.g. nyx dns lookup)
                                      |
                                      v
                       module logic returns a ModuleResult
                    (Finding[] + Asset[] + raw_data + errors)
                                      |
                                      v
                  core/output.emit_results() renders per --json/--yaml/--output
                                      |
                        (optional) core/reporting writers -> file
```

Every module returns `ModuleResult` objects — never ad-hoc dicts printed
directly — so the same rendering path (`core/output.py`) and the same
report writers work identically for every plugin.

## Plugin registration vs. runtime context

Plugins attach their Typer commands to the root app once, at import time,
via `Plugin.register(app, bootstrap_context)`. At that point global CLI
options (`--profile`, `--json`, ...) haven't been parsed yet, so the
`bootstrap_context` passed to `register()` only carries default
configuration — use it for wiring, not for reading config values.

Each command function should instead accept `ctx: typer.Context` and read
`ctx.obj`, which is the fully resolved `NyxorContext` populated by the root
`main_callback` after argv is parsed. See any existing plugin's
`plugin.py` for the pattern.

## One scan, three front-ends

Every domain plugin (`network`, `dns`, `tls`, `http`, `audit`) splits its
logic into an `async def run_*(...) -> ModuleResult` function and a thin
Typer command that calls it. Everything downstream reuses those same
coroutines instead of talking to the network again:

- **CLI**: `nyx dns lookup example.com` calls `run_lookup(...)` directly.
- **TUI**: `plugins/tui/app.py`'s Scan tab imports the identical `run_*`
  functions and calls them from a Textual worker.
- **NyxScript**: `core/scripting/stdlib.py`'s `MODULE_RUNNERS` maps
  `run audit example.com` in a `.nyx` script to `run_audit(...)` — the
  exact function the CLI and TUI use.
- **`nyx watch`**: reruns `run_audit(...)` on an interval and diffs the
  resulting findings against the previous run.

Four surfaces, one implementation. This is why `nyx dns lookup
example.com`, running "DNS — lookup" from `nyx tui`, and `run dns
example.com` from a NyxScript file produce *identical* findings — they're
the same code path, rendered four different ways.

When adding a new module, follow this split from the start: keep the async
logic free of Typer/Textual/NyxScript imports, and let each front-end
format its own output.

## NyxScript: a language living inside a Core it doesn't touch

`core/scripting/` is a complete, independent pipeline —
`lexer.py` → `parser.py` (builds the `ast_nodes.py` tree) → either
`linter.py` (pure static analysis, zero side effects) or `interpreter.py`
(executes it for real). It depends on `core/config.py` and the plugin
`run_*` functions; nothing else in the Core depends on it.

Three consumers sit on top of that pipeline without touching its internals:

- `plugins/script/plugin.py` — the `nyx script run|lint|new` commands.
- `plugins/tui/editor.py` — a `TextArea` subclass that reuses the lexer for
  syntax highlighting (no tree-sitter grammar needed) and the same
  prefix-matching logic for ghost-text/popup completion.
- `lsp/server.py` — a `pygls`-based Language Server exposing the linter as
  `textDocument/publishDiagnostics` and the keyword/module/variable list as
  `textDocument/completion`, so any LSP-capable editor gets the same
  checks the CLI does.

## Cross-platform notes

- Host discovery shells out to the system `ping` binary (parsed via return
  code, not raw ICMP) since raw sockets require elevated privileges on
  every OS.
- Service enumeration uses `asyncio.open_connection` (a full TCP connect),
  never a SYN scan. Banner grabbing is equally passive: it reads whatever
  bytes a service sends after connect, never sends a probe.
- TLS inspection uses the stdlib `ssl` module so it honors the platform
  trust store.

## Future expansion points

The interfaces are deliberately narrow so these can be added without
Core changes: a REST API and web dashboard consuming the same
`ModuleResult`/`ReportDocument` models, a database-backed `InventoryStore`
implementation, remote/distributed scanning agents publishing over the
same event names, and scheduling.
