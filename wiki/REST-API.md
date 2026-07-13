# REST API

`nyx serve` runs a small [FastAPI](https://fastapi.tiangolo.com) app
(`src/nyxor/api/app.py`) over the exact same `run_*()` coroutines the
CLI/TUI/NyxScript/MCP server use — no scan logic is reimplemented for
HTTP. It's a fourth front-end, not a separate product.

```bash
uv sync --extra api    # or: pipx install 'nyxor[api]' if published with extras
nyx serve --port 8842  # interactive docs at http://127.0.0.1:8842/docs
```

Every check the API makes is the same passive observation NYXOR always
makes: TCP-connect, DNS, TLS handshake, HTTP request. No exploitation.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check — `{"status": "ok", "version": "..."}` |
| `GET` | `/plugins` | Every discovered plugin's metadata |
| `GET` | `/audit/{domain}` | Full combined DNS+TLS+HTTP audit — list of `ModuleResult` |
| `GET` | `/audit/{domain}/score` | Just the grade/points/finding-count summary |
| `GET` | `/badge/{domain}.svg` | Live-generated SVG grade badge — **re-audits on every request** |
| `GET` | `/dns/{domain}` | DNS lookup only |
| `GET` | `/tls/{target}` | TLS inspection only (`target` = `host[:port]`) |
| `GET` | `/http?url=...` | HTTP inspection only |
| `GET` | `/inventory` | Stored inventory assets — **requires a bearer token**, see [Authentication](#authentication) |
| `POST` | `/oauth/device/code` | Start an OAuth2 device-flow login |
| `GET` | `/oauth/device` | Browser page to approve a device login |
| `POST` | `/oauth/device/approve` | Approve headlessly (what `nyx auth approve` calls) |
| `POST` | `/oauth/token` | Poll for the issued token (what `nyx auth login` polls) |

All scan responses use the same `ModuleResult`/`Finding` Pydantic models
the CLI's `--json` output does — same shape either way.

```bash
curl http://127.0.0.1:8842/audit/example.com/score
# {"domain":"example.com","grade":"A","points":94,"finding_counts":{"info":16,"low":0,"medium":1,"high":0,"critical":0}}
```

```markdown
![security](http://your-host:8842/badge/example.com.svg)
```

## The SSRF guard

Every scan endpoint refuses to target a private/loopback/link-local/
reserved/multicast/unspecified address — otherwise an internet-facing
`nyx serve` instance would be a generic internal-network probe for
anyone who can reach it (`GET /http?url=http://169.254.169.254/...`
reading cloud metadata, `GET /tls/127.0.0.1:6379` probing localhost
services).

The guard (`_ensure_public_target`) resolves the hostname and checks the
resulting IP **before** the initial request, and — for `/http` and
`/audit`, since HTTP responses can redirect — **again on every redirect
hop**, not just the URL you typed. A public redirector that bounces to
`http://169.254.169.254/...` gets caught, not followed. A rejected
redirect surfaces as an error on that module's result rather than a hard
500 — the request still returns `200`, just with `"errors": [...]` set.

```bash
curl http://127.0.0.1:8842/dns/127.0.0.1
# 400: refusing to scan '127.0.0.1': resolves to a non-public address (127.0.0.1)
```

## Rate limiting

Per-client-IP, via [slowapi](https://github.com/laurentS/slowapi):

- Scan endpoints (`/audit`, `/dns`, `/tls`, `/http`, `/badge`): 20/minute
- Everything else: 60/minute default

## Authentication

Only `/inventory` requires auth — every other endpoint (including the
scan endpoints) is open, matching the API's stated purpose: auditing
*other people's* public infrastructure, rate-limited so it can't become
an amplification vector.

`/inventory` uses the OAuth2 Device Authorization Grant (RFC 8628):

```bash
nyx auth login --host http://127.0.0.1:8842
# prints a short user code + a URL

# on another device/terminal, approve it:
nyx auth approve XXXX-XXXX --host http://127.0.0.1:8842

# back on the first terminal, the CLI polls /oauth/token and saves
# the issued bearer token once approved

nyx auth whoami   # confirm it's saved
```

Device codes expire after 10 minutes; polling is rate-limited to once
per ~3 seconds. State is in-memory and per-process — restarting `nyx
serve` clears pending/approved devices, matching every other piece of
local state NYXOR keeps (inventory, trends, saved token).

## Design notes

- **No auth on scan endpoints is intentional**, not an oversight — see
  the docstring on `create_app()` in `src/nyxor/api/app.py`.
- **The badge endpoint re-audits on every request** rather than caching
  — simplicity over performance for what's meant to be an occasionally
  polled status badge, not a high-traffic endpoint.
- Label text passed into the SVG badge (`domain` from the URL path) is
  XML-escaped before being embedded — see
  [Security § XSS in the badge SVG](Security#xss-fixes-this-project-shipped-and-fixed).

## Related

- [Security](Security) — the SSRF guard and two XSS fixes in detail,
  with the exact exploit each closed.
- [GitHub Action](GitHub-Action) — a different HTTP-adjacent front-end,
  for CI rather than a running server.
