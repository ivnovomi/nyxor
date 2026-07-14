# NyxScript Standard Library Reference

Two layers: **builtin functions** (implemented in Python, always
available, no import needed) and **`lib/*.nyx` modules** (written in
NyxScript itself, loaded via `import "lib/x.nyx" as alias`, resolved
relative to the current working directory — same convention the
interpreter always uses, matching `nyx script run`/`repl`).

For the language itself (syntax, control flow, types), see
[NyxScript Language Guide](NyxScript-Language-Guide).

## Builtin functions

Every builtin below is callable directly, with no import. All are
pure/synchronous with no I/O, **except**:

- `now()` — reads the wall clock (non-deterministic, but no I/O).
- `regex_match`/`regex_find`/`regex_find_all`/`regex_replace` — run in a
  dedicated worker **process** with a 1-second wall-clock timeout, input
  capped at 100,000 characters. See
  [Security § The regex timeout design](Security#the-regex-timeout-design)
  for why a process instead of a thread.

| Function | Signature | Description |
|---|---|---|
| `len` | `(x)` | Length of a list or string |
| `range` | `(a)` / `(a, b)` / `(a, b, step)` | List of integers; capped at 1,000,000 items |
| `upper` | `(s)` | Uppercases a string |
| `lower` | `(s)` | Lowercases a string |
| `strip` | `(s)` | Strips whitespace from both ends |
| `split` | `(text, sep)` | Splits a string on `sep` → list |
| `join` | `(list, sep)` | Joins a list (stringified) with `sep` → string |
| `contains` | `(collection, item)` | Membership test |
| `str` | `(x)` | Converts to string |
| `int` | `(x)` | Converts to int |
| `float` | `(x)` | Converts to float |
| `abs` | `(x)` | Absolute value |
| `round` | `(x)` / `(x, digits)` | Rounds a number |
| `sorted` | `(list)` | New sorted list |
| `reversed` | `(list)` | New reversed list |
| `min` | `(list)` / `(a, b, ...)` | Smallest value |
| `max` | `(list)` / `(a, b, ...)` | Largest value |
| `sum` | `(list)` | Sum of a list of numbers |
| `type_of` | `(x)` | Runtime type name: `"bool"`, `"int"`, `"float"`, `"string"`, `"list"`, `"dict"`, `"function"`, or the underlying Python class name otherwise (e.g. `"NoneType"` for a value like `asset.source_module` that isn't set) |
| `keys` | `(dict)` | Dict keys → list |
| `values` | `(dict)` | Dict values → list |
| `items` | `(dict)` | Dict → list of `[key, value]` pairs |
| `get` | `(dict, key, default)` | Dict lookup with a **mandatory** default — NyxScript has no null to fall back to |
| `replace` | `(text, old, new)` | String replace |
| `starts_with` | `(text, prefix)` | Prefix test |
| `ends_with` | `(text, suffix)` | Suffix test |
| `find` | `(text, needle)` | Index of first match, or `-1` |
| `zip` | `(list, list)` | Pairs elements → list of `[a, b]`, stops at the shorter list |
| `parse_json` | `(text)` | JSON string → NyxScript value; errors if the JSON contains `null` anywhere (unrepresentable) |
| `to_json` | `(value)` | NyxScript value → JSON string |
| `now` | `()` | Current time as Unix epoch seconds (float) |
| `to_iso8601` | `(epoch)` | Formats epoch seconds as an ISO 8601 UTC string |
| `sha256` | `(x)` | SHA-256 hex digest of `str(x)` |
| `md5` | `(x)` | MD5 hex digest of `str(x)` — fingerprinting/dedup, not password hashing |
| `regex_match` | `(text, pattern)` | True if `pattern` matches anywhere in `text` |
| `regex_find` | `(text, pattern, default)` | First match, or `default` if none |
| `regex_find_all` | `(text, pattern)` | Every match as a list (capture groups become nested lists, not tuples) |
| `regex_replace` | `(text, pattern, replacement)` | Substitutes every match |
| `base64_encode` | `(x)` | Base64-encodes `str(x)` |
| `base64_decode` | `(s)` | Decodes base64 `s` back to a UTF-8 string (errors if the decoded bytes aren't valid UTF-8 — no bytes type to hold them otherwise) |
| `random` | `()` | A random float in `[0.0, 1.0)` |

### Byte-level helpers

NyxScript has no bytes type — binary data crosses the `socket.*`
boundary (below) as a UTF-8 string or a list of ints 0-255. These build
and parse that; all pure, always available, no `--unsafe` needed.
Integers pack/unpack in network byte order (big-endian).

| Function | Signature | Description |
|---|---|---|
| `bytes_from_hex` | `(s)` | Hex string → list of byte values |
| `bytes_to_hex` | `(list)` | List of byte values → hex string |
| `bytes_from_string` | `(s)` | UTF-8 encodes `s` → list of byte values |
| `bytes_to_string` | `(list)` | Decodes a list of byte values as UTF-8 |
| `pack_uint16` | `(n)` | `n` as 2 big-endian bytes (a list) |
| `pack_uint32` | `(n)` | `n` as 4 big-endian bytes (a list) |
| `unpack_uint16` | `(list)` | 2 big-endian bytes → int |
| `unpack_uint32` | `(list)` | 4 big-endian bytes → int |

```
print bytes_to_hex(bytes_from_string("AB"))  # 4142
print pack_uint16(4660)                      # [18, 52]
print unpack_uint16([18, 52])                # 4660
```

### Raw packet builders

Also pure and always available (no `--unsafe`) — these only construct
bytes in memory, per RFC 791 (IPv4), RFC 793 (TCP), RFC 768 (UDP), and
RFC 792 (ICMP echo), checksums included. Only *sending* the result over
the network (`socket.raw_send`, below) needs `--unsafe`.

| Function | Signature | Description |
|---|---|---|
| `checksum` | `(list)` | The Internet checksum (RFC 1071) of a list of byte values |
| `build_ip_header` | `(src_ip, dst_ip, protocol, payload[, ttl][, id][, dont_fragment])` | A 20-byte IPv4 header (no options), checksum filled in |
| `build_tcp_header` | `(src_ip, dst_ip, src_port, dst_port, seq, ack, flags, payload[, window])` | A 20-byte TCP header, checksum filled in via the pseudo-header; `flags` is an int bitmask or a string like `"SYN,ACK"` |
| `build_udp_header` | `(src_ip, dst_ip, src_port, dst_port, payload)` | An 8-byte UDP header, checksum filled in via the pseudo-header |
| `build_icmp_echo` | `(identifier, sequence, payload[, is_reply])` | An ICMP echo request (default) or reply packet, checksum filled in |

```
set icmp = build_icmp_echo(1, 1, bytes_from_string("ping"))
set packet = build_ip_header("192.168.1.10", "192.168.1.1", 1, icmp) + icmp
print bytes_to_hex(packet)
```

`src_ip`/`dst_ip` need to be real for TCP/UDP headers even if you never
send the packet — the checksum is computed over a pseudo-header that
includes both addresses, per spec, so a wrong address produces a
structurally valid but wire-invalid packet.

### Higher-order functions

These call a NyxScript function value per item, so they're handled
specially by the interpreter rather than living in the table above — but
they behave like any other builtin:

| Function | Signature | Description |
|---|---|---|
| `map` | `(list, fn)` | New list of `fn(item)` for each item |
| `filter` | `(list, fn)` | Items where `fn(item)` is truthy |
| `sort_by` | `(list, fn)` | List sorted by `fn(item)` as the key |
| `reduce` | `(list, fn, initial)` | Fold: `acc = fn(acc, item)`, starting from `initial` |

```
set nums = [1, 2, 3, 4, 5]
print map(nums, lambda(x): x * 2)              # [2, 4, 6, 8, 10]
print filter(nums, lambda(x): x > 2)           # [3, 4, 5]
print reduce(nums, lambda(acc, x): acc + x, 0) # 15
```

### `ui.*` — interactive prompts

Available in both `nyx script run` (blocks the terminal normally) and
`nyx tui`'s Script tab (suspends the dashboard temporarily) — the same
script works unmodified either way.

| Function | Signature | Returns |
|---|---|---|
| `ui.confirm` | `(question)` | `bool` — yes/no prompt |
| `ui.input` | `(prompt)` | `string` — free-text prompt |
| `ui.select` | `(prompt, options)` | `string` — one of `options` |
| `ui.table` | `(headers, rows)` | prints a table, no return value |
| `ui.banner` | `(text)` | prints a rule with a heading, no return value |
| `ui.status` | `(message)` | prints a dim status line, no return value |

### `socket.*` — raw TCP/UDP network access

⚠️ **Requires `--unsafe`** (CLI/TUI flag, or a script-level `unsafe`
statement — never reachable via `nyx mcp`). Unlike every other module
in this reference, this reaches arbitrary hosts/ports outside NYXOR's
audited scan modules — see
[Security § `--unsafe` gating](Security#unsafe-gating) before reaching
for it. Every blocking call has an explicit timeout; a script that
forgets to `socket.close()` gets cleaned up automatically when a
one-shot run (`nyx script run`, the TUI's Run button) ends.

| Function | Signature | Description |
|---|---|---|
| `socket.connect` | `(host, port[, protocol][, timeout])` | Opens a `"tcp"` (default) or `"udp"` connection, returns a handle |
| `socket.connect_tls` | `(host, port[, timeout][, verify])` | Opens a TCP connection and performs a TLS handshake over it; returns an ordinary handle — every other `socket.*` function works on it unchanged. `verify` (default `true`) validates the certificate; `false` is an explicit opt-out for a host with a self-signed/invalid cert on purpose |
| `socket.send` | `(handle, data)` | Sends a string (UTF-8 encoded) or a list of byte values |
| `socket.recv` | `(handle[, max_bytes][, timeout])` | Reads available data as a list of byte values (default 4096 bytes, capped at 1 MiB) |
| `socket.recv_text` | `(handle[, max_bytes][, timeout])` | Same, decoded as UTF-8 (errors on non-text data — use `socket.recv` + `bytes_to_hex` for binary protocols) |
| `socket.close` | `(handle)` | Closes the connection |

```
unsafe
set h = socket.connect("example.com", 80)
socket.send(h, "GET / HTTP/1.0\r\n\r\n")
print socket.recv_text(h, 4096, 5.0)
socket.close(h)
```

`socket.connect_tls` works identically, just over port 443:

```
unsafe
set h = socket.connect_tls("example.com", 443)
socket.send(h, "GET / HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n")
print socket.recv_text(h, 65536, 5.0)
socket.close(h)
```

### `socket.raw_*` — raw IP send/receive (the "protocol builder")

⚠️ **Requires `--unsafe`**, same as `socket.*` above, plus OS-level
privileges (root on Linux/macOS, Administrator on Windows) — and even
then, **raw send is not usable on Windows in practice**: `IP_HDRINCL`
raw sockets are refused outright by the OS/network stack for every
protocol, a restriction in place since Windows XP SP2, confirmed
empirically during development on a fully administrator-elevated
machine (the socket failed to even open, for ICMP as much as TCP/UDP).
`socket.raw_recv` needs the same privileges and is similarly unreliable
on Windows depending on the network adapter/driver/security software —
Linux/macOS as root is the realistic target for this module.

| Function | Signature | Description |
|---|---|---|
| `socket.raw_send` | `(dst_ip, packet[, timeout])` | Sends one complete IP packet (own header included, e.g. from `build_ip_header`) via `IP_HDRINCL`. Returns bytes sent. |
| `socket.raw_recv` | `(interface_ip[, timeout])` | Opens a raw capture socket bound to a local interface, returns a handle. On Windows, flips on `SIO_RCVALL` (the standard Windows sniffer technique). |
| `socket.raw_read` | `(handle[, max_bytes][, timeout])` | Reads one captured IP packet (header included) as a list of byte values |
| `socket.close` | `(handle)` | Also closes a `raw_recv` handle (and flips `SIO_RCVALL` back off on Windows first) |

```
unsafe
set icmp = build_icmp_echo(1, 1, bytes_from_string("ping"))
set packet = build_ip_header("192.168.1.10", "192.168.1.1", 1, icmp) + icmp
socket.raw_send("192.168.1.1", packet)
```

**`socket.raw_recv` only sees traffic addressed to the given interface**
unless the OS additionally puts the NIC into promiscuous mode. On
non-Windows platforms, NyxScript deliberately does *not* flip
promiscuous mode itself (`ip link set <iface> promisc on` is a
system-wide, shared setting — a much bigger blast radius than anything
else `socket.*` touches, and not something a script should change as a
side effect). If you need to capture other hosts' traffic on a shared
segment, set the interface promiscuous outside NyxScript first, with
the same authorization scrutiny you'd apply to any other packet
capture — see [Security § `socket.raw_*`](Security#unsafe-gating).

## The `⚠️ {{`/`}}` regex gotcha — and the fix

Every *ordinary* NyxScript string literal runs through `{expr}`
interpolation — including regex patterns. A quantifier like `{1,3}` or
`{2,}` looks exactly like an interpolation span and gets silently
evaluated/mangled unless you double the braces:

```
print regex_match("aaa", "a{2,3}")     # WRONG — {2,3} gets interpolated away
print regex_match("aaa", "a{{2,3}}")   # right, but ugly
```

**Better**: use a raw string (`r"..."`) — it never interpolates at all,
so the pattern reads exactly like the regex it is, with no doubling and
no fighting NyxScript's own escape table for `\w`/`\d`/`\s`:

```
print regex_match("aaa", r"a{2,3}")   # right, and reads normally
```

`lib/regex.nyx` (below) writes all of its patterns as raw strings for
exactly this reason. See
[NyxScript Language Guide § Raw strings](NyxScript-Language-Guide#raw-strings)
for the full rules.

## `lib/` modules

Import path is always relative to the current working directory, e.g.
`import "lib/hash.nyx" as hash` run from the repo root.

### `lib/math.nyx`

NyxScript has no `%` operator — `mod()` fills that gap.

| Function | Params | Description |
|---|---|---|
| `mod` | `(a, b)` | Integer remainder of `a / b` |
| `clamp` | `(x, lo, hi)` | Clamps `x` into `[lo, hi]` |
| `mean` | `(numbers)` | Arithmetic mean of a non-empty list |
| `median` | `(numbers)` | Median of a non-empty list |
| `gcd` | `(a, b)` | Greatest common divisor (Euclidean algorithm) |
| `is_prime` | `(n)` | True if `n` is prime |

### `lib/dict.nyx`

Built on the native dict type plus `keys()`/`values()`/`items()`/`get()`.

| Function | Params | Description |
|---|---|---|
| `merge` | `(a, b)` | New dict with `b`'s keys overriding `a`'s |
| `pick` | `(d, wanted_keys)` | New dict containing only the given keys, skipping missing ones |
| `invert` | `(d)` | Swaps keys and values; last key wins on duplicate values |
| `from_pairs` | `(pairs)` | Builds a dict from `[key, value]` pairs — inverse of `items()` |

### `lib/validate.nyx`

Cheap, conservative validators — not full RFC parsers, just enough to
catch obvious typos before spending a network round-trip.

| Function | Params | Description |
|---|---|---|
| `is_valid_port` | `(value)` | True if `value` parses as an int in `[1, 65535]` |
| `is_valid_ipv4` | `(s)` | True if `s` looks like a dotted-quad IPv4 address |
| `is_valid_domain` | `(s)` | Conservative hostname sanity check |

### `lib/collection.nyx`

| Function | Params | Description |
|---|---|---|
| `unique` | `(items)` | Deduplicated, order-preserving |
| `chunk` | `(items, size)` | Splits into sublists of at most `size` |
| `flatten` | `(nested)` | Concatenates a list of lists, one level deep |
| `partition` | `(items, pred)` | `[matching, non_matching]` by `pred(item)` |
| `take` | `(items, n)` | First `n` items (or fewer) |
| `drop` | `(items, n)` | `items` with the first `n` removed |
| `sum_by` | `(items, fn)` | Sum of `fn(item)` across `items` |

### `lib/set.nyx`

Lists as unordered, deduplicated collections — output order follows
first-seen order in the inputs, not sorted (no hashable-set type).

| Function | Params | Description |
|---|---|---|
| `union` | `(a, b)` | All items from either, deduplicated |
| `intersect` | `(a, b)` | Items present in both, deduplicated |
| `difference` | `(a, b)` | Items in `a` not in `b`, deduplicated |
| `symmetric_difference` | `(a, b)` | Items in exactly one of `a`/`b` |
| `is_subset` | `(a, b)` | True if every item in `a` is also in `b` |
| `is_disjoint` | `(a, b)` | True if `a` and `b` share no items |

### `lib/strings.nyx`

| Function | Params | Description |
|---|---|---|
| `title_case` | `(s)` | Title-cases each whitespace-separated word |
| `truncate` | `(s, max_len)` | Truncates to `max_len` chars, appends `"..."` if longer |

### `lib/format.nyx`

Human-readable formatting for script output.

| Function | Params | Description |
|---|---|---|
| `pad_left` | `(s, width, ch)` | Left-pads with `ch` to at least `width` chars |
| `pad_right` | `(s, width, ch)` | Right-pads with `ch` to at least `width` chars |
| `human_bytes` | `(n)` | e.g. `"1.5 KB"`, `"3.0 MB"` |
| `human_duration` | `(total_seconds)` | e.g. `"1h 2m 3s"`, drops zero leading units |
| `bullet_list` | `(items)` | Newline-separated, `"- "`-prefixed list |

### `lib/time.nyx`

Built on `now()`/`to_iso8601()` — epoch seconds as a float, since
NyxScript has no native datetime type. `import "lib/format.nyx" as
format` internally.

| Function | Params | Description |
|---|---|---|
| `elapsed` | `(start)` | Seconds since epoch timestamp `start` |
| `is_older_than` | `(start, max_age_seconds)` | True if `start` is more than `max_age_seconds` in the past |
| `humanize` | `(seconds)` | Delegates to `format.human_duration` |
| `now_iso` | `()` | Current time as an ISO 8601 UTC string |
| `backoff_delay` | `(attempt, base_seconds)` | Exponential backoff: `base_seconds * 2^attempt` (via repeated doubling — no `**` operator in NyxScript) |
| `time_it` | `(fn)` | Calls `fn()`, returns `[result, elapsed_seconds]` |

### `lib/hash.nyx`

Built on `sha256()`/`md5()` — for fingerprinting/dedup/change-detection,
not password storage.

| Function | Params | Description |
|---|---|---|
| `short_hash` | `(s, length)` | First `length` characters of `sha256(s)` |
| `fingerprint` | `(parts)` | One sha256 digest over a list of values, order-sensitive |
| `has_changed` | `(previous_hash, current_value)` | True if `sha256(current_value)` differs from `previous_hash` |

### `lib/csv.nyx`

Hand-written RFC-4180-ish parser/writer (no `--unsafe` escape hatch to
reach Python's `csv` module needed). Quote-aware: handles
commas/newlines inside quoted fields and doubled `""` as an escaped
quote.

| Function | Params | Description |
|---|---|---|
| `parse_csv` | `(text)` | CSV text → list of rows (each a list of string fields) |
| `to_csv` | `(rows)` | List of rows → CSV text, quoting fields that need it |

### `lib/regex.nyx`

Text-extraction helpers built on the `regex_*` builtins — see the
`{{`/`}}` gotcha above, which every pattern in this file works around.

| Function | Params | Description |
|---|---|---|
| `extract_ips` | `(text)` | Every dotted-quad IPv4-looking substring (doesn't validate octet ranges — see `net.is_private_ipv4` for that) |
| `extract_emails` | `(text)` | Every email-looking substring |
| `extract_urls` | `(text)` | Every `http(s)://` URL substring, up to the next whitespace |
| `matches_any` | `(text, patterns)` | True if any pattern in the list matches |

### `lib/random.nyx`

Built on the `random()` builtin.

| Function | Params | Description |
|---|---|---|
| `random_int` | `(lo, hi)` | A random integer in `[lo, hi]`, inclusive both ends |
| `choice` | `(items)` | A random element from a non-empty list |
| `shuffle` | `(items)` | A new list in random order (Fisher-Yates) — does not mutate `items` |
| `sample` | `(items, n)` | `n` random items without replacement |
| `jitter` | `(base_seconds, spread)` | `base_seconds` ± up to `spread`, for randomized retry delays |

### `lib/text.nyx`

More string helpers on top of the builtins and `lib/strings.nyx`. No
separate `repeat()` — the native `*` operator already repeats a string
(`"x" * 3`).

| Function | Params | Description |
|---|---|---|
| `capitalize` | `(s)` | Uppercases the first character, lowercases the rest |
| `center` | `(s, width, ch)` | Centers `s` in a field of `width`, padded with `ch` |
| `reverse` | `(s)` | `s` with characters in reverse order |
| `contains_ignore_case` | `(text, needle)` | Case-insensitive substring test |
| `count_occurrences` | `(text, needle)` | Non-overlapping occurrence count |
| `is_blank` | `(s)` | True if `s` is empty or only whitespace |
| `words` | `(s)` | Every whitespace-separated word in `s` |
| `lines` | `(s)` | Splits `s` on `\n`, keeping empty lines |
| `slugify` | `(s)` | Lowercases and collapses non-alphanumeric runs into a single hyphen |

### `lib/table.nyx`

| Function | Params | Description |
|---|---|---|
| `render` | `(headers, rows)` | An aligned, pipe-delimited plain-text table as a string — for `print`/`save`, distinct from the interactive `ui.table` (which needs a live terminal) |

### `lib/net.nyx`

Pure string/int parsing for target strings and IPv4 addresses — no
actual network I/O (that's what `run dns`/`run tls`/`run http` are for).
`import "lib/validate.nyx" as validate` internally.

| Function | Params | Description |
|---|---|---|
| `host_from_target` | `(raw)` | Bare hostname/IP from a domain, `host:port`, `scheme://host/path`, or `[ipv6]` string |
| `port_from_target` | `(raw, default_port)` | Port from a `host:port` string, or `default_port` if absent/invalid |
| `count_char` | `(s, ch)` | Occurrences of a single character in `s` |
| `octets` | `(s)` | Dotted-quad IPv4 string → list of 4 ints (assumes already validated) |
| `is_private_ipv4` | `(s)` | True if `s` is private/loopback/link-local (RFC 1918 + friends; precise about the 172.16.0.0/12 second-octet range) |

### `lib/ftp.nyx`

A minimal, read-oriented FTP client built entirely on `socket.*` — no new
builtins needed. Requires `--unsafe` transitively, since every function
here calls `socket.*` under the hood. Deliberately read-only: `connect`/
`login`/`pwd`/`cwd`/`list`/`retr`, no `STOR`/`DELE`/`MKD`/`RMD` — if you
need to write to a server, `socket.send` directly against the connection
object's `"handle"` gives you the same control connection this module
does.

Connection objects returned by `connect()` are plain dicts
(`"handle"`, `"host"`, `"code"`, `"message"`, plus an internal
`"buffer"` field the response reader uses) — pass the same object into
every subsequent call.

| Function | Params | Description |
|---|---|---|
| `connect` | `(host, port)` | Opens the control connection; returns a connection object |
| `login` | `(conn, username, password)` | `USER`/`PASS`; returns `[code, message]` from the final response |
| `anonymous_login` | `(conn)` | `login(conn, "anonymous", "anonymous@")` |
| `pwd` | `(conn)` | The current working directory, as reported by `PWD` |
| `cwd` | `(conn, path)` | Changes directory; returns `[code, message]` |
| `set_binary_mode` | `(conn)` | `TYPE I` — for downloading files as-is |
| `set_ascii_mode` | `(conn)` | `TYPE A` — the default on most servers |
| `list` | `(conn, path)` | `PASV` + `LIST`; returns the raw directory listing text |
| `retr` | `(conn, remote_path)` | `PASV` + `RETR`; returns the file's content as UTF-8 text |
| `quit` | `(conn)` | Sends `QUIT` and closes the control connection |

The response reader keeps a per-connection leftover buffer
(`conn["buffer"]`) rather than assuming one `socket.recv_text` call maps
to exactly one FTP response — a real server can (and, tested against a
local mock server during development, reliably does) flush a `150`
reply and the following `226 Transfer complete` in the same TCP segment
when the data connection was already open before the command was sent.
Treating "the last `\d{3} ` line in whatever came back" as the answer
silently returns the wrong response in that case; the fix parses one
line at a time and stops at the first complete response, stashing
anything read past it for the next call.

### `lib/http.nyx`

A minimal HTTP/1.1 client built on `socket.*`/`socket.connect_tls` — the
"protocol builder" HTTP piece, distinct from the audited, passive `run
http` module. Requires `--unsafe` transitively. Every request sends
`Connection: close` and reads until the server closes the connection —
there's no chunked transfer-encoding or keep-alive support, so this is
a scriptable request/response tool, not a full HTTP client.

| Function | Params | Description |
|---|---|---|
| `request` | `(method, url, headers, body, timeout)` | Sends one request, returns `{status_code, status_text, headers, body}` |
| `get` | `(url, headers, timeout)` | `request("GET", url, headers, "", timeout)` |
| `post` | `(url, body, headers, timeout)` | `request("POST", url, headers, body, timeout)` |
| `build_request` | `(method, path, host, headers, body)` | Builds a raw HTTP/1.1 request as text — adds `Host`/`Connection`/`Content-Length` automatically unless already present in `headers` |
| `parse_response` | `(raw)` | Parses a raw HTTP response string into `{status_code, status_text, headers, body}` (header keys lowercased) |

```
unsafe
import "lib/http.nyx" as http

set resp = http.get("https://example.com/", {}, 8.0)
print resp["status_code"]
print resp["headers"]["content-type"]
print resp["body"]
```

`request()`/`get()`/`post()` pick `socket.connect` or
`socket.connect_tls` based on the URL's scheme (`http://` vs
`https://`, defaulting to `http://` and port 80 if no scheme is given).
URL parsing is intentionally minimal — enough to split scheme/host/
port/path for sending a request, not a full RFC 3986 parser.

### `lib/asset.nyx`

Helpers over the `Asset` lists a module like `network.discover` attaches
to its `ModuleResult` (`.assets`). `kind`/`identifier`/`attributes` are
always set; `source_module` can be Python's `None` under the hood, so
it's handled defensively via `type_of()` rather than accessed directly.

| Function | Params | Description |
|---|---|---|
| `by_kind` | `(assets, kind)` | Only the assets whose `.kind` equals `kind` |
| `kinds` | `(assets)` | Distinct `.kind` values, first-seen order |
| `identifiers` | `(assets)` | Every `.identifier`, in order |
| `count_by_kind` | `(assets)` | Dict of `kind -> count` |
| `group_by_kind` | `(assets)` | Dict of `kind -> [asset, ...]` |
| `attr` | `(a, key, default)` | `a.attributes[key]`, or `default` |
| `has_attr` | `(a, key)` | True if `key` is present in `a.attributes` |
| `has_source` | `(a)` | True if `a.source_module` is set |
| `source_or` | `(a, default)` | `a.source_module`, or `default` if unset |
| `summary_line` | `(a)` | `"kind: identifier"` |

### `lib/lambdas.nyx`

Functional combinators built on top of the native `map`/`filter`/
`sort_by`/`reduce`. **Naming note**: none of these are named `find`,
`min`, `max`, `sum`, etc. — a bare (unqualified) call always resolves
against NyxScript's builtins first, even inside this file, so a local
function sharing a builtin's name would be silently shadowed rather than
override it.

| Function | Params | Description |
|---|---|---|
| `identity` | `(x)` | Returns `x` unchanged |
| `constant` | `(x)` | Function that ignores its argument, always returns `x` |
| `compose` | `(f, g)` | Right-to-left: `compose(f, g)(x) == f(g(x))` |
| `pipe` | `(f, g)` | Left-to-right: `pipe(f, g)(x) == g(f(x))` |
| `flip` | `(f)` | `f` with its first two arguments swapped |
| `partial` | `(f, a)` | Fixes `f`'s first argument to `a` |
| `negate` | `(pred)` | Predicate that's true exactly when `pred` is false |
| `any_of` | `(items, pred)` | True if `pred` is truthy for at least one item |
| `all_of` | `(items, pred)` | True if `pred` is truthy for every item |
| `none_of` | `(items, pred)` | True if `pred` is falsy for every item |
| `count_where` | `(items, pred)` | Count of items where `pred` is truthy |
| `find_where` | `(items, pred, default)` | First item where `pred` is truthy, or `default` |
| `flat_map` | `(items, fn)` | Maps `fn` (must return a list) over `items`, flattens one level |
| `group_by` | `(items, key_fn)` | Dict of `key_fn(item) -> [items with that key]` |
| `times` | `(n, fn)` | Calls `fn(i)` for `i` in `0..n-1`, collects results |

### `lib/finding.nyx`

| Function | Params | Description |
|---|---|---|
| `count_by_severity` | `(results, severity)` | Findings across `results` matching `severity` |
| `total_findings` | `(results)` | Total finding count across `results` |
| `worst_severity` | `(results)` | Worst severity present (defaults to `"info"`) |
| `summary_line` | `(result, target)` | `"target: N finding(s), worst severity: X"` |

### `lib/report.nyx`

`import "lib/finding.nyx" as findings` internally.

| Function | Params | Description |
|---|---|---|
| `severity_breakdown` | `(results)` | Dict of `severity -> count` |
| `print_summary` | `(results, target)` | Prints a one-line summary plus a per-severity table (`ui.table`) |

## A worked example combining several modules

```
import "lib/validate.nyx" as validate
import "lib/lambdas.nyx" as fn
import "lib/math.nyx" as math
import "lib/report.nyx" as report

set targets = ["example.com", "not a domain", "openai.com"]
set good_targets = filter(targets, lambda(t): validate.is_valid_domain(t))

set all_results = []
set findings_per_target = []

foreach target in good_targets:
    run audit target as results
    report.print_summary(results, target)

    set all_results = all_results + results
    set findings_per_target = findings_per_target + [fn.count_where(results, lambda(r): len(r.findings) > 0)]
end

print "Average modules-with-findings per target: " + str(math.mean(findings_per_target))

save all_results to "report.json"
```
