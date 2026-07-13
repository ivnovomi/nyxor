# FAQ / Troubleshooting

## Start here: `nyx doctor`

```
$ nyx doctor
─────────────────────── system.doctor ───────────────────────
│ info │ Python version      │ Running Python 3.13.x (requires >= 3.13). │
│ info │ Platform            │ Windows / Linux / macOS                  │
│ info │ uv package manager  │ Found at ...                              │
│ info │ Dependency: typer   │ Available.                                │
│ ...                                                                    │
│ info │ Registered plugins  │ N plugin(s) registered ...                │
```

Every check is `info`-severity when healthy; a missing dependency or
wrong Python version shows up as a higher-severity finding here first,
before you hit a confusing error somewhere else. This is also the
**Overview** tab's live diagnostics in `nyx tui`.

## "Registered plugins: N" is lower than I expected

`nyx plugin list` shows exactly which ones loaded and why any didn't —
a plugin whose optional dependency isn't installed (e.g. `serve`
without `--extra api`, `lsp` without `--extra lsp`) is expected to be
missing unless you installed that extra. See
[Installation § Optional extras](Installation#optional-extras).

## Local AI setup

Every AI feature (`nyx analyze`, `nyx ask`, `--dumber`,
`--fix-suggestions`, `--narrate`) talks to a local
[Ollama](https://ollama.com) server — no API key, no per-token cost,
nothing leaves your machine unless you explicitly point `--host` at
something else.

```bash
# 1. install Ollama: https://ollama.com/download
# 2. pull a model once
ollama pull llama3.2
# 3. use any AI-touched command normally
nyx ask "which of my domains got worse this month?"
```

**None of these need AI to work.** Every one degrades to a
deterministic, templated fallback if no model answers — a missing or
unreachable Ollama server is never a hard failure, just a plainer
output. If you expected the model's version and got the fallback
instead, check `nyx doctor` and confirm `ollama serve` is actually
running (`ollama list` should show your pulled model).

Override the server/model per-command or in config:

```bash
nyx analyze example.com --host http://localhost:11434 --model llama3.2
```

```toml
# nyxor.toml or the user config
[ai]
ollama_host = "http://localhost:11434"
model = "llama3.2"
```

## Configuration

```
$ nyx config path
User config:    <platform config dir>/nyxor/config.toml
Project config: ./nyxor.toml (if present in the current directory)
```

Merge order, lowest to highest precedence:

1. Packaged defaults
2. User config (`nyx config init` to create it)
3. Project config — `./nyxor.toml` in the current working directory
4. The active `--profile`'s `[profiles.<name>]` overrides
5. `NYXOR_*` environment variables (`__` for nesting, e.g.
   `NYXOR_GENERAL__LOG_LEVEL=DEBUG`)
6. Explicit CLI flags

```bash
nyx config init            # write a starter user config
nyx config init --project  # write ./nyxor.toml instead
nyx config show            # print the fully resolved, merged config
```

## Where does NYXOR store the inventory / trend history / saved token?

Same platform-appropriate directory `nyx config path` reports for the
user config, alongside it — deleting that whole directory resets
everything (inventory, trend history, saved API token) to a clean
slate. There's no separate "data" location to hunt down.

## `nyx serve` / REST API questions

See the dedicated [REST API](REST-API) page — covers the SSRF guard,
rate limits, and the OAuth2 device-flow login for `/inventory`.

## MCP server won't connect

```bash
uv sync --extra mcp   # the mcp extra must be installed
nyx mcp                # runs over stdio — point your MCP client's
                        # config at this command, don't run it by hand
                        # and expect terminal output
```

Most MCP clients (Claude Desktop, Claude Code) expect a command to
launch, not a running server to connect to — configure the client with
the `nyx mcp` command itself (with its working directory / environment
set to wherever `nyx` is on PATH), not a host:port.

## Editor (LSP) not showing diagnostics/completion

```bash
uv sync --extra lsp   # the lsp extra must be installed
```

- **VS Code**: confirm the extension from
  [`editors/vscode-nyxscript`](https://github.com/ivnovomi/nyxor/tree/main/editors/vscode-nyxscript)
  is installed and the file is recognized as NyxScript (bottom-right
  language indicator).
- **Neovim**: confirm the filetype association and `vim.lsp.start()`
  snippet from [Installation § Editor support](Installation#editor-support)
  are in your config, and that `nyx` is on `$PATH` from the same
  terminal Neovim was launched in.
- **Autocomplete for an imported library not showing its functions**:
  make sure the library file actually exists at the resolved path —
  imports resolve relative to the **current working directory**, not
  the open file's own directory (matching how the interpreter itself
  resolves `import`). Opening a file from a different directory than
  where you'd `cd` before running `nyx script run` is the most common
  cause of "it works from the CLI but not the editor."

## `nyx script run` refuses to run my script

Lint errors block execution by default. `nyx script lint yourfile.nyx`
to see exactly what's wrong (undefined variable, unknown `run` module,
empty control-flow body) — no network access needed to check. Use
`--no-lint` only if you're confident the lint failure is a false
positive.

## A NyxScript regex pattern isn't matching what I expect

Almost always the `{{`/`}}` interpolation gotcha — see
[NyxScript Standard Library Reference § the regex gotcha](NyxScript-Standard-Library-Reference#the-️-gotcha).
Any `{n}` or `{n,m}` quantifier needs doubled braces in a NyxScript
string literal.

## `--unsafe` / `python:` blocks aren't running

`--unsafe` is required on the specific command (`nyx script run
file.nyx --unsafe`, `nyx script repl --unsafe`, the Unsafe switch in
`nyx tui`'s Script tab) — it isn't a global config setting, and it's
never available at all through `nyx mcp`. See
[Security § --unsafe gating](Security#unsafe-gating).

## Where do I report a bug or request a feature?

[GitHub Issues](https://github.com/ivnovomi/nyxor/issues). For a
security-relevant finding, see
[Security § Reporting a vulnerability](Security#reporting-a-vulnerability).
