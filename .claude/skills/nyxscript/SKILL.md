---
name: nyxscript
description: Write, lint, and run NyxScript (.nyx) automation files for NYXOR — a small language for batch-driving audit/dns/tls/http/network/recon scan modules. Use whenever the user asks to write a .nyx script, automate a NYXOR scan, or debug NyxScript syntax/lint/runtime errors.
---

# NyxScript

NyxScript is NYXOR's own small automation language — not YAML, not a
config format, an actual lexer/parser/interpreter/linter language that
batch-drives NYXOR's scan modules (`audit`, `dns`, `tls`, `http`,
`network.discover`, `network.scan`, `recon`). Every `run`
statement calls the exact same `async def run_*()` coroutine the CLI,
TUI, REST API, and MCP server use — NyxScript is a fifth front-end over
that shared engine, never a reimplementation.

## Before writing a script

1. If the `nyxor` MCP server is connected, prefer its `lint_nyxscript`
   and `run_nyxscript` tools over shelling out — they run the identical
   `lint_source()`/`run_script()` calls.
2. Otherwise use the CLI: `nyx script new file.nyx` scaffolds a starter,
   `nyx script lint file.nyx` checks without executing, `nyx script run
   file.nyx` executes (add `--unsafe` only if the script needs a
   `python:`/`pip` block — see below).
3. **Always lint before claiming a script works.** The linter is pure
   static analysis (no execution, no network) and catches undefined
   variables, unknown modules/functions, bad `break`/`continue`/`return`
   placement, and empty blocks — cheaper and safer than running it to
   find out.

## Language at a glance

Statements, one per line; blocks (`if`, `foreach`, `while`, `func`)
close with `end`, not indentation:

```
set target = "example.com"

if target != "":
    run audit target as result
    save result to "report.html"
end
```

**Types**: string (`"..."`/`'...'`, with `\n \t \r \\ \" \'` escapes and
`{expr}` interpolation), number (`int`/`float`), `true`/`false`, list
(`[1, 2, 3]`, heterogeneous, indexable), dict (`{"a": 1, "b": 2}`,
indexable, string/number/bool keys). No `null` — an unset variable is a
lint error, not a value, and `get(d, key, default)` requires an explicit
default for the same reason.

`set CONTAINER[index]... = expr` mutates a list or dict in place (the
only mutation-through-indexing NyxScript has; `.field` stays read-only —
no `x.y = z`). Chains: `set d["a"]["b"] = 1`.

**Variables**: `set name = expr` both declares and reassigns. No
closures — one global scope, plus one local scope per active function
call; a function's fallback scope is where it was *defined*, not where
it was *called from* (this is what makes library sibling-calls work
correctly — see Libraries below).

**Operators**, loosest to tightest precedence: `or` → `and` → `not` →
`== != < <= > >=` → `+ -` → `* /` → unary `-` → primary. `+` concatenates
two strings; mismatched-type arithmetic raises a clear runtime error
rather than silently coercing.

**Postfix chains**: indexing (`list[0]`), attribute access
(`value.field`, read-only — no `x.y = z`), and calls (`fn(a, b)`), all
chainable: `result[0].findings[0].severity`.

**String interpolation**: `{expr}` inside a string runs full NyxScript,
not just a bare name; `{{`/`}}` are literal braces.

**Raw strings**: `r"..."` / `r'...'` — no escapes, no `{expr}`
interpolation, every character between the quotes is literal. Use these
for regex patterns (`r"\d{2,4}"` instead of `"\\d{{2,4}}"`) and Windows
paths (`r"C:\Users\x"`) — the one exception is a backslash right before
the closing quote, which doesn't end the string but stays in the value.

**Control flow**:

```
if EXPR:
    ...
else:
    ...
end

foreach VAR in LIST_EXPR:
    ...
end

while EXPR:            # 1,000,000-iteration safety cap
    ...
end
```

`break`/`continue` are lint errors outside a loop and never cross a
function-call boundary.

**Error handling**:

```
try:
    set n = int(user_input)
except err:
    print "not a number: {err}"
    set n = 0
end
```

