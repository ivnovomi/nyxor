# Changelog

All notable changes to NYXOR are documented here.

## 0.2.0 — REST API, Cloud, and three new plugins

### REST API
- `nyx serve` — a fourth front-end (FastAPI) over the exact same `run_*`
  coroutines the CLI, TUI, and NyxScript use: `/audit/{domain}`,
  `/dns/{domain}`, `/tls/{target}`, `/http`, `/badge/{domain}.svg`
  (live SVG grade badge), `/inventory`.
- SSRF guard on every scan endpoint — resolves and refuses private/loopback/
  link-local/reserved/multicast targets, so an internet-facing instance
  can't be used to probe internal networks or cloud metadata endpoints.
- Rate limiting (slowapi): 60/min default, 20/min on endpoints that trigger
  real network I/O.
- A real OAuth 2.0 Device Authorization Grant (RFC 8628) — `nyx auth login`
  authenticates against any running `nyx serve` (or NYXOR Cloud, later)
  with no password and no embedded client secret. `/inventory` requires
  the bearer token it issues.

### New plugins
- `auth` — `login` (OAuth2 device flow, or `--token` to paste one),
  `approve` (headless device-code approval), `logout`, `whoami`.
- `trends` — records each audit's score to a per-domain history and reports
  real statistics via NumPy: mean, std, least-squares trend slope,
  sparkline, and z-score outlier detection.
- `analyze` — an AI-written findings summary. Prefers a local Ollama model
  (free, nothing leaves the machine); falls back to a deterministic
  rule-based summary when no local model is running.

### NYXOR Cloud
- `action.yml` — a composite GitHub Action that installs NYXOR straight
  from source (`uv tool run --from git+...`) and runs an audit on a
  GitHub-hosted runner. No PyPI publish, no server, no account.
- `cloud-demo.yml` — a scheduled, self-referential demo of the same action.

### Website
- A static marketing site (`website/`) — terminal/CRT aesthetic, a live
  typed `nyx audit` demo, honest Free/Cloud/Scale pricing (Cloud/Scale
  aren't live — the buttons open an email, not a checkout, and the page
  says so).

## 0.1.0 — initial release

### Core
- Plugin-first CLI (Typer) with global `--verbose`/`--json`/`--yaml`/`--output`/`--profile` options.
- Layered TOML configuration (defaults → user → project → profile → env → CLI).
- Structured logging (structlog), an in-process event bus, and an entry-point-based
  plugin loader — no central registry to edit.
- A reporting framework (`ModuleResult` → JSON/Markdown/HTML) shared by every module.

### Modules
- `network` — host discovery (ping/CIDR sweep) and TCP service enumeration with
  passive banner grabbing.
- `dns` — record lookup, DNSSEC detection, mail-related checks (SPF/DMARC/MX).
- `tls` — certificate inspection, expiry, protocol/cipher overview.
- `http` — headers, redirects, cookies, compression, security header inspection.
- `audit` — combined DNS + TLS + HTTP assessment with an SSL-Labs-style letter
  grade and exportable SVG badge.
- `watch` — continuous monitoring that reports only new/resolved findings and
  grade transitions.
- `inventory`, `report`, `plugin`, `config`, `system` (`doctor`), `update`.

### NyxScript
- A small, safe automation language with its own lexer, recursive-descent
  parser, AST, tree-walking interpreter, and standalone static linter
  (undefined variables, unknown modules with "did you mean", empty blocks).
- Opt-in `--unsafe` escape hatches: `python: ... end` blocks and `pip` package
  installs.
- A real Language Server (`nyx script lsp`, built on pygls) with diagnostics,
  completion, and hover — plus a VS Code extension (syntax highlighting,
  embedded-Python highlighting inside `python:` blocks, custom file icon).

### TUI
- A Textual dashboard (`nyx tui`): environment overview, inventory browser,
  live scans across every module, a syntax-highlighted NyxScript editor with
  a floating completion box, and a plugin browser/editor — all built on the
  exact same functions the CLI uses.

### Tooling
- `uv`-managed project, `ruff` + `mypy --strict`, pytest suite, GitHub Actions
  CI (lint, cross-platform tests, VS Code extension compile check).
