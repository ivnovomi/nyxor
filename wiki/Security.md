# Security

## Design principles

- **Passive by default, always.** `nyx`'s own audit/dns/tls/http/network
  modules — the only thing usable via `nyx mcp` — stay strictly to DNS
  lookups, TLS handshakes, HTTP requests, public certificate-transparency
  logs, response-header/cookie/markup fingerprinting: no exploitation,
  nothing that needs elevated privileges. `nyx hostcheck` is the same
  story locally — two explainable, signature-free checks (masquerading
  processes, suspicious autorun), not an antivirus. NyxScript's opt-in
  `socket.*`/`socket.raw_*` (below) are the one deliberate exception —
  gated behind `--unsafe`, never reachable through `nyx mcp`, and each
  a considered scope decision, not a quiet crack in "passive by
  default".
- **Only audit what you're authorized to.** "Passive" doesn't mean
  "permitted" — point NYXOR at infrastructure you own or have explicit
  authorization to assess.
- **`--unsafe` gates real code execution.** NyxScript's grammar itself
  has no `eval` and can't run arbitrary code. The two statements that
  can (`python:` blocks, `pip`) are disabled unless the caller opts in
  explicitly (`--unsafe` on `nyx script run`/`repl`, the Unsafe switch in
  `nyx tui`) — and neither is reachable through the MCP server at all,
  since an MCP tool can be invoked autonomously with no human confirming
  each call.
