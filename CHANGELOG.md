# Changelog

All notable changes to NYXOR are documented here.

## 0.5.0 — Passive fingerprinting, a Rich-markup bugfix sweep, and local AI

### Passive tech-stack / CDN / WAF fingerprinting
- `nyx http inspect` (and therefore `nyx audit`) now passively fingerprints
  the target from data already fetched for the request — response headers,
  cookie names, and page markup (including `<meta name="generator">`).
  Zero extra requests, zero active probing. New findings: "Detected
  technology" and "CDN / WAF".
- New module: `core/explain.py` templates for both, so `--dumber` explains
  them in plain language too.

### Local AI, expanded (`nyx analyze`'s Ollama client, reused everywhere)
- `nyx audit --dumber` now asks the local model (if reachable) for a
  beginner-friendly, finding-by-finding writeup instead of the fixed
  templates — falls back to the templates automatically if no model
  answers.
- `nyx audit --fix-suggestions`: concrete remediation steps for
  medium-or-worse findings, from the local model.
- `nyx watch --narrate`: on a grade change or new/resolved findings, a
  one-line plain-English narration from the local model.
- `nyx ask ["question"]`: chat with the local model about your recorded
  `nyx audit`/`nyx trends` history — single-shot with a question, or an
  interactive REPL with none.
- All of the above are strictly additive and strictly local: same Ollama
  client, your own GPU if Ollama is configured to use one, nothing sent
  anywhere unless `--host` is pointed elsewhere. Every one degrades
  gracefully (templates, a skipped section, or a clear error for `nyx ask`)
  if no local model is running — nothing here can break a command that
  worked fine without AI.

### Bugfix sweep
- **Rich was silently eating literal `[...]` text in almost every table and
  status line** across the CLI — a TCP banner, a DNS TXT record, an HTTP
  header value, a process name, anything containing a literal `[` got
  parsed as a (nonexistent) Rich style tag and dropped. Fixed with
  `rich.markup.escape()` everywhere externally-sourced text reaches a
  `Console.print()`/`Table.add_row()`: the core table renderer, `nyx
  hostcheck`, `nyx recon`, `nyx watch`, `nyx audit --dumber`, and
  NyxScript's `ui.table`/`ui.banner`/`ui.status`.
- **IPv6 targets were badly mangled.** `nyx tls inspect "[::1]:443"` built
  a target string of `[::1]:443:443` (the whole bracket notation, port
  suffix included, treated as one opaque "host"); `nyx audit "[::1]"`
  truncated the DNS hostname down to a single `"["` character. Both
  `_parse_target` (tls) and `_hostname_for_dns` (audit) now parse bracketed
  IPv6 literals correctly and leave bare (unbracketed) IPv6 addresses with
  more than one colon alone instead of misreading part of the address as a
  port.

## 0.4.0 — NyxScript grows up: dicts, error handling, a REPL, and a stdlib

### NyxScript language
- **Dicts**: `{"key": value, ...}` literals, indexing (`d["key"]`), and
  `set CONTAINER[index]... = expr` for in-place mutation of a list or
  dict (chainable — `set d["a"]["b"] = 1` works). New builtins:
  `keys`, `values`, `items`, `get` (with a mandatory default — NyxScript
  still has no `null` to silently fall back to).
- **Error handling**: `try: ... except err: ... end` catches a NyxScript
  runtime error and binds its message to `err` for the `except` block.
  Never catches `break`/`continue`/`return`. The linter understands it:
  a variable the `try` body sets is treated as defined afterward only
  when the `except` branch can't fall through past it.
- **Standard library, written entirely in NyxScript** (`lib/`): `math.nyx`
  (`mod`, `clamp`, `mean`, `median`, `gcd`, `is_prime` — NyxScript has no
  `%` operator, `mod()` is the way), `dict.nyx` (`merge`, `pick`,
  `invert`, `from_pairs`), `validate.nyx` (`is_valid_port`,
  `is_valid_ipv4`, `is_valid_domain`), plus the existing
  `collection`/`strings`/`finding` libs and a fixed, working
  `report.nyx` (it shipped with an empty function body).
- **`nyx script repl`**: an interactive prompt where variables and
  functions persist across lines — multi-line blocks (`if`/`foreach`/
  `while`/`func`/`try`/`python:`) are detected and only run once their
  matching `end` arrives.
- VS Code extension, TUI editor, and the Claude Skill all updated for
  the new grammar (`{`/`}`, `try`/`except`, the new builtins).

### Fixes found while building the above
- **Rich was eating printed lists/dicts.** `print [1, 2, 3]` rendered as
  `[, , ]` in both `nyx script run`/`repl` and the TUI's script log,
  because Rich's markup parser treats a literal `[...]` in output as a
  style tag. Fixed with `markup=False` (CLI/REPL) and `rich.markup.escape`
  (TUI) on script-generated output specifically — our own `[bold]...[/]`
  status lines are untouched.
- A linter false-negative/positive pair around `try`/`except` definite-
  assignment (see above).

### Terminal badges and `--dumber`
- `nyx audit` and `nyx watch` now print a shields.io-style pill badge
  directly in the terminal (`render_terminal_badge` in `core/scoring.py`)
  using Rich truecolor backgrounds — plain color blocks, not Nerd Font
  glyphs, so it doesn't break on terminals without a patched font.
- `nyx audit --dumber`: a plain-language, no-jargon explanation of every
  finding (`core/explain.py`) — purely templated, no LLM call, no extra
  network access. Falls back to a generic severity-flavored line for
  anything it doesn't have a specific explainer for.

## 0.3.6 — Hotfix: audit crashing on redirects

- `nyx audit` crashed on any target that redirects (e.g. bare domain ->
  `www`) with `1 validation error for Finding — evidence: Input should
  be a valid dictionary`. The "Redirect chain" finding was passed the
  raw redirect-chain list where `Finding.evidence` expects a dict; it's
  now wrapped as `{"hops": [...]}`.

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
