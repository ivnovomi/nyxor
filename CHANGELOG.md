# Changelog

All notable changes to NYXOR are documented here.

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
