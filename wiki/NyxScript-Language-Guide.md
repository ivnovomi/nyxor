# NyxScript Language Guide

NyxScript is a small, intentionally safe language for batch-driving
NYXOR modules — its own lexer, recursive-descent parser, AST,
tree-walking interpreter, and a standalone static linter, living
entirely inside NYXOR (`src/nyxor/core/scripting/`). No `eval`, no
arbitrary code execution by default.

This page is a practical tour. For the complete formal grammar
(EBNF-style), every statement form, and edge cases, see
[`docs/nyxscript.md`](https://github.com/ivnovomi/nyxor/blob/main/docs/nyxscript.md)
in the repo. For every function available, see
[NyxScript Standard Library Reference](NyxScript-Standard-Library-Reference).

## The shape of a script

Statements are newline-terminated; blocks are `end`-delimited (no
significant indentation, though the CLI/TUI auto-indent as if there
were):

```
if x > 0:
    print "positive"
end
```

Comments start with `#` and run to end of line.

## Types

int, float, string, bool, list, dict — **no null**. Every place another
language might reach for `null`/`None` (a missing dict key, a
not-found regex match), NyxScript requires an explicit default argument
instead (`get(d, key, default)`, `regex_find(text, pattern, default)`).

```
set n = 42
set pi = 3.14
set name = "example.com"
set found = true
set items = [1, 2, 3]
set config = {"host": "example.com", "port": 443}
```

## Variables

`set NAME = EXPR`. One global scope plus one local scope per active
function call — `func` does **not** close over the enclosing scope (no
closures); `lambda` does capture a snapshot of the enclosing scope at
creation time (see [Lambdas](#lambdas--higher-order-functions) below).

## Operators

Arithmetic `+ - * /`, comparison `== != < <= > >=`, logical `and or
not`. No `%` — use `mod(a, b)` from `lib/math.nyx`. No `**` — see
`lib/time.nyx`'s `backoff_delay` for how to do exponentiation via
repeated multiplication instead.

`+` on two strings concatenates; on two lists concatenates. `*` on a
list/string and an int repeats it (`[1, 2] * 3` → `[1, 2, 1, 2, 1, 2]`)
— capped at 1,000,000 resulting items, since two tiny operands can
otherwise request an arbitrarily large allocation.

Dot access reads a field on a value returned from a scan (`r.severity`,
`asset.kind`) or a member of an imported module (`math.mod(...)`).

## String interpolation

`"{expr}"` embeds any expression's value; `{{`/`}}` escape a literal
brace:

```
set target = "example.com"
print "Auditing {target}... ({len(target)} chars)"
print "literal braces: {{not interpolated}}"
```

**Gotcha**: this applies to *every* string literal, including regex
patterns passed to `regex_match`/etc. — a quantifier like `{1,3}` needs
doubled braces (`{{1,3}}`) or it gets silently mangled. See
[NyxScript Standard Library Reference § the regex gotcha](NyxScript-Standard-Library-Reference#the-️-gotcha).

## Dicts

```
set d = {"host": "example.com", "port": 443}
set d["port"] = 8443              # in-place mutation
print get(d, "missing", "n/a")    # mandatory default — no null to fall back to
foreach k in keys(d):
    print k + " = " + str(d[k])
end
```

## Slicing

Python-style, on lists and strings only (not dicts), no slice
assignment:

```
set nums = [1, 2, 3, 4, 5]
print nums[1:3]     # [2, 3]
print nums[:2]      # [1, 2]
print nums[3:]      # [4, 5]
print "hello"[0:3]  # hel
```

## Control flow

```
if x > 10:
    print "big"
else:
    print "small"
end

foreach item in [1, 2, 3]:
    if item == 2:
        continue
    end
    print item
end

set i = 0
while i < 5:
    set i = i + 1
end
```

`while` is capped at 1,000,000 iterations (raises a script error past
that — almost certainly an infinite loop, not a legitimate use case).
`foreach` has no separate cap since it iterates a list that's already
materialized in memory.

## Error handling

```
try:
    set n = int(user_input)
except err:
    print "not a number: {err}"
end
```

`try`/`except` catches script-level runtime errors (`RuntimeScriptError`
— a bad argument, a failed conversion, a `run` that errored) — not
`break`/`continue`/`return`, which are control flow, not errors. The
linter tracks definite-assignment across `try`/`except` branches the
same way it does for `if`/`else`.

## Running scan modules

```
run audit "example.com" as results
run dns "example.com" as dns_result
run network.discover "192.168.1.0/24" as hosts
```

`MODULE` is one of: `audit`, `dns`, `tls`, `http`, `network.discover`,
`network.scan`, `recon` — each wraps the exact same `async def run_*()`
coroutine the CLI itself calls (see [Architecture](Architecture)). The
`as VAR` clause is optional if you don't need the result. Every module
returns a `list` of `ModuleResult`-like objects (`.module`, `.target`,
`.findings`, `.assets`, `.errors`) except `dns`/`tls`/`http`, which
return a single result directly (not wrapped in a list) — check the
module's own docs if unsure, or just `print type_of(results)`.

## Saving reports

```
save results to "report.json"    # format inferred from extension
save results to "report.sarif"   # .json/.md/.markdown/.html/.htm/.sarif — else JSON
```

The destination path is resolved relative to the script's working
directory and **cannot** escape it (absolute paths and `../` are
rejected) — this holds even without `--unsafe`, since `save` is meant to
stay inside the "just makes requests to the targets you name" safety
model.

## Functions

```
func greet(name):
    "Optional docstring, shown by hover in the language server."
    return "hello, " + name
end

print greet("world")
```

Arity is checked at call time (wrong argument count is a script error,
not silent). Recursion is capped at 200 stack frames. `func` does not
close over the enclosing scope — pass what you need as parameters.

## Lambdas & higher-order functions

```
set square = lambda(x): x * x
print square(5)               # 25
print map([1, 2, 3], square)  # [1, 4, 9]
```

Unlike `func`, a `lambda` captures a snapshot of whatever scope it was
created in — including a locally-scoped variable inside an enclosing
`func`:

```
func find_big(items, threshold):
    return filter(items, lambda(x): x > threshold)
end
```

`map`/`filter`/`sort_by`/`reduce` are the native higher-order functions
— see [Standard Library Reference § Higher-order functions](NyxScript-Standard-Library-Reference#higher-order-functions).
`lib/lambdas.nyx` adds `compose`/`pipe`/`partial`/`flip`/predicate
combinators/etc. built on top.

## Imports — the standard library and your own libraries

```
import "lib/validate.nyx" as validate
import "my_helpers.nyx" as helpers

print validate.is_valid_domain("example.com")
```

Import paths are always resolved relative to the *running script's
working directory* — never relative to the importing file's own
location. Circular imports are detected and rejected; import depth is
capped at 20. See [NyxScript Standard Library Reference](NyxScript-Standard-Library-Reference)
for every shipped `lib/*.nyx` module.

## Diagnostics

```
print "a line of output"
assert x > 0, "x must be positive"
fail "unconditional abort"
sleep 2.5
```

## Interactive prompts — `ui.*`

```
if ui.confirm("Proceed with the scan?"):
    set target = ui.input("Target domain: ")
    ui.status("Auditing {target}...")
    run audit target as results
    ui.table(["severity", "title"], map(results[0].findings, lambda(f): [f.severity, f.title]))
end
```

Works identically under `nyx script run` (blocks the terminal normally)
and inside `nyx tui`'s Script tab (temporarily suspends the dashboard) —
see [Standard Library Reference § ui.*](NyxScript-Standard-Library-Reference#ui--interactive-prompts).

## The REPL

```
$ nyx script repl
nyx> set d = {}
nyx> set d["found"] = 0
nyx> func bump():
...     set d["found"] = d["found"] + 1
... end
nyx> bump()
nyx> print d
{found: 1}
```

Variables and functions persist across lines; multi-line blocks
(`if`/`foreach`/`while`/`func`/`try`/`python:`) are detected and only
run once their matching `end` arrives.

## Escape hatches: `python:` and `pip`

Disabled unless you opt in (`--unsafe` on `nyx script run`/`repl`, the
Unsafe switch in `nyx tui`) — and never reachable through the MCP server
at all:

```
pip "cowsay"
python:
    import cowsay
    cowsay.cow(f"hello from {target}")
end
```

`python:` runs as real Python with direct read/write access to the
script's variables; `pip` installs a package into the current
environment. Both require `--unsafe` because they step outside
NyxScript's safety model entirely — treat a script using them like any
other executable. See [Security § --unsafe gating](Security#unsafe-gating).

## The linter

`nyx script lint file.nyx` (or automatically before `nyx script run`,
unless `--no-lint`) catches, with zero network access:

- Undefined variables — including inside `"{...}"` interpolation, across
  `if`/`foreach`/`try`/`except` branches
- Unknown `run` modules, with a "did you mean" suggestion
- Empty control-flow bodies

The language server (`nyx script lsp`) runs the same linter live as you
type — see [Installation § Editor support](Installation#editor-support).

## Resource limits

All of these raise a normal script error (catchable with `try`/`except`)
rather than hanging or crashing the process:

| Limit | Value | Guards against |
|---|---|---|
| Call stack depth | 200 frames | Infinite/runaway recursion |
| `while` iterations | 1,000,000 | Infinite loops |
| `range()` result size | 1,000,000 items | `range(10**12)` allocating a huge list in one call |
| `*` sequence repetition | 1,000,000 items | `"x" * 10**12` allocating a huge string/list from tiny operands |
| Import depth | 20 | Runaway import chains |
| Regex evaluation | 1 second wall clock | Catastrophic-backtracking patterns |
| Regex input length | 100,000 characters | Large-input regex cost |

See [Security](Security) for the reasoning behind each of these,
especially the regex one — it took two failed designs to get right.