- **Resource limits, not blanket refusal.** Rather than disabling
  features that *could* be misused, NyxScript caps their blast radius —
  see [NyxScript resource limits](NyxScript-Language-Guide#resource-limits)
  for the full table (call depth, loop iterations, allocation size,
  import depth, regex timeout).

## The regex timeout design

Adding `regex_match`/`regex_find`/`regex_find_all`/`regex_replace`
raised an obvious question: a NyxScript script isn't `--unsafe`-gated,
so what stops a pattern like `(a+)+b` against a long non-matching input
— textbook catastrophic backtracking — from hanging the interpreter (or
`nyx serve`, if a future version ever exposed script execution over
HTTP) indefinitely?

Two designs were tried and rejected before landing on the one that
ships:

1. **A shared `ThreadPoolExecutor` with `future.result(timeout=...)`.**
   Looked correct, wasn't: `ThreadPoolExecutor` registers an `atexit`
   hook that joins every submitted task before the process is allowed to
   exit — timed out or not. A single stuck regex would hang the whole
   `nyx` process on shutdown, the exact failure mode being defended
   against.
2. **A plain `daemon=True` thread with `Thread.join(timeout=...)`.**
   Fixed the shutdown hang, but didn't actually bound the wait: CPython's
   `re` engine never releases the GIL mid-match, so a catastrophic
   pattern holds the GIL for its entire run. The watchdog thread waiting
   on `.join(timeout=...)` can't get scheduled to even notice the
   deadline passed, since noticing it also requires the GIL the runaway
   match is holding. Verified empirically — the process didn't return
   control even after several times the configured timeout.

**What ships**: a persistent worker **process** (`multiprocessing`,
`spawn` context on every platform), reused across calls so the ~tens-
to-hundreds-of-milliseconds spawn cost is paid roughly once per `nyx`
invocation rather than per regex call. A process has its own GIL, so
unlike a thread it can be killed outright (`Process.terminate()`/
`.kill()`) when it overruns the 1-second timeout — and is, with the
worker replaced fresh on the next call. Input length is separately
capped at 100,000 characters.

Building this also surfaced two real language bugs in the lexer, both
fixed:

- **Escapes silently dropped their backslash.** `\w`/`\d`/`\s` (any
  escape not in the small recognized table) used to become `w`/`d`/`s`
  — making regex character classes essentially unwritable. An unknown
  escape now keeps both characters, matching Python's own string literal
  behavior.
- **String interpolation collides with regex quantifiers.** Every
  NyxScript string runs through `{expr}` interpolation, so `{1,3}` reads
  as an interpolation span and gets silently mangled unless doubled
  (`{{1,3}}`). Not a bug — interpolation is intentional — but sharp
  enough that it's called out explicitly in
  [NyxScript Standard Library Reference](NyxScript-Standard-Library-Reference#the-️-gotcha).

## The REST API's SSRF guard

`nyx serve` refuses to target private/loopback/link-local/reserved/
multicast/unspecified addresses on every scan endpoint — otherwise an
internet-facing instance would be a generic internal-network probe for
anyone who could reach it. Full detail: [REST API § The SSRF guard](REST-API#the-ssrf-guard).

The guard was originally bypassable via HTTP redirects: it validated
only the URL the caller typed, but `/http` and `/audit` follow
redirects manually, and a public redirector could bounce the request to
`http://169.254.169.254/...` (cloud instance metadata) or an internal
service. Fixed by threading an optional `validate_url` callback through
the HTTP inspector so it's checked on the initial request **and every
redirect hop** — the callback is only wired up by the API layer, so the
CLI/TUI/NyxScript (meant to be able to target internal hosts on
purpose) are unaffected.

It was also bypassable via DNS rebinding: validating a hostname and
then letting the HTTP/TLS client resolve it *again* to actually connect
are two independent DNS lookups, and a short-TTL nameserver can answer
the first with a public address and the second with a private one.
Fixed by having `validate_url` return the specific IP it validated and
pinning the actual connection to it (`Host`/SNI override for HTTP, a
direct-IP dial for TLS) instead of letting the connection re-resolve
the hostname on its own — closed for `/http`, `/tls`, and `/audit`.

## XSS fixes this project shipped and fixed

Two reflected-XSS issues were found and fixed in the REST API during a
security review of this codebase, both before any public release:

1. **`GET /badge/{domain}.svg`** — the badge SVG interpolated the
   `label` parameter (the raw URL path segment) into XML/SVG via an
   f-string with no escaping. A crafted "domain" like
   `"><script>...` broke out of an attribute and injected markup into
   the served SVG — meaningful because the badge is explicitly designed
   to be embedded in third-party READMEs and dashboards. Fixed with
   `xml.sax.saxutils.escape` (including quotes, not just `&<>`) before
   interpolation.
2. **`GET /oauth/device`** — the device-login approval page reflected
   `user_code` into an HTML attribute unescaped. A crafted link could
   break out and inject script into the one page where a user confirms
   "yes, approve this login" — enough to hijack that approval into
   approving an attacker's device code instead. Fixed with `html.escape`.

Both are covered by regression tests asserting a crafted payload never
appears unescaped in the response.

## Path traversal in NyxScript's `save`

`save results to "path"` resolved the destination as `base_dir /
path_str` — but `pathlib`'s `/` operator silently **discards** `base_dir`
when `path_str` is absolute (`/etc/cron.d/x`, `C:\Windows\x`), and
nothing checked for `../` walking out of the directory either. This
worked without `--unsafe`, which broke the "safe by default" framing
`python:`/`pip` gating implies — since NyxScript scripts are explicitly
meant to be shared and run by others, a downloaded "audit script" could
silently write outside its working directory. Fixed by resolving and
checking containment against `base_dir`, matching the pattern `import`
already used.

## Allocation caps

`range(10**12)` and `"x" * 10**12` are both single-call-does-a-lot
patterns: two tiny operands requesting an allocation orders of magnitude
larger than anything a loop-iteration cap would catch (there's no loop
to count). Both are capped at 1,000,000 resulting items — the same
order of magnitude as the pre-existing `while`-loop iteration cap — and
raise a normal, catchable script error past that limit rather than
hanging or exhausting memory.

## `--unsafe` gating

`python:` blocks run as real Python with direct read/write access to
the script's variables; `pip` installs a package into the current
environment; `socket.*` opens a real TCP/UDP connection to whatever
host:port the script names. All three step outside NyxScript's "just
makes requests to the targets you name via audited scan modules" safety
model entirely, so all three require `--unsafe` — treat a script using
any of them like you would any other executable you're choosing to run.

`socket.*` in particular is a genuine identity shift for the project,
not just another builtin: `run dns`/`run tls`/`run http`/
`network.discover`/`network.scan` are each a bounded, passive,
already-scored observation — a raw socket lets a script speak whatever
protocol it wants to whatever destination it wants, which NYXOR can't
describe or bound the meaning of. It's still built with the same care
as everything else here (every blocking call has an explicit timeout
via `asyncio.to_thread`, connections a script forgets to close are
cleaned up automatically at the end of a one-shot run), but the
capability itself is a deliberate, considered expansion, not something
that crept in as a side effect of another feature.

## `socket.connect_tls` and `lib/http.nyx`

`socket.connect_tls` is a TLS-wrapped `socket.connect` — same
`--unsafe` gate, same handle-based API, no new capability class beyond
"the connection happens to be encrypted." Certificate verification is
on by default (`ssl.create_default_context()`, the same defaults
Python's own `ssl`/`httpx` use); `verify: false` is an explicit,
documented opt-out for a script that needs to talk to a host with a
self-signed or otherwise invalid certificate on purpose — the same
posture as everything else `--unsafe`-gated here: safe by default, with
an opt-out a reviewer can spot in a diff rather than a silent one.
Verified against both outcomes during development with a local,
throwaway self-signed certificate: `verify: true` correctly rejects it
(no real network or CA involved), `verify: false` connects.

`lib/http.nyx` is a thin HTTP/1.1 client built entirely on
`socket.connect`/`socket.connect_tls` — it doesn't add any capability
`socket.*` didn't already have, just packages request/response framing
on top of it, the same relationship `lib/ftp.nyx` has to `socket.*`.

## `socket.raw_*` and the packet builder — a second, larger identity shift

`checksum`/`build_ip_header`/`build_tcp_header`/`build_udp_header`/
`build_icmp_echo` (pure, no `--unsafe`) plus `socket.raw_send`/
`socket.raw_recv`/`socket.raw_read` (behind `--unsafe`, like the rest of
`socket.*`) are a second step past `socket.connect`/`send`/`recv`, and a
meaningfully bigger one: `socket.connect` still asks the OS to establish
a normal, well-formed connection on the caller's behalf — the kernel's
TCP/UDP stack won't let a script lie about who it is. `socket.raw_send`
hands the kernel a fully-formed IP packet, source address included, and
asks it to just put that on the wire — a script can put someone else's
address in the source field. That's IP spoofing capability, not just
"talk to more hosts than the audited scan modules cover", and it's why
this shipped as its own explicit `AskUserQuestion` scope decision rather
than folding into the existing `socket.*` gate silently: the maintainer
was shown the three-way split (packet builder only / + raw send / +
raw receive-and-sniff) with each tier's implications spelled out, and
chose the full set.

`socket.raw_recv` is the largest step of the three. `socket.raw_send`
still only affects packets the *script itself* originates; a capture
socket can observe traffic the script had no hand in creating —
depending on the network segment and OS, that can include other
devices' traffic, not just the host running NYXOR. NyxScript
deliberately does not flip a NIC into promiscuous mode on the caller's
behalf (see [NyxScript Standard Library Reference §
`socket.raw_*`](NyxScript-Standard-Library-Reference#socketraw_--raw-ip-sendreceive-the-protocol-builder))
— that's a shared, system-wide setting change with a blast radius well
past "reaches a network host `socket.*` wasn't scoped for", and it's the
one place where NYXOR's usual authorization framing ("audit hosts
you're authorized to assess") isn't quite sufficient on its own: capturing
traffic on a shared segment can implicate devices and traffic that
belong to someone who never consented to being observed, even if the
person running the script is authorized against the target host. Treat
this the same as you would any other packet-capture tool — get
authorization for the network segment, not just the target.

**What was actually verified, not assumed**: this was tested against a
real, administrator-elevated Windows environment during development,
not just reasoned about from documentation. The results matter for
setting expectations: `IP_HDRINCL` raw sockets — required for
`socket.raw_send` and for `socket.raw_recv`'s Windows `SIO_RCVALL` path
— were refused outright by the OS/network stack for every IP protocol
tried (ICMP included), even with a fully elevated administrator token.
Raw ICMP *without* `IP_HDRINCL` (letting the OS build the IP header
itself) worked fine in the same environment — but that's a different,
narrower capability than the full custom-header packet builder exposes,
and isn't what `socket.raw_send` implements. In practice, this module's
realistic home is root on Linux/macOS; treat Windows support as
"present in the code, refused by the OS" rather than "works". Both
outcomes — success and a clean, catchable `PermissionError`/`OSError` —
are covered by tests, since which one applies depends on where NYXOR
runs, not on a bug either way.

A script can also self-enable them with a bare `unsafe` statement
instead of the caller passing `--unsafe` — see
[NyxScript Language Guide § Escape hatches](NyxScript-Language-Guide#escape-hatches-python-and-pip).
This deliberately inverts the earlier model, where `python:`/`pip` were
opt-in only by whoever *runs* the script, never by the script itself —
worth knowing before treating a shared `.nyx` file as inert just because
you didn't pass `--unsafe` yourself.

## The `unsafe` statement vs. MCP

Adding the `unsafe` statement surfaced a real gap before it ever
shipped: `nyx mcp`'s `run_nyxscript` tool hardcodes `unsafe=False`
specifically so an MCP call can never reach `python:`/`pip`/`socket.*`
— but that flag is only a *starting* value on the interpreter, not a
hard ceiling. A script submitted through that tool with a bare `unsafe`
statement at the top would have self-escalated past `unsafe=False`
anyway, defeating the one guarantee `run_nyxscript`'s own docstring
makes — verified directly for `socket.*` too when it shipped, not
assumed to be covered by the existing fix.

Fixed with a second, independent flag: `allow_unsafe_directive`
(default `True`, so `nyx script run`/`nyx tui` are unaffected — that's
the whole point of the feature). `run_nyxscript` sets it `False`, which
makes the `unsafe` statement raise a script error instead of silently
granting what the caller tried to withhold. `unsafe=False` alone was
never enough to guarantee that; `allow_unsafe_directive=False` is what
actually does.

## MCP is deliberately narrower than the CLI

`nyx mcp` exposes `audit`, `dns_lookup`, `tls_inspect`, `http_inspect`,
`recon`, `hostcheck`, `lint_nyxscript`, and `run_nyxscript` — not
`hostcheck --kill` (which terminates local processes) and not
`--unsafe` NyxScript execution. The reasoning: an MCP tool can be
invoked autonomously by an agent with no human confirming each
individual call, so anything destructive or capable of arbitrary code
execution is simply not offered as a tool in the first place, rather
than relying on a confirmation prompt that might not exist in every MCP
client.

## How this project is built

NYXOR is built with Claude Code as a pair-programmer — not a secret,
not hidden. Architecture, scope, and verification decisions are the
maintainer's; judge the project by its tests and whether it actually
works, the same standard you'd apply to any other codebase regardless
of how it was written. See
[`docs/contributing.md`](https://github.com/ivnovomi/nyxor/blob/main/docs/contributing.md#how-this-project-is-built)
for the fuller statement.

## Reporting a vulnerability

Found something? Open an issue on the
[GitHub repository](https://github.com/ivnovomi/nyxor/issues) — for
anything you'd rather not post publicly before a fix ships, note that in
the issue and a maintainer will follow up privately.
