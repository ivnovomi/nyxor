# NYXOR Wiki

NYXOR is a modular, cross-platform **security assessment and infrastructure
auditing** toolkit. Everything it does is a passive, non-destructive
observation — TCP-connect checks, standard DNS lookups, TLS handshakes,
HTTP requests, public certificate-transparency logs. No exploitation, no
packet crafting, no raw sockets, nothing that needs elevated privileges.

One engine, many front-ends: the exact same `async def run_*()` coroutine
backs the CLI, the TUI dashboard, the REST API, NyxScript's `run`
statement, the MCP server, and the GitHub Action. Nothing is ever
reimplemented twice — fix a bug once, it's fixed everywhere. See
[Architecture](Architecture) for how that's wired together.

## Getting started

- **[Installation](Installation)** — `pipx`/`uv`/`pip`, optional extras
  (`api`, `lsp`, `mcp`), development checkout.
- **[Quickstart](Quickstart)** — your first audit, reading the output,
  badges, your first NyxScript, your first TUI session.
- **[CLI Reference](CLI-Reference)** — every `nyx` command and flag,
  grouped the same way `nyx --help` groups them.

## NyxScript — the automation language

- **[NyxScript Language Guide](NyxScript-Language-Guide)** — syntax,
  types, control flow, functions, imports, error handling.
- **[NyxScript Standard Library Reference](NyxScript-Standard-Library-Reference)**
  — every builtin function and every `lib/*.nyx` module, with signatures.

## Other front-ends

- **[REST API](REST-API)** — `nyx serve`: endpoints, the SSRF guard, rate
  limits, the OAuth2 device flow for `/inventory`.
- **[GitHub Action](GitHub-Action)** — run an audit in CI with no Python
  install, `fail-on` gates, SARIF upload to the Security tab.

## Extending NYXOR

- **[Plugin Development](Plugin-Development)** — add a new module without
  touching the Core; the same mechanism every built-in module uses.
- **[Architecture](Architecture)** — how the Core, plugin loader, and
  reporting framework fit together.

## Project

- **[Security](Security)** — the passive-only design, `--unsafe` gating,
  the SSRF/XSS guards in the REST API, the regex timeout design, and how
  this project is built (AI-assisted, transparently).
- **[FAQ / Troubleshooting](FAQ-Troubleshooting)** — common `nyx doctor`
  failures, local-AI setup, config file locations.
- **[Contributing](Contributing)** — how to propose changes, cut a
  release.

---

Not sure where to start? `nyx doctor` (environment diagnostics), then
`nyx audit example.com` (or any domain you're authorized to check).