`try` catches a NyxScript runtime error (`RuntimeScriptError`) raised
anywhere in its body — a bad conversion, a missing dict key, a failed
`assert`/`fail`/`run`, etc. — and binds `err` (a string, the error
message) for the `except` block only. Never catches `break`/`continue`/
`return`. A variable the `try` body sets is only usable after the whole
`try`/`except` if the `except` branch always exits (`return`/`fail`/
`break`/`continue`) — same rule the linter applies to `if`/`else`.

**Running scan modules**: `run MODULE TARGET [as VAR]`. `MODULE` is one
of `audit`, `dns`, `tls`, `http`, `network.discover`, `network.scan`,
`recon.subdomains`. `VAR` holds a `list[ModuleResult]`.

```
run audit "example.com" as result
foreach r in result:
    print "{r.module}: {len(r.findings)} finding(s)"
end
```

**Saving reports**: `save VAR to "path.ext"` — `VAR` must hold scan
results; format is inferred from extension (`.json`, `.md`/`.markdown`,
`.html`/`.htm`, else JSON).

**Functions**:

```
func square(x):
    "Returns x squared."     # docstring: bare string as first statement, no-op
    return x * x
end

print square(5)   # 25
```

Recursion works (200-frame cap). Argument count is checked at call time.
`return`/`break`/`continue` outside valid context are lint errors.

**Lambdas and higher-order functions**: `lambda(params): expr` is a
single-expression anonymous function value. Unlike `func`, **a lambda
captures a snapshot of every variable visible where it's defined**
(locals and globals, frozen at creation time) — so a lambda built inside
a `func` body can see that function's own parameters:

```
func find_big(items, threshold):
    return filter(items, lambda(x): x > threshold)
end
```

`map(list, fn)`, `filter(list, fn)`, `sort_by(list, fn)`, and
`reduce(list, fn, initial)` take a function value (a lambda, or a
variable holding one) and call it per item — these aren't plain
synchronous builtins, they're handled specially by the interpreter, but
they lint and call exactly like one.

**Slicing**: `list[1:3]`, `list[:2]`, `list[3:]`, `list[:]`, and the
same on strings — Python semantics, either bound optional. Not
assignable (`set x[1:3] = ...` is a parse error) and not valid on dicts.

**Libraries — `import`**: any `.nyx` file can be imported as a
namespaced bag of functions/constants.

```
import "mathlib.nyx" as math

print math.square(4)
print math.version
```

Import paths resolve relative to the *running script's* directory, not
the importer's. Circular imports are detected and rejected (depth cap
20). The linter registers the alias as defined but does not follow the
import cross-file — a missing member is caught at run time, not lint
time.

