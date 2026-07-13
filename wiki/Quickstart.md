# Quickstart

Assumes you've already installed NYXOR — see [Installation](Installation)
if not.

## Your first audit

```bash
nyx audit example.com
```

One command: a live DNS + TLS + HTTP assessment. You'll see, in order:

1. A terminal pill badge — `security  A  92/100` in truecolor, no image
   viewer needed.
2. A summary table per module (`dns.lookup`, `tls.inspect`,
   `http.inspect`) with every finding, color-coded by severity
   (`critical`/`high`/`medium`/`low`/`info`).
3. Passive tech-stack/CDN/WAF fingerprinting, if anything was detected
   from headers/cookies/markup already fetched — zero extra requests.

Only ever point this at something you're authorized to check. Everything
NYXOR does is passive (DNS lookups, TLS handshakes, HTTP requests,
public CT logs) — no exploitation, no packet crafting — but "passive"
doesn't mean "permitted."

## Plain-English output

```bash
nyx audit example.com --dumber            # no-jargon explanation of every finding
nyx audit example.com --fix-suggestions   # concrete remediation steps for medium+ findings
nyx analyze example.com                   # a short written summary instead of a table
```

All three use a local [Ollama](https://ollama.com) model if one's
running (`ollama pull llama3.2` once, first), and fall back to a
templated/rule-based version automatically if not — nothing ever breaks
because a model isn't installed. See [FAQ § Local AI setup](FAQ-Troubleshooting#local-ai-setup).

## A badge for your README

```bash
nyx audit example.com --badge badge.svg
```

Writes a shields.io-style flat SVG (`nyxor: example.com | A`) you can
embed anywhere. If you'd rather it stay live and re-audit on every page
load instead of a static file, see [REST API § the badge endpoint](REST-API#get-badgedomainsvg).

## Keep watching, not just a one-shot

```bash
nyx watch example.com --interval 300 --narrate
```

Reruns the audit every 5 minutes (`--interval` seconds) and stays quiet
— a heartbeat line — until something actually changes: a new finding, a
resolved one, or a grade transition, each timestamped and color-coded.
`--narrate` asks a local model for a one-line plain-English take on the
change, same graceful fallback as everything else AI-touched.

## Everything else in one shot

```bash
nyx recon example.com          # subdomains via certificate transparency (never touches the target)
nyx dns lookup example.com     # DNS records, DNSSEC, mail posture, standalone
nyx tls inspect example.com    # certificate + protocol/cipher, standalone
nyx http inspect https://example.com  # headers/redirects/cookies/fingerprint, standalone
nyx network discover 192.168.1.0/24   # host discovery on a range you're authorized to scan
nyx network scan 192.168.1.10  # TCP service enumeration on one host
nyx hostcheck                  # local host hygiene — no target needed, checks *this* machine
```

Full flag reference for every command: [CLI Reference](CLI-Reference).

## Your first NyxScript

NyxScript is NYXOR's own automation language — batch-drive any module
without shelling out to `nyx` repeatedly.

```bash
nyx script new my-audit.nyx
```

writes a starter file. Open it, or paste this:

```
import "lib/validate.nyx" as validate

set targets = ["example.com", "example.org"]

foreach target in targets:
    if not validate.is_valid_domain(target):
        print "skipping {target}: doesn't look like a domain"
        continue
    end

    print "Auditing {target}..."
    run audit target as result
    print "  {len(result)} module result(s)"
end
```

```bash
nyx script lint my-audit.nyx   # static-check — no network access, catches typos before they cost a round-trip
nyx script run my-audit.nyx    # lints, then executes
```

Full language reference: [NyxScript Language Guide](NyxScript-Language-Guide).
Every function available: [NyxScript Standard Library Reference](NyxScript-Standard-Library-Reference).

## Your first TUI session

```bash
nyx tui
```

A full-screen dashboard over the exact same functions the CLI calls:
live environment diagnostics, a sortable inventory table, a scan form
that streams findings in as they arrive, a syntax-highlighted NyxScript
editor with autocomplete, and a plugin browser. Keys: `1`–`5` switch
tabs, `r` refreshes, `q` quits.

## Where scan output goes

By default, everything prints to your terminal. To also write a
structured report:

```bash
nyx audit example.com --output report.html    # format inferred from the extension
nyx audit example.com --output report.json
nyx audit example.com --output report.sarif   # for GitHub Code Scanning — see GitHub-Action
nyx --json audit example.com                  # JSON straight to stdout instead of the table
```

## What's next

- Point it at CI: [GitHub Action](GitHub-Action).
- Automate a fleet of targets: [NyxScript Language Guide](NyxScript-Language-Guide).
- Run it as a service other tools can call: [REST API](REST-API).
- Add your own module: [Plugin Development](Plugin-Development).
