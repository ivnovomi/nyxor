# Installation

## Requirements

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/) for dependency management (used by
  every install path below, including the plain `pip`/`pipx` one under
  the hood for development checkouts)
- Optional: [Ollama](https://ollama.com) for local AI features (`nyx
  analyze`/`ask`/`--dumber`/`--fix-suggestions`/`--narrate`) — everything
  else needs nothing beyond the base install.

## As a CLI tool

```bash
pipx install nyxor   # or: uv tool install nyxor / pip install nyxor
nyx --help
```

`pipx` / `uv tool install` are recommended over a bare `pip install` for a
CLI tool — they isolate NYXOR's dependencies from whatever else is on your
system Python.

Optional extras (`--extra mcp` / `--extra lsp` / `--extra api`) aren't
available through `pipx`/`uv tool install` — extras only apply to a
project checkout. For those, or to hack on NYXOR itself, install from
source instead (below).

## From source (development)

```bash
git clone https://github.com/ivnovomi/nyxor.git
cd nyxor
uv sync --extra dev
uv run nyx --help
```

This installs an editable checkout, so `nyx` / `nyxor` on your `uv run`
PATH reflect local source changes immediately — no reinstall needed after
editing a plugin or the interpreter.

### Optional extras

| Extra | Unlocks | Install |
|---|---|---|
| `dev` | Test suite, linters, everything needed to contribute | `uv sync --extra dev` |
| `api` | `nyx serve` (FastAPI + slowapi rate limiting) | `uv sync --extra api` |
| `lsp` | `nyx script lsp` (pygls language server) | `uv sync --extra lsp` |
| `mcp` | `nyx mcp` (MCP server for Claude and other clients) | `uv sync --extra mcp` |

Extras compose — `uv sync --extra dev --extra api --extra mcp` pulls in
everything at once.

## Verifying the install

```bash
nyx doctor
```

Runs environment diagnostics: Python version, whether optional
dependencies for extras you haven't installed are missing (expected,
not an error, unless you meant to use that feature), whether a local
Ollama server is reachable, and where NYXOR's config file lives. This is
also the first tab (**Overview**) of `nyx tui`.

## Editor support (NyxScript)

- **VS Code**: install the extension in
  [`editors/vscode-nyxscript`](https://github.com/ivnovomi/nyxor/tree/main/editors/vscode-nyxscript)
  from source (syntax highlighting, the language server, `python:` blocks
  highlighted as embedded Python, a dedicated file icon for `.nyx`).
- **Neovim** (0.10+, built-in LSP client) — see
  [NyxScript Language Guide § Editor support](NyxScript-Language-Guide#editor-support)
  for the exact `vim.lsp.start()` snippet.
- **Anything else** with a generic LSP client: point it at `nyx script
  lsp` over stdio for `.nyx` files (requires `--extra lsp`).

## Uninstalling

```bash
pipx uninstall nyxor        # if installed via pipx
uv tool uninstall nyxor     # if installed via uv tool install
pip uninstall nyxor         # if installed via pip
```

NYXOR's local state — the inventory database, trend history, saved API
token — lives under the same platform-appropriate config directory `nyx
config path` reports; delete that directory too if you want a completely
clean slate.
