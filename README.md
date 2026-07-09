# NYXOR

[![CI](https://github.com/ivnovomi/nyxor/actions/workflows/ci.yml/badge.svg)](https://github.com/ivnovomi/nyxor/actions/workflows/ci.yml)

NYXOR is a modular, cross-platform security **assessment and infrastructure
auditing** toolkit. It is not a hacking framework — it discovers, inspects,
and reports on infrastructure (hosts, DNS, TLS, HTTP) using only safe,
authorized-use techniques: TCP-connect checks, standard DNS lookups, TLS
handshakes, and HTTP requests. No exploitation, no packet crafting, no raw
sockets.

```
nyx doctor              # environment diagnostics
nyx tui                 # interactive dashboard (overview, inventory, live scans, script editor, plugin browser)
nyx audit <domain>      # combined DNS + TLS + HTTP assessment, with a letter grade
nyx watch <domain>      # keep auditing on an interval, report only what changes
nyx network discover    # host discovery (ping / CIDR sweep)
nyx network scan        # TCP service enumeration + passive banner grabbing
nyx dns lookup          # DNS records, DNSSEC, mail posture
nyx tls inspect         # certificate + protocol/cipher inspection
nyx http inspect        # headers, redirects, cookies, security headers
nyx inventory list      # discovered assets
nyx script run/lint/new # NyxScript automation (see below)
nyx report convert      # JSON -> Markdown/HTML
nyx plugin list         # installed plugins
nyx config show         # effective configuration
```

Run `nyx` with no arguments for the banner + command list.

## Security grade & badges

`nyx audit` scores every run on a 0–100 scale (SSL-Labs-style: findings
subtract points by severity) and maps it to a letter grade, shown right in
the summary table. Want it in a README or status page?

```bash
nyx audit example.com --badge badge.svg
```

writes a shields.io-style flat SVG badge (`nyxor: example.com | A`) you can
embed anywhere. `nyx watch` uses the same grade to flag regressions:

```bash
nyx watch example.com --interval 300
```

reruns the audit every 5 minutes and stays quiet — a heartbeat line —
until something actually changes: a new finding, a resolved one, or a
grade transition, each timestamped and color-coded.

## The dashboard

`nyx tui` launches a full-screen [Textual](https://textual.textualize.io/)
dashboard on top of the exact same plugin logic the CLI uses — nothing is
reimplemented, every tab just calls the same `run_*` coroutines as the CLI:

- **Overview** — live environment diagnostics (the same checks as `nyx
  doctor`) plus at-a-glance stat cards (plugins loaded, findings, inventory
  size).
- **Inventory** — every discovered asset in a sortable table, with one-click
  refresh, HTML export, and clear.
- **Scan** — pick a module (full audit, network discover/scan, DNS lookup,
  TLS inspect, HTTP inspect), enter a target, and watch findings stream in,
  color-coded by severity — new assets land in the inventory automatically.
- **Script** — a syntax-highlighted editor for [NyxScript](#nyxscript)
  files: keywords, module names, strings, numbers, and comments are
  colored as you type. A floating completion box pops up under the cursor
  with matching keywords/modules/variables as you type (click one, or
  press → to accept the top match as ghost text). Open, edit, save, lint,
  and run `.nyx` scripts without leaving the dashboard, with a live output
  log. Running a script with lint errors is refused until you fix them.
  An **Unsafe** switch (off by default) is required before `python:`
  blocks or `pip` statements are allowed to actually run.
- **Plugins** — browse every installed plugin, view and lightly edit its
  `plugin.py` source in place, or scaffold a brand-new plugin skeleton
  under `./nyxor_plugins/<name>/` from a name you type in.
- **About** — version and plugin summary.

Keys: `1`–`5` switch tabs, `r` refreshes, `q` quits.

## NyxScript

NyxScript is a small, intentionally safe language for batch-driving NYXOR
modules — no `eval`, no arbitrary code execution. It has a real lexer,
recursive-descent parser, AST, and a standalone static linter, but the
grammar is deliberately small: variables, `if`/`else`, `foreach` loops,
boolean/arithmetic/comparison expressions, string interpolation, and six
statements that talk to NYXOR (`run`, `save`) or control flow (`set`,
`print`, `assert`, `fail`, `sleep`).

```
set targets = ["example.com", "example.org"]
set min_findings = 1

foreach target in targets:
    print "Auditing {target}..."
    run audit target as result

    set count = 0
    foreach r in result:
        set count = count + 1
    end

    if count >= min_findings:
        save result to "nyxor-output/{target}-audit.html"
    else:
        print "  skipped {target}: nothing came back"
    end
end

print "Done."
```

```bash
nyx script new my-audit.nyx    # scaffold a starter script
nyx script lint my-audit.nyx   # static-check it — no network access
nyx script run my-audit.nyx    # lints, then executes (--no-lint to skip)
```

The linter catches undefined variables (including inside `"{...}"`
interpolation, across `if`/`foreach` branches), unknown `run` modules (with
a "did you mean" suggestion), and empty control-flow bodies — all without
touching the network. `nyx script run` refuses to execute a script with
lint errors unless you pass `--no-lint`.

### Escape hatches: `python:` and `pip`

For the rare case NyxScript's grammar isn't enough, two statements exist
but are **disabled unless you opt in** (`--unsafe` on the CLI, the Unsafe
switch in the TUI):

```
pip "cowsay"
python:
    import cowsay
    cowsay.cow(f"hello from {target}")
end
```

`python:` blocks run as real Python with direct read/write access to the
script's variables; `pip` installs a package into the current environment
(via `uv pip install` when available). Both require `--unsafe` precisely
because they step outside NyxScript's "just makes requests to the targets
you name" safety model — treat a script using them like you would any
other executable.

### Editor support

NyxScript has a real [Language Server](src/nyxor/lsp/server.py) (built on
[pygls](https://github.com/openlawlibrary/pygls)) that any LSP-capable
editor can use for live diagnostics, completion, and hover docs:

```bash
uv sync --extra lsp
nyx script lsp   # run by your editor, not by hand — speaks LSP over stdio
```

- **VS Code**: install the extension in
  [editors/vscode-nyxscript](editors/vscode-nyxscript) (syntax highlighting
  + the language server, `python:` blocks highlighted as embedded Python).
- **Neovim** (0.10+, built-in LSP client):
  ```lua
  vim.filetype.add({ extension = { nyx = "nyxscript" } })
  vim.api.nvim_create_autocmd("FileType", {
    pattern = "nyxscript",
    callback = function(args)
      vim.lsp.start({
        name = "nyxscript",
        cmd = { "nyx", "script", "lsp" },
        root_dir = vim.fs.dirname(vim.fs.find({ "nyxor.toml", ".git" }, { upward = true })[1]),
      }, { bufnr = args.buf })
    end,
  })
  ```
- **Anything else** with a generic LSP client: point it at `nyx script lsp`
  over stdio for `.nyx` files.

Available modules for `run`: `audit`, `dns`, `tls`, `http`,
`network.discover`, `network.scan`. See
[core/scripting/](src/nyxor/core/scripting/) — `lexer.py`, `parser.py`,
`ast_nodes.py`, `interpreter.py`, `linter.py` — for the implementation and
full grammar.

## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) for dependency management

## Install (development)

```bash
uv sync --extra dev
uv run nyx --help
```

This installs an editable checkout, so `nyx` / `nyxor` on your `uv run` PATH
reflect local source changes immediately.

## Global options

Every command accepts:

| Flag | Purpose |
|---|---|
| `--verbose` / `-v` | Debug-level structured logging |
| `--json` | Emit machine-readable JSON to stdout |
| `--yaml` | Emit YAML to stdout |
| `--output PATH` / `-o` | Write a report to a file (format inferred from extension: `.json`, `.md`, `.html`) |
| `--profile NAME` / `-p` | Apply a named configuration profile |

## Configuration

NYXOR merges configuration from, lowest to highest precedence:

1. Packaged defaults
2. User config — `~/.config/nyxor/config.toml` (platform-appropriate path)
3. Project config — `./nyxor.toml`
4. The active `--profile`
5. `NYXOR_*` environment variables (`NYXOR_GENERAL__LOG_LEVEL=DEBUG`)
6. Explicit CLI flags

Run `nyx config init` to write a starter file, `nyx config show` to see the
fully resolved configuration, and `nyx config path` to see where NYXOR is
looking.

## Architecture

See [docs/architecture.md](docs/architecture.md) for how the Core, plugin
system, and reporting framework fit together, and
[docs/plugin-development.md](docs/plugin-development.md) to add your own
module without touching the Core.

## Testing

```bash
uv run pytest
uv run ruff check .
uv run mypy src
```

## Contributing

See [docs/contributing.md](docs/contributing.md).
