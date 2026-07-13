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

## The `⚠️ {{`/`}}` regex gotcha

Every NyxScript string literal runs through `{expr}` interpolation —
including regex patterns. A quantifier like `{1,3}` or `{2,}` looks
exactly like an interpolation span and gets silently evaluated/mangled
unless you double the braces:

```
print regex_match("aaa", "a{2,3}")     # WRONG — {2,3} gets interpolated away
print regex_match("aaa", "a{{2,3}}")   # right — matches
```

`lib/regex.nyx` (below) writes all of its own patterns this way for
exactly this reason.

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