**Built-ins** (pure, no I/O, safe anywhere): `len`, `range`, `upper`,
`lower`, `strip`, `split`, `join`, `contains`, `str`, `int`, `float`,
`abs`, `round`, `sorted`, `reversed`, `min`, `max`, `sum`, `type_of`,
`keys`, `values`, `items`, `get`, `replace`, `starts_with`, `ends_with`,
`find`, `zip`, `parse_json`, `to_json`, `now`, `to_iso8601`, `sha256`,
`md5`, `base64_encode`, `base64_decode`, `random`. No `%` operator —
use `mod(a, b)` from `lib/math.nyx` (see below). No `**` operator —
see `lib/time.nyx`'s `backoff_delay` for exponentiation via repeated
doubling. `parse_json` errors on `null` (no way to represent it — same
reason `get()`'s default is mandatory). `base64_decode` only succeeds
on valid UTF-8 text (no bytes type to hold arbitrary binary otherwise).
`random()` is `[0.0, 1.0)`, the other non-deterministic builtin besides
`now()`. `range()`/`*` (sequence repetition) are capped at 1,000,000
resulting items.

**Byte-level builtins** (pure, no `--unsafe` needed) — NyxScript has no
bytes type, so binary data is a list of ints 0-255: `bytes_from_hex(s)`,
`bytes_to_hex(list)`, `bytes_from_string(s)`, `bytes_to_string(list)`,
`pack_uint16(n)`/`pack_uint32(n)` (→ list, big-endian/network order),
`unpack_uint16(list)`/`unpack_uint32(list)` (→ int). Use these to build/
parse messages for `socket.*` below.

**Regex builtins** — `regex_match(text, pattern)`,
`regex_find(text, pattern, default)`, `regex_find_all(text, pattern)`,
`regex_replace(text, pattern, replacement)`. Run in a sandboxed worker
process with a 1-second timeout (catastrophic-backtracking patterns get
killed, not left to hang). Write patterns as raw strings —
`regex_match(text, r"\d{2,4}")` — so quantifiers like `{2,4}` and
escapes like `\d`/`\w`/`\s` don't need any special handling; an ordinary
`"..."` string would need `{{2,4}}` (doubled braces) instead, since it
interpolates. `lib/regex.nyx` (below) writes all of its patterns as raw
strings for this reason.

**Standard library — `lib/`** (all written in NyxScript itself, `import
"lib/NAME.nyx" as alias` same as any other library):
`math.nyx` (`mod`, `clamp`, `mean`, `median`, `gcd`, `is_prime`),
`dict.nyx` (`merge`, `pick`, `invert`, `from_pairs`), `validate.nyx`
(`is_valid_port`, `is_valid_ipv4`, `is_valid_domain`), `collection.nyx`
(`unique`, `chunk`, `flatten`, `partition`, `take`, `drop`, `sum_by`),
`strings.nyx` (`title_case`, `truncate`), `finding.nyx`
(`count_by_severity`, `total_findings`, `worst_severity`,
`summary_line`), `report.nyx` (`severity_breakdown`, `print_summary`),
`lambdas.nyx` (`identity`, `constant`, `compose`, `pipe`, `flip`,
`partial`, `negate`, `any_of`, `all_of`, `none_of`, `count_where`,
`find_where`, `flat_map`, `group_by`, `times` — combinators built on
`map`/`filter`/`sort_by`/`reduce`), `set.nyx` (`union`, `intersect`,
`difference`, `symmetric_difference`, `is_subset`, `is_disjoint`),
`net.nyx` (`host_from_target`, `port_from_target`, `octets`,
`is_private_ipv4`), `format.nyx` (`pad_left`, `pad_right`,
`human_bytes`, `human_duration`, `bullet_list`), `time.nyx` (`elapsed`,
`is_older_than`, `humanize`, `now_iso`, `backoff_delay`, `time_it`),
`asset.nyx` (`by_kind`, `kinds`, `identifiers`, `count_by_kind`,
`group_by_kind`, `attr`, `has_attr`, `has_source`, `source_or`,
`summary_line` — for the `.assets` a module like `network.discover`
attaches to its result), `hash.nyx` (`short_hash`, `fingerprint`,
`has_changed` — fingerprinting/dedup, not password hashing), `csv.nyx`
(`parse_csv`, `to_csv` — quote-aware, no `--unsafe` needed), `regex.nyx`
(`extract_ips`, `extract_emails`, `extract_urls`, `matches_any`),
`random.nyx` (`random_int`, `choice`, `shuffle`, `sample`, `jitter` —
`shuffle`/`sample` don't mutate their input), `text.nyx` (`capitalize`,
`center`, `reverse`, `contains_ignore_case`, `count_occurrences`,
`is_blank`, `words`, `lines`, `slugify` — the native `*` operator
already repeats a string, so there's no separate `repeat()`),
`table.nyx` (`render(headers, rows)` — an aligned plain-text table as a
string, for `print`/`save`; distinct from the interactive `ui.table`,
which needs a live terminal), `ftp.nyx` (`connect`, `login`/
`anonymous_login`, `pwd`, `cwd`, `set_binary_mode`/`set_ascii_mode`,
`list`, `retr`, `quit` — a minimal read-oriented FTP client built on
`socket.*`, requires `--unsafe` transitively; connection objects are
plain dicts, pass the same one into every call).
Reach for these before reimplementing — e.g. don't hand-roll a dict merge
when `dict.merge(a, b)` already exists, or a retry loop when
`time.backoff_delay` already does exponential backoff.

**Full worked examples**: see the
[NyxScript Cookbook wiki page](https://github.com/ivnovomi/nyxor/wiki/NyxScript-Cookbook)
for seven runnable scripts combining several of these modules (batch
CSV export, hash-based change detection, retry with backoff, IOC
extraction, grouping findings by severity, an interactive triage flow).

**Interactive UI — `ui.*`** (works unchanged from both CLI and TUI):
`ui.confirm(msg) -> bool`, `ui.input(prompt) -> string`,
`ui.select(prompt, options) -> string`, `ui.table(headers, rows)`,
`ui.banner(title)`, `ui.status(msg)`.

**Diagnostics**: `print EXPR`, `assert EXPR[, "message"]`, `fail
"message"`, `sleep SECONDS`.

**Escape hatches — `python:` / `pip` / `socket.*`**: disabled by
default, refuse to run without `--unsafe` (CLI) or the MCP
`run_nyxscript` tool (which *never* enables `--unsafe` — an MCP call
can't get arbitrary code execution or arbitrary-host network access
through this path, by design). Don't reach for these unless the task
genuinely needs them; prefer the built-ins and audited scan modules
(`run dns`/`run tls`/`run http`/`network.discover`/`network.scan`)
first — `socket.*` in particular is for when you need to speak a
protocol none of those cover (a custom text protocol, a non-HTTP
service), not a replacement for them.

```
unsafe
set h = socket.connect("example.com", 80, "tcp", 5.0)
socket.send(h, "GET / HTTP/1.0\r\n\r\n")
print socket.recv_text(h, 4096, 5.0)
socket.close(h)
```

`socket.connect(host, port[, protocol][, timeout])` → handle (protocol
`"tcp"`/`"udp"`), `socket.send(handle, data)` (string or list of byte
values), `socket.recv(handle[, max_bytes][, timeout])` → list of byte
values, `socket.recv_text(...)` → UTF-8 string, `socket.close(handle)`.
Every blocking call has an explicit timeout; a one-shot run (`nyx
script run`, the TUI's Run button) auto-closes connections a script
left open.

A script can also self-enable all three with a bare `unsafe` statement
(typically the first line), instead of the caller passing `--unsafe`:

```
unsafe
python:
    result = 6 * 7
end
print result
```

`nyx script lint` surfaces `unsafe` and every `socket.*` call as a
warning (doesn't block execution) so they stay visible when reviewing
a script someone else wrote. None of the three are reachable via the
MCP `run_nyxscript` tool regardless of what the script itself
contains.

```
pip "requests"

python:
    import requests
    status = requests.get(f"https://{target}/robots.txt").status_code
end

print "status: {status}"
```

## Common mistakes to avoid

- Forgetting `end` to close a block — every `if`/`foreach`/`while`/`func`
  needs one, indentation is cosmetic only.
- Writing `x.y = z` — attribute access is read-only; there's no field
  assignment on scan results.
- Assuming a `func` has closures — it can't see a caller's local
  variables, only its own locals and its *defining* scope's globals.
  Lambdas are the exception: they capture everything visible at creation.
- Writing `set x[1:3] = ...` — slice assignment doesn't exist, only
  single-index assignment (`set x[1] = ...`).
- Reaching for `python:`/`pip` for things the built-ins already cover
  (string ops, list ops, math) — adds an unsafe flag for no reason.
- Forgetting that `run`'s module names use dotted syntax
  (`network.discover`) but these are single tokens, not attribute access.
- Using `get(d, key)` with only 2 arguments — the default is mandatory
  (3 args), since there's no `null` to silently fall back to.
- Reinventing a dict/math helper that already exists in `lib/` (above).

## Full grammar and worked examples

See [docs/nyxscript.md](../../../docs/nyxscript.md) in the repo root for
the complete EBNF grammar, the full built-in/`ui.*` tables, and more
worked examples (fibonacci, a full audit-and-report script, a library
with sibling calls).
