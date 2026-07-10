# Changelog

All notable changes to NYXOR are documented here.

## 0.3.5 — Recon, host hygiene, MCP server, and a Claude Skill

### New plugins
- `nyx recon` — passive subdomain discovery via certificate transparency
  logs (crt.sh), with optional DNS-based live/historical distinction.
  100% passive: reads a public third-party log, never touches the target.
- `nyx hostcheck` — passive local host hygiene checks: processes
  masquerading as well-known Windows system binaries, autorun entries
  pointing at temp/downloads-style paths, and an opt-in VirusTotal
  hash-reputation lookup if you supply your own free API key. Not an
  antivirus — no signatures, no real-time protection — and `--kill` only
  ever acts on a finding you explicitly confirm, one process at a time.
- `nyx matrix` — a cosmetic terminal screensaver. Explicitly not a
  security feature.

### MCP server and Claude Skill
- `nyx mcp` starts NYXOR as an MCP server over stdio, exposing `audit`,
  `dns_lookup`, `tls_inspect`, `http_inspect`, `recon`, `hostcheck`,
  `lint_nyxscript`, and `run_nyxscript` as tools — all wrapping the exact
  same `run_*()` coroutines the CLI/TUI/REST API use. Deliberately
  narrower than the CLI: no `hostcheck --kill` and no `--unsafe`
  NyxScript execution are reachable through it, since an MCP tool can be
  invoked autonomously with no human confirming each call.
- A Claude Skill for NyxScript (`.claude/skills/nyxscript/`) teaches
  Claude the language so it can write, lint, and run `.nyx` scripts
  correctly on the first try.

### Fixes
- `nyx audit "https://example.com/"` no longer crashes — target parsing
  now uses `urlsplit()` for anything containing `://`, instead of a naive
  `rpartition(":")` that read the scheme as the hostname.
- Audit's DNS lookup now strips scheme/port from a full-URL target
  before resolving, instead of silently querying the literal URL string.
- `nyx hostcheck` no longer flags the legitimate `C:\Windows\explorer.exe`
  as a HIGH-severity masquerading process.

## 0.3.0 — NyxScript v3, editor tooling, and a live website

### NyxScript v3
- User-defined functions (`func`/`return`), with real recursion (200-frame
  cap) and a call-stack-based local scope.
- `import "lib.nyx" as alias` — load another script's top-level functions
  and constants as a namespaced module. Library functions resolve sibling
  calls against their own *home* scope regardless of who imports them.
  Circular imports are detected; import depth is capped.
- `while`/`break`/`continue` (1,000,000-iteration safety cap on `while`).
- List indexing (`list[i]`) and a real `.attr` postfix operator, so
  `result[0].findings[0].severity` works on actual scan-result objects.
- 19 pure builtin functions (`len`, `range`, `upper`, `join`, `sorted`, ...)
  and an interactive `ui.*` module (`confirm`/`input`/`select`/`table`/
  `banner`/`status`) built on Rich — the same implementation works from
  the CLI (blocks normally) and the TUI (hands the terminal back via
  `App.suspend()` for the prompt, then restores the dashboard).
- Docstrings: a bare string as a function's first statement, a no-op at
  runtime, surfaced by the LSP.
- Fixed a linter false-positive where a function referencing an import
  alias or module-level variable from its enclosing scope was flagged as
  undefined, despite running fine.
- Full language reference: `docs/nyxscript.md`.

### Editor tooling
- **TUI**: real auto-indent (indent after `:`, `end`/`else` snap back to
  the enclosing level), line numbers, smart backspace (deletes a full
  indent level), a less trigger-happy completion popup, and a visual
  file browser for opening scripts.
- **LSP / VS Code**: hover shows a function's real signature and
  docstring — including through an import alias, resolved cross-file —
  go-to-definition jumps to the `func` line, and `import "` completes
  with `.nyx` files in the workspace. Syntax highlighting updated for
  the full v3 grammar.

### Website
- Deployed for real: `https://ivnovomi.github.io/nyxor/` now serves the
  actual marketing site instead of GitHub Pages' default Jekyll theme.
- A custom hand-drawn brand mark, an editorial two-column feature index,
  and a warm-paper palette with a single accent.

### Fixes
- `cloud-demo.yml` and `action.yml` had a literal `${{ }}` inside a
  `run:` comment — GitHub Actions tries to parse that as an expression
  even inside a comment, so an empty one failed the whole workflow file
  at zero jobs scheduled, silently, since the file was first added.

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
