# Architecture

A CLI, a full-screen TUI, a REST API, an MCP server, a GitHub Action, and
NyxScript's own `run` statement — six ways to trigger a scan, and every
single one of them calls the *same* async function to do the real work.
Nothing is reimplemented twice. That single decision is what makes the
rest of this page short: once you understand the Core/plugin split and
the "one scan, N front-ends" pattern below, you've understood most of
how NYXOR is put together.

## Layout

```
src/nyxor/
  core/            # CLI, config, plugin loader, events, logging, interfaces, reporting, scoring
    reporting/     # ReportDocument + JSON/Markdown/HTML/SARIF writers
    scripting/     # NyxScript: lexer, parser, AST, interpreter, linter, builtins, stdlib registry
  lsp/             # NyxScript Language Server (pygls) + pure analysis helpers
  api/             # the REST API (FastAPI) — a front-end over run_*
  plugins/         # every feature area — network, dns, tls, http, audit, watch, script, tui, serve, ...
editors/
  vscode-nyxscript/  # the VS Code extension (syntax highlighting + LSP client)
lib/               # the NyxScript standard library — written in NyxScript itself
tests/
docs/
```

## The Core is small on purpose

`nyxor/core` provides exactly these things, and nothing domain-specific:

1. **CLI** (`core/cli.py`) — parses global options (`--verbose`, `--json`,
   `--yaml`, `--output`, `--profile`) and hands control to plugins.
2. **Configuration** (`core/config.py`) — TOML-based, layered override
   hierarchy — see [FAQ § Configuration](FAQ-Troubleshooting#configuration).
3. **Plugin loader** (`core/plugins.py`) — discovers plugins via the
   `nyxor.plugins` Python entry-point group. No central registry file.
4. **Logging** (`core/logging.py`) — `structlog`-based, Rich console or
   JSON.
5. **Shared interfaces** (`core/interfaces.py`, `core/models.py`) — the
   `Plugin` protocol and the `Finding` / `Asset` / `ModuleResult` data
   models every module returns.
7. **Reporting framework** (`core/reporting/`) — renders a
   `ReportDocument` to JSON, Markdown, HTML, or SARIF. Adding a format
   means implementing `ReportWriter`, nothing else changes.
8. **Scoring** (`core/scoring.py`) — turns a list of findings into a
   0–100 score, a letter grade, and an SVG/terminal badge. Used by
   `audit` and `watch`; nothing about it is specific to either.

**No feature should require modifying the Core.** If you find yourself
editing `core/` to add a capability, it likely belongs in a plugin
instead — see [Plugin Development](Plugin-Development). NyxScript is
the proof of this: an entire language — lexer, parser, interpreter,
linter — lives in `core/scripting/` as a self-contained unit the Core
doesn't know exists.

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
directly — so the same rendering path and the same report writers work
identically for every plugin.

## Plugin registration vs. runtime context

Plugins attach their Typer commands to the root app once, at import
time, via `Plugin.register(app, bootstrap_context)`. At that point
global CLI options (`--profile`, `--json`, ...) haven't been parsed yet,
so the `bootstrap_context` passed to `register()` only carries default
configuration — use it for wiring, not for reading config values.

Each command function should instead accept `ctx: typer.Context` and
read `ctx.obj`, which is the fully resolved `NyxorContext` populated by
the root `main_callback` after argv is parsed.

## One scan, six front-ends

Every domain plugin (`network`, `dns`, `tls`, `http`, `audit`) splits its
logic into an `async def run_*(...) -> ModuleResult` function and a thin
Typer command that calls it. Everything downstream reuses those same
coroutines instead of talking to the network again:

- **CLI**: `nyx dns lookup example.com` calls `run_lookup(...)` directly.
- **TUI**: the Scan tab imports the identical `run_*` functions and
  calls them from a Textual worker.
- **NyxScript**: `core/scripting/stdlib.py`'s `MODULE_RUNNERS` maps `run
  audit example.com` in a `.nyx` script to `run_audit(...)` — the exact
  function the CLI and TUI use.
- **REST API**: `api/app.py`'s `GET /dns/{domain}` handler is a
  two-line wrapper around `run_lookup(...)`, returning the
  `ModuleResult` Pydantic model directly.
- **MCP server**: `nyx mcp` exposes `audit`/`dns_lookup`/`tls_inspect`/
  `http_inspect`/`recon`/`hostcheck` as MCP tools, each a thin wrapper
  over the same coroutine — deliberately narrower than the CLI (no
  `hostcheck --kill`, no `--unsafe` NyxScript), since an MCP tool can be
  invoked autonomously with no human confirming each call.
- **GitHub Action**: `action.yml` runs `nyx audit` via `uv tool run`
  inside the calling workflow — same binary, same code path, just
  triggered from CI instead of a terminal.
- **`nyx watch`**: reruns `run_audit(...)` on an interval and diffs the
  resulting findings against the previous run.

One implementation, many surfaces. This is why `nyx dns lookup
example.com`, running "DNS — lookup" from `nyx tui`, `run dns
example.com` from a NyxScript file, `curl .../dns/example.com`, and an
MCP tool call all produce *identical* findings — they're the same code
path, rendered differently at the very last step.

When adding a new module, follow this split from the start: keep the
async logic free of Typer/Textual/NyxScript imports, and let each
front-end format its own output.

## NyxScript: a language living inside a Core it doesn't touch

`core/scripting/` is a complete, independent pipeline — `lexer.py` →
`parser.py` (builds the `ast_nodes.py` tree) → either `linter.py` (pure
static analysis, zero side effects) or `interpreter.py` (executes it for
real). It depends on `core/config.py` and the plugin `run_*` functions;
nothing else in the Core depends on it.

Three consumers sit on top of that pipeline without touching its
internals:

- `plugins/script/plugin.py` — the `nyx script run|lint|new|repl`
  commands.
- `plugins/tui/editor.py` — a `TextArea` subclass that reuses the lexer
  for syntax highlighting (no tree-sitter grammar needed) and resolves
  a script's own `import` statements dynamically for autocomplete.
- `lsp/server.py` — a `pygls`-based Language Server exposing the linter
  as `textDocument/publishDiagnostics`, hover/go-to-definition that
  resolves into imported libraries, and completion that follows
  `alias.` into an imported module's actual functions.

`lib/*.nyx` — the standard library — is written in NyxScript itself, not
Python; see [NyxScript Standard Library Reference](NyxScript-Standard-Library-Reference).

## Cross-platform notes

- Host discovery shells out to the system `ping` binary (parsed via
  return code, not raw ICMP) since raw sockets require elevated
  privileges on every OS.
- Service enumeration uses `asyncio.open_connection` (a full TCP
  connect), never a SYN scan. Banner grabbing is equally passive: it
  reads whatever bytes a service sends after connect, never sends a
  probe.
- TLS inspection uses the stdlib `ssl` module so it honors the platform
  trust store.
- NyxScript's regex timeout uses a subprocess (`multiprocessing`,
  `spawn` context on every platform) rather than a thread — see
  [Security § The regex timeout design](Security#the-regex-timeout-design)
  for why, and why that choice is itself cross-platform-sensitive
  (Windows only supports `spawn`, not `fork`).

## Future expansion points

The interfaces are deliberately narrow so these can be added without
Core changes: a web dashboard consuming the REST API that already
exists, a database-backed `InventoryStore` implementation,
remote/distributed scanning agents publishing over the same event
names, broader API authentication, and scheduling.
