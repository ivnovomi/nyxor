# Glossary

Core terms used across the CLI, NyxScript, the REST API, and this wiki.

**Front-end** — one of the ways to trigger a NYXOR scan: the CLI, the
TUI dashboard, the REST API, NyxScript's `run` statement, the MCP
server, or the GitHub Action. All six call the same underlying
coroutine — see [Architecture § One scan, six front-ends](Architecture#one-scan-six-front-ends).

**Module** — a self-contained scan area (DNS, TLS, HTTP, network
discovery/scan, recon, audit). Each exposes an `async def run_*(...)`
coroutine that every front-end calls identically.

**`ModuleResult`** — the structured object every module returns:
`.module` (name), `.target`, `.findings` (list of `Finding`), `.assets`
(list of `Asset`), `.raw_data`, `.errors`. `nyx audit` returns a list of
these (one per sub-module: DNS, TLS, HTTP); single-purpose commands like
`nyx dns lookup` return one directly.

**`Finding`** — one observation from a scan: `.title`, `.severity`,
`.description`, `.target`, plus optional `.evidence`/`.tags`. Findings
are informational observations, not exploit outcomes — NYXOR never
attempts to exploit anything it finds.

**`Severity`** — one of `critical`, `high`, `medium`, `low`, `info`, in
that order from worst to best. Used by `--fail-on` (CI gates), the
scoring system, and SARIF's severity mapping.

**`Asset`** — a discovered piece of infrastructure (host, service,
domain, ...): `.kind`, `.identifier`, `.attributes` (a dict),
`.discovered_at`, `.source_module`. Recorded to the local inventory by
modules like `network.discover`/`network.scan` unless `--no-inventory`
is passed.

**Grade / score** — `nyx audit`'s 0–100 point score (SSL-Labs-style:
start at 100, subtract per finding by severity, floor at 0) mapped to a
letter grade (`A+` down to `F`). Powers the terminal pill badge, the SVG
badge, and `--fail-on`.

**Inventory** — the local, persistent store of discovered `Asset`s
(`nyx inventory list`/`export`/`clear`). Same platform-appropriate
directory as the config file — see
[FAQ § Where does NYXOR store...](FAQ-Troubleshooting#where-does-nyxor-store-the-inventory--trend-history--saved-token).

**Trend** — recorded score history for a domain over time
(`nyx trends show`/`clear`), what `nyx watch` diffs against to decide
whether anything actually changed.

**Plugin** — the unit of extension: a Python object satisfying the
`Plugin` protocol, discovered via the `nyxor.plugins` entry-point group,
no central registry. See [Plugin Development](Plugin-Development).
Every built-in command — including `audit`, `tui`, `serve` — is a
plugin; there's no privileged "core" command type.

**NyxScript** — NYXOR's own automation language: lexer, parser, AST,
tree-walking interpreter, static linter, all living inside
`core/scripting/`, no `eval`. See
[NyxScript Language Guide](NyxScript-Language-Guide).

**`--unsafe`** — the flag/switch that enables NyxScript's `python:` and
`pip` statements, which step outside the language's normal safety model
entirely (real Python execution, real package installs). Off by
default, never available through the MCP server. See
[Security § --unsafe gating](Security#unsafe-gating).

**`lib/*.nyx`** — the NyxScript standard library, written in NyxScript
itself (not Python), imported like any other script:
`import "lib/x.nyx" as alias`. See
[NyxScript Standard Library Reference](NyxScript-Standard-Library-Reference).

**Passive check** — the only kind of check NYXOR performs: TCP-connect,
DNS lookups, TLS handshakes, HTTP requests, reading public
certificate-transparency logs. No exploitation, no packet crafting, no
raw sockets. "Passive" describes the *technique*, not permission —
authorization to check a target is still required.

**SARIF** — Static Analysis Results Interchange Format, a JSON standard
GitHub's Code Scanning (Security tab) consumes natively. One of the
report formats `--output`/`save`/`nyx report convert` can produce.

**SSRF guard** — the REST API's check that refuses to target private/
loopback/link-local/reserved addresses, including on HTTP redirect hops,
so an internet-facing `nyx serve` can't be turned into an internal
network probe. See [REST API § The SSRF guard](REST-API#the-ssrf-guard).

**Composite action** — the GitHub Actions mechanism `action.yml` uses
(`runs: using: composite`) — a sequence of steps bundled into one
reusable action. Its quirk (a failed internal step loses the action's
declared outputs) is why `fail-on` works the way it does — see
[GitHub Action § Why fail-on doesn't fail the action itself](GitHub-Action#why-fail-on-doesnt-fail-the-action-itself).

**Ollama** — the local model server every AI-touched command
(`analyze`/`ask`/`--dumber`/`--fix-suggestions`/`--narrate`) talks to.
Runs entirely on your own machine; every feature degrades to a
deterministic fallback if it isn't running. See
[FAQ § Local AI setup](FAQ-Troubleshooting#local-ai-setup).
