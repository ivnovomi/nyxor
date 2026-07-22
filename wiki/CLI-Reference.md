# CLI Reference

Run `nyx` with no arguments for the banner + full command list, or `nyx
--help` / `nyx COMMAND --help` / `nyx COMMAND SUBCOMMAND --help` for the
same information from the tool itself — this page mirrors that output.

## Global options

Accepted before the command name (`nyx --json audit example.com`, not
`nyx audit example.com --json`):

| Flag | Purpose |
|---|---|
| `--verbose` / `-v` | Debug-level structured logging |
| `--json` | Emit machine-readable JSON to stdout |
| `--yaml` | Emit YAML to stdout |
| `--output PATH` / `-o` | Write a report to a file (format inferred from extension: `.json`, `.md`, `.html`, `.sarif`) |
| `--profile NAME` / `-p` | Apply a named configuration profile — see [FAQ § Configuration](FAQ-Troubleshooting#configuration) |
| `--install-completion` | Install shell completion |
| `--show-completion` | Print shell completion script |

## Scanning

### `nyx audit DOMAIN`

Combined DNS + TLS + HTTP assessment — the flagship command.

| Flag | Purpose |
|---|---|
| `--no-inventory` | Don't record discovered assets to the local inventory |
| `--badge PATH` | Write a shields.io-style SVG grade badge |
| `--dumber` | Plain, no-jargon explanation of every finding (local model, template fallback) |
| `--fix-suggestions` | Concrete remediation steps for medium+ findings (local model) |
| `--no-local` | Skip the local model for `--dumber`/`--fix-suggestions` (template/skip instead) |
| `--fail-on [info\|low\|medium\|high\|critical]` | Exit code 1 if any finding meets or exceeds this severity — for CI gates |

### `nyx recon DOMAIN`

Passive subdomain discovery via certificate-transparency logs (crt.sh) —
never touches the target directly.

| Flag | Purpose |
|---|---|
| `--no-resolve` | Skip DNS resolution — just list names seen in certificates |
| `--limit INTEGER` | Maximum subdomains to report (default 500) |

### `nyx dns lookup DOMAIN`

Standard records, DNSSEC status, mail-related records (SPF/DMARC/MX). No
extra flags beyond the globals.

### `nyx tls inspect TARGET`

Certificate inspection, expiry, protocol/cipher overview for
`HOST[:PORT]`. No extra flags.

### `nyx http inspect URL`

Response headers, redirects, cookies, compression, security headers,
passive tech-stack/CDN/WAF fingerprinting.

| Flag | Purpose |
|---|---|
| `--screenshot PATH` | Save a full-page PNG screenshot (requires `--unsafe`) |
| `--unsafe` | Allow `--screenshot` to render the page in a real headless browser |

`--screenshot` needs the `screenshot` extra (`uv sync --extra
screenshot`, then a one-time `uv run playwright install chromium` to
fetch the browser itself — the extra only installs Playwright's Python
bindings). It's gated behind `--unsafe` because, unlike the
rest of this command, rendering a page executes its own JavaScript and
loads whatever it references — not a bounded, passive request like
everything else NYXOR does. When run in a terminal, also prints an
inline preview of the screenshot (Kitty/Sixel graphics protocol if the
terminal supports it, falling back to plain text — no protocol
detection code of our own, and no dependency on what pwsh/Windows
Terminal happens to support).

### `nyx network discover TARGET`

Ping-sweep a host or CIDR range (e.g. `nyx network discover
192.168.1.0/24`) — only ever run against ranges you're authorized to
scan.

| Flag | Purpose |
|---|---|
| `--no-inventory` | Don't record discovered hosts to the local inventory |

### `nyx network scan HOST`

TCP connect-scan a single host, plus passive banner grabbing on open
ports.

| Flag | Purpose |
|---|---|
| `--ports TEXT` | Comma-separated ports; defaults to a common set |
| `--no-inventory` | Don't record discovered services to the local inventory |

## Continuous & History

### `nyx watch DOMAIN`

Reruns `audit` on an interval, reports only what changed.

| Flag | Purpose |
|---|---|
| `--interval FLOAT` | Seconds between checks (default 300.0) |
| `--iterations INTEGER` | Stop after N checks (0 = forever, default) |
| `--narrate` | On a change, ask a local model for a one-line plain-English narration |

### `nyx trends show DOMAIN`

Audits a domain, records the score, reports the trend line.

| Flag | Purpose |
|---|---|
| `--no-record` | Only report existing history — don't run a new audit |
| `--limit INTEGER` | Number of most recent runs to consider (default 30) |

### `nyx trends clear DOMAIN`

Deletes recorded history for a domain. No extra flags.

## AI (local model)

All of these talk to a local [Ollama](https://ollama.com) server and
degrade to a deterministic fallback if none is reachable — see
[FAQ § Local AI setup](FAQ-Troubleshooting#local-ai-setup).

### `nyx analyze DOMAIN`

Audits a domain, produces a short written summary instead of a table.

| Flag | Purpose |
|---|---|
| `--host TEXT` | Local (or Cloud) model server, defaults to config `ai.ollama_host` |
| `--model TEXT` | Model name, defaults to config `ai.model` |
| `--no-local` | Skip the local model, go straight to the rule-based summary |

### `nyx ask [QUESTION]`

Chat with the local model about your recorded `nyx audit`/`nyx trends`
history. Omit `QUESTION` for an interactive prompt.

| Flag | Purpose |
|---|---|
| `--host TEXT` | Local (or Cloud) model server |
| `--model TEXT` | Model name |

## Host Security

### `nyx hostcheck`

Passive local host hygiene: masquerading processes (claiming to be a
well-known system binary but running from the wrong path) and
suspicious autorun entries. Not an antivirus — no signatures, no
real-time protection.

| Flag | Purpose |
|---|---|
| `--vt-api-key TEXT` | Your own free VirusTotal API key for hash-reputation lookups (env: `VT_API_KEY`) |
| `--kill` | Offer to terminate HIGH-severity process findings, one at a time |
| `--yes` | Don't ask for confirmation before killing (use with `--kill`) |

## Automation

### `nyx mcp`

Starts the NYXOR MCP server over stdio for Claude and other MCP
clients. No extra flags — see [Security § MCP is deliberately narrower than the CLI](Security#mcp-is-deliberately-narrower-than-the-cli).

### `nyx script SUBCOMMAND`

See [NyxScript Language Guide](NyxScript-Language-Guide) for the
language itself.

| Subcommand | Purpose | Flags |
|---|---|---|
| `run PATH` | Lint, then execute, a `.nyx` file | `--no-lint` (skip the pre-flight lint check), `--unsafe` (allow `python:`/`pip` to actually run) |
| `lint PATH` | Statically check without running — no network access | — |
| `new PATH` | Scaffold a starter `.nyx` file | `--force` (overwrite existing) |
| `repl` | Interactive prompt, variables/functions persist across lines | `--unsafe` |
| `lsp` | Start the language server over stdio (for editors, not humans) | — |

## Dashboard & Reports

### `nyx tui`

Launches the interactive dashboard. No flags — see the Overview /
Inventory / Scan / Script / Plugins tabs described on the
[Home](Home) page and README.

### `nyx inventory SUBCOMMAND`

| Subcommand | Purpose | Flags |
|---|---|---|
| `list` | List every asset currently in the inventory | — |
| `export` | Export the inventory (combine with global `--output` for JSON/Markdown/HTML) | — |
| `clear` | Delete every asset from the inventory | `--yes`/`-y` (skip confirmation) |

### `nyx report convert INPUT_PATH`

Converts a saved JSON report (from an earlier `--output foo.json` run)
into another format.

| Flag | Purpose |
|---|---|
| `--to TEXT` | Target format: `json`, `markdown`, `html`, or `sarif` (default `html`) |
| `--output PATH` / `-o` | Where to write the converted report (**required**) |

## Setup & Config

### `nyx doctor`

Environment diagnostics and dependency checks. No flags — run this
first if anything seems broken; see [FAQ](FAQ-Troubleshooting).

### `nyx update`

Checks whether a newer version of NYXOR is available. No flags — it never
installs anything, it only reports the latest version and how to install it
via `uv`.

### `nyx auth SUBCOMMAND`

For authenticating against a `nyx serve` instance's OAuth2-protected
`/inventory` endpoint — see [REST API § Authentication](REST-API#authentication).

| Subcommand | Purpose | Flags |
|---|---|---|
| `login` | Log in via OAuth2 device flow (default), or save a token directly. When the server provides a complete verification URL and output is interactive, also prints a QR code (rendered as text — no image protocol needed) that scans straight to the approval page | `--host TEXT` (default `http://127.0.0.1:8842`), `--token TEXT` (skip the flow, save a token you already have) |
| `approve USER_CODE` | Approve a device login headlessly, no browser needed | `--host TEXT` |
| `logout` | Delete the locally-saved API token | — |
| `whoami` | Show whether a token is saved, and where | — |

### `nyx config SUBCOMMAND`

| Subcommand | Purpose | Flags |
|---|---|---|
| `show` | Print the fully resolved, merged configuration | — |
| `path` | Show where NYXOR looks for configuration files | — |
| `init` | Write a default configuration file | `--project` (write `./nyxor.toml` instead of the user config), `--force` (overwrite existing) |

### `nyx plugin SUBCOMMAND`

| Subcommand | Purpose | Flags |
|---|---|---|
| `list` | List every plugin discovered via the `nyxor.plugins` entry-point group | — |
| `info NAME` | Show metadata for a single plugin | — |

## API

### `nyx serve`

Runs the REST API — see [REST API](REST-API) for the full endpoint
list, SSRF guard, and auth model.

| Flag | Purpose |
|---|---|
| `--host TEXT` | Interface to bind to (default `127.0.0.1`) |
| `--port INTEGER` | Port to listen on (default `8842`) |

## Fun

Not security features, kept anyway.

### `nyx flex`

A glitch-reveal RGB wordmark.

| Flag | Purpose |
|---|---|
| `--duration FLOAT` | Seconds to hold the final frame before exiting (default 5.0) |

### `nyx matrix`

A Matrix-rain easter egg.

| Flag | Purpose |
|---|---|
| `--duration FLOAT` | Seconds to run — 0 runs until Ctrl+C (default 6.0) |
| `--rainbow` | Cycle the trail through a moving RGB rainbow instead of green |
