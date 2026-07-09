# Architecture

## Layout

```
src/nyxor/
  core/            # CLI, config, plugin loader, events, logging, interfaces, reporting
    reporting/     # ReportDocument + JSON/Markdown/HTML writers
  plugins/         # every feature area — network, dns, tls, http, inventory, report, system, ...
tests/
  core/
  plugins/
docs/
scripts/
```

## The Core is small on purpose

`nyxor/core` provides exactly seven things:

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

**No feature should require modifying the Core.** If you find yourself
editing `core/` to add a capability, it likely belongs in a new or existing
plugin instead.

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

## One scan, two front-ends

Every domain plugin (`network`, `dns`, `tls`, `http`) splits its logic into
an `async def run_*(...) -> ModuleResult` function and a thin Typer command
that calls it. The `tui` plugin (`plugins/tui/app.py`) imports those same
`run_*` coroutines directly — it never reimplements a scan. This is why
`nyx dns lookup example.com` and running "DNS — lookup" from `nyx tui`
produce identical findings: they're the same code path, just two renderers
(`core/output.py` for the CLI, Textual widgets for the dashboard).

When adding a new module, follow this split from the start: keep the async
logic free of Typer/Textual imports, and let each front-end format its own
output.

## Cross-platform notes

- Host discovery shells out to the system `ping` binary (parsed via return
  code, not raw ICMP) since raw sockets require elevated privileges on
  every OS.
- Service enumeration uses `asyncio.open_connection` (a full TCP connect),
  never a SYN scan.
- TLS inspection uses the stdlib `ssl` module so it honors the platform
  trust store.

## Future expansion points

The interfaces are deliberately narrow so these can be added without
Core changes: a REST API and web dashboard consuming the same
`ModuleResult`/`ReportDocument` models, a database-backed `InventoryStore`
implementation, remote/distributed scanning agents publishing over the
same event names, and scheduling.
