# NyxScript language reference

NyxScript is the automation language that ships inside NYXOR. It has its
own lexer, recursive-descent parser, AST, tree-walking interpreter, and a
standalone static linter — not a config format, not a YAML dialect, an
actual small language. This document is the full reference: every
statement, every expression form, functions, imports/libraries, the
interactive `ui.*` module, and the two escape hatches.

Run `nyx script new myfile.nyx` to get a starter file, `nyx script lint
myfile.nyx` to check one without running it, `nyx script run myfile.nyx`
to execute it, and `nyx script repl` for an interactive prompt where
variables and functions persist between lines. Every editor with an LSP
client (VS Code, Neovim, Helix, ...) gets diagnostics/completion/hover for
free from `nyx script lsp` — see
[plugin-development.md](plugin-development.md) if you're embedding
NyxScript somewhere new.

## Contents

- [The shape of a script](#the-shape-of-a-script)
- [Types and literals](#types-and-literals)
- [Variables](#variables)
- [Expressions and operators](#expressions-and-operators)
- [Dicts](#dicts)
- [Slicing](#slicing)
- [String interpolation](#string-interpolation)
- [Control flow](#control-flow)
- [Error handling — `try`/`except`](#error-handling--tryexcept)
- [Running scan modules](#running-scan-modules-run)
- [Saving reports](#saving-reports-save)
- [Functions](#functions)
- [Lambdas and higher-order functions](#lambdas-and-higher-order-functions)
- [Libraries — `import`](#libraries--import)
- [The standard library — `lib/`](#the-standard-library--lib)
- [Built-in functions](#built-in-functions)
- [Interactive UI — `ui.*`](#interactive-ui--ui)
- [Diagnostics — `print` / `assert` / `fail` / `sleep`](#diagnostics)
- [The REPL](#the-repl)
- [Escape hatches: `python:` and `pip`](#escape-hatches-python-and-pip)
- [The linter](#the-linter)
- [Errors](#errors)
- [Full grammar](#full-grammar)

## The shape of a script

A script is a sequence of statements, one per line (blank lines and `#
comments` are ignored). Blocks (`if`, `foreach`, `while`, `func`) are
closed with `end`, not indentation — indentation is cosmetic.

```
set target = "example.com"

if target != "":
    run audit target as result
    save result to "report.html"
end
```

## Types and literals

| Type | Literal syntax | Notes |
|---|---|---|
| string | `"double"` or `'single'` quotes | supports `\n \t \\ \" \'` escapes and `{expr}` interpolation |
| number | `42`, `3.14` | `int` if no `.`, otherwise `float` |
| boolean | `true`, `false` | |
| list | `[1, 2, 3]`, `["a", "b"]` | heterogeneous, indexable |
| dict | `{"a": 1, "b": 2}`, `{}` | string/number/bool keys, indexable — see [Dicts](#dicts) |

There is no `null`/`none` literal — an undefined variable is a lint/runtime
error, not a value.

## Variables

```
set name = "example.com"
set count = 0
set items = [1, 2, 3]
```

`set` both declares and reassigns — there's no separate declaration form.
Referencing a variable that hasn't been `set` yet (on any reachable code
path) is a **lint error**, and an interpreter error if it somehow slips
past the linter (e.g. `nyx script run --no-lint`).

**Scoping is intentionally simple — no closures.** There is exactly one
global scope, plus, while a function call is active, exactly one local
scope for it:

- `set` inside a function body always writes to that function's local
  scope.
- Reading a variable checks the local scope first, then falls through to
  global.
- A function's global fallback is the scope it was *defined* in, not the
  scope it was *called* from — see [Libraries](#libraries--import) for why
  that matters.

## Expressions and operators

Precedence, loosest to tightest:

```
or  →  and  →  not  →  == != < <= > >=  →  + -  →  * /  →  unary -  →  primary
```

Primaries: literals, `[...]` list literals, `(...)` parenthesized
expressions, variable references, indexing (`list[0]`), attribute access
(`value.field`), and calls (`fn(a, b)`) — chainable, so
`result[0].findings[0].severity` works.

```
set ok = 1 + 2 * 3 == 7 and not false
set last = items[len(items) - 1]
```

`.field` reads a field off whatever's on the left: a member of an
imported [library](#libraries--import) (`math.version`), or — most
usefully — a field on a scan result object returned by `run`
(`ModuleResult`/`Finding` are plain Pydantic models, so every one of their
fields is readable this way):

```
run dns "example.com" as result
foreach r in result:
    print "{r.module}: {len(r.findings)} finding(s)"
end
print result[0].findings[0].severity   # "info", "medium", ...
```

There's no way to *write* through `.field` (no `x.y = z`) — scan results
are read-only from NyxScript, matching NYXOR's "observe, don't mutate"
design everywhere else.

`+` on two strings concatenates; `+`/`-`/`*`/`/` on mismatched types raise
a runtime error naming both types involved (`cannot apply '+' to string
and int`) rather than silently coercing. There's no `%` operator — use
`mod(a, b)` from [`lib/math.nyx`](#the-standard-library--lib).

## Dicts

```
set d = {"host": "example.com", "port": 443}
print d["host"]                # example.com
set d["port"] = 8443           # mutates in place
```

`set CONTAINER[index]... = expr` mutates a list or dict in place —
the only form of mutation-through-indexing NyxScript has (there's still
no way to *write* through `.field`; see below). It chains, so
`set d["a"]["b"] = 1` works on a dict of dicts.

Keys are usually strings but can be any hashable value (number, bool);
building a dict with an unhashable key (a list or another dict) is a
runtime error. Reading a missing key with `d["missing"]` is a runtime
error too — use `get(d, "missing", default)` to avoid one. See
[Built-in functions](#built-in-functions) for `keys`/`values`/`items`/`get`.

Index assignment is unrelated to `.field` access above — it mutates a
plain list/dict *value* the script itself created, not a scan result
(those stay read-only).

## Slicing

Lists and strings support Python-style slicing; either bound can be
omitted:

```
set nums = [1, 2, 3, 4, 5]
print nums[1:3]     # [2, 3]
print nums[:2]      # [1, 2]
print nums[3:]      # [4, 5]
print nums[:]       # [1, 2, 3, 4, 5] — a shallow copy
print "hello"[1:4]  # ell
```

Slicing a dict is a runtime error — there's no ordering to slice by
beyond insertion order, and `pick()`/`{k: v for ...}`-style filtering
doesn't map cleanly onto a `start:stop` pair. Slice bounds can't be
assigned to (`set nums[1:3] = ...` is a parse error) — only single-index
assignment (`set nums[1] = ...`) is supported.

## String interpolation

`{expr}` inside a string literal is replaced with that expression's value
(itself full NyxScript, not just a bare variable name); `{{` and `}}` are
literal braces.

```
set grade = "A+"
print "Result: {grade} ({1 + 1} findings)"   # Result: A+ (2 findings)
print "literal braces: {{not interpolated}}"
```

## Control flow

```
if EXPR:
    ...
else:
    ...
end

foreach VAR in LIST_EXPR:
    ...
end

while EXPR:
    ...
end
```

`break` exits the nearest enclosing `foreach`/`while`; `continue` skips to
its next iteration. Both are lint errors outside a loop, and neither
crosses a function-call boundary (a stray `break` inside a function whose
*caller* happens to be in a loop does not break the caller's loop — it's a
runtime error naming the function).

`while` has a 1,000,000-iteration safety cap: a runaway `while true:`
raises a clear runtime error instead of hanging a CI job forever.

## Error handling — `try`/`except`

```
try:
    set port = int(ui.input("Port:"))
except err:
    print "not a number: {err}"
    set port = 443
end
```

`try` runs its body; if a statement inside raises a NyxScript runtime
error (a bad type conversion, a missing dict key, a failed `run`, an
`assert`/`fail`, ...), execution jumps straight to `except VAR:` with
`VAR` bound to the error's message (a string) for the duration of that
block only. If the body succeeds, `except` never runs. `break`/`continue`/
`return` inside the body still propagate normally — `try` only catches
NyxScript's own `RuntimeScriptError`, not control flow.

A variable `try`'s body sets is only guaranteed defined afterward if the
`except` branch can't fall through past it (i.e. it always
`return`s/`fail`s/`break`s/`continue`s) — the linter checks this the same
way it checks `if`/`else` branches.

## Running scan modules: `run`

```
run MODULE TARGET [as VAR]
```

`MODULE` is one of `audit`, `dns`, `tls`, `http`, `network.discover`,
`network.scan` (see `core/scripting/stdlib.py`'s `MODULE_RUNNERS` — this
is a third front-end over the exact same `run_*` coroutines the CLI, TUI,
and REST API use, never a reimplementation). `VAR`, if given, holds a
`list[ModuleResult]` you can `save`, iterate with `foreach`, or inspect.

```
run audit "example.com" as result
foreach r in result:
    print "{r.module}: {len(r.findings)} finding(s)"
end
```

## Saving reports: `save`

```
save VAR to "path.ext"
```

`VAR` must hold scan results (from `run ... as VAR`). The output format is
inferred from the extension: `.json`, `.md`/`.markdown`, `.html`/`.htm`
(anything else defaults to JSON).

## Functions

```
func NAME(param, param, ...):
    ...
    return EXPR   # optional; a function with no `return` yields nothing
end
```

Calls are ordinary expressions: `NAME(arg, arg, ...)`. Functions are
first-class-ish values (a `func` statement stores a callable value under
its name, just like `set` stores any other value) but there's no lambda
syntax and no passing a function as an argument in this version.

```
func square(x):
    return x * x
end

func fib(n):
    if n < 2:
        return n
    end
    return fib(n - 1) + fib(n - 2)
end

print square(5)   # 25
print fib(10)     # 55
```

Recursion works (call-stack capped at 200 frames — a clear "possible
infinite recursion" error beyond that, not a Python `RecursionError`).
Argument count is checked at call time: `'square' expects 1 argument(s),
got 2`.

`return`/`break`/`continue` outside their valid context are **lint
errors**, caught before anything runs.

### Docstrings

A bare string literal as a function's first statement is a docstring —
purely documentation, a no-op at run time:

```
func square(x):
    "Returns x squared."
    return x * x
end
```

Editor tooling picks these up: `nyx script lsp` shows the signature and
docstring on hover (over the call, not just the definition — including
calls into an imported library, e.g. hovering `math.square(4)` shows
`math.nyx`'s docstring for `square`), and jumps straight to the `func`
line on go-to-definition. The TUI's editor highlights a docstring line
differently from an ordinary string.

## Lambdas and higher-order functions

```
set square = lambda(x): x * x
print square(5)   # 25
```

`lambda(params): expr` is a single-expression, anonymous function value —
no `end`, the whole thing is one expression. Unlike `func`, **a lambda
captures a snapshot of every variable visible where it's defined** (both
locals and globals, frozen at definition time, not a live reference) —
that's what makes this work:

```
func find_big(items, threshold):
    return filter(items, lambda(x): x > threshold)
end

print find_big([1, 2, 3, 4, 5], 3)   # [4, 5]
```

`threshold` is `find_big`'s own local parameter; the lambda passed to
`filter` still sees it, because it captured it when it was created —
`func` bodies can't do this (see [Functions](#functions) above).

Four built-ins take a list and a function value (a lambda, or a plain
variable that holds one) and call it per item:

| Function | Signature | Returns |
|---|---|---|
| `map` | `map(list, fn)` | a new list of `fn(item)` for each item |
| `filter` | `filter(list, fn)` | items where `fn(item)` is truthy |
| `sort_by` | `sort_by(list, fn)` | the list sorted by `fn(item)` as the key |
| `reduce` | `reduce(list, fn, initial)` | folds: `acc = fn(acc, item)` for each item, starting from `initial` |

```
set nums = [1, 2, 3, 4]
print map(nums, lambda(x): x * 2)              # [2, 4, 6, 8]
print filter(nums, lambda(x): x > 2)            # [3, 4]
print reduce(nums, lambda(acc, x): acc + x, 0)  # 10
```

## Libraries — `import`

Any `.nyx` file can be imported into another as a namespaced bag of
functions and constants — this is how you write and share NyxScript
*libraries*, not just one-off scripts.

`mathlib.nyx`:

```
func square(x):
    return x * x
end

func cube(x):
    return x * square(x)   # sibling calls resolve against mathlib's own
end                        # scope, regardless of who imports it

set version = "1.0"
```

`main.nyx`:

```
import "mathlib.nyx" as math

print math.square(4)     # 16
print math.cube(3)       # 27
print math.version       # 1.0
```

Import paths are resolved relative to the *running script's* directory
(`--base-dir`/`Path.cwd()`), not the importing file's own directory, so
nested libraries importing other libraries all resolve against the same
root. Circular imports (`a.nyx` imports `b.nyx` imports `a.nyx`) are
detected and rejected with a clear error rather than hanging or
stack-overflowing; import depth is capped at 20.

The linter registers the alias as a defined name so `lib.member(...)`
doesn't false-positive on the module reference itself, but it does not
follow the import cross-file — a genuinely missing member is caught by
the interpreter at run time, not by `nyx script lint`.

## The standard library — `lib/`

NYXOR ships a small standard library, written entirely in NyxScript
itself, at [`lib/`](../lib) in the repo root — import it the same way as
any other `.nyx` file:

```
import "lib/math.nyx" as math
import "lib/dict.nyx" as dict
import "lib/validate.nyx" as validate
import "lib/collection.nyx" as collection
import "lib/strings.nyx" as strings
import "lib/finding.nyx" as findings
import "lib/report.nyx" as report

print math.clamp(150, 0, 100)                    # 100
print validate.is_valid_domain("example.com")    # true
```

| File | Functions |
|---|---|
| `math.nyx` | `mod(a, b)`, `clamp(x, lo, hi)`, `mean(list)`, `median(list)`, `gcd(a, b)`, `is_prime(n)` |
| `dict.nyx` | `merge(a, b)`, `pick(d, keys)`, `invert(d)`, `from_pairs(pairs)` |
| `validate.nyx` | `is_valid_port(v)`, `is_valid_ipv4(s)`, `is_valid_domain(s)` — conservative sanity checks, not full RFC parsers |
| `collection.nyx` | `unique(list)`, `chunk(list, size)` |
| `strings.nyx` | `title_case(s)`, `truncate(s, max_len)` |
| `finding.nyx` | `count_by_severity(results, sev)`, `total_findings(results)`, `worst_severity(results)`, `summary_line(results, target)` |
| `report.nyx` | `severity_breakdown(results)` (a dict of `severity -> count`), `print_summary(results, target)` (prints the summary line plus a `ui.table` breakdown) |

## Built-in functions

Pure, synchronous, no I/O — safe to call anywhere, no `--unsafe` needed.

| Function | Signature | Notes |
|---|---|---|
| `len` | `len(x)` | length of a list or string |
| `range` | `range(n)` / `range(a, b)` / `range(a, b, step)` | list of ints |
| `upper` / `lower` | `upper(s)` / `lower(s)` | |
| `strip` | `strip(s)` | trims whitespace |
| `split` | `split(s, sep)` | → list of strings |
| `join` | `join(list, sep)` | → string |
| `contains` | `contains(collection, item)` | membership test |
| `str` / `int` / `float` | `str(x)` etc. | conversions |
| `abs` / `round` | `abs(x)` / `round(x[, digits])` | |
| `sorted` / `reversed` | `sorted(list)` / `reversed(list)` | new list |
| `min` / `max` / `sum` | `min(list)` or `min(a, b, ...)`; `sum(list)` | |
| `type_of` | `type_of(x)` | `"string"`, `"int"`, `"float"`, `"bool"`, `"list"`, `"dict"` |
| `keys` / `values` | `keys(d)` / `values(d)` | → list, in insertion order |
| `items` | `items(d)` | → list of `[key, value]` pairs |
| `get` | `get(d, key, default)` | dict lookup with a mandatory default (no `null` to fall back to otherwise) |
| `replace` | `replace(s, old, new)` | |
| `starts_with` / `ends_with` | `starts_with(s, prefix)` / `ends_with(s, suffix)` | |
| `find` | `find(s, needle)` | index of the first match, or `-1` |
| `zip` | `zip(list, list)` | → list of `[a, b]` pairs, stops at the shorter list |
| `parse_json` | `parse_json(s)` | JSON → NyxScript value. Errors on `null` (no way to represent it) |
| `to_json` | `to_json(value)` | NyxScript value → JSON string |

See [Lambdas and higher-order functions](#lambdas-and-higher-order-functions)
for `map`/`filter`/`sort_by`/`reduce`, which take a function value and so
aren't plain synchronous builtins like the ones above.

## Interactive UI — `ui.*`

Not a bundled GUI toolkit — real terminal interactivity, built on Rich
(already a NYXOR dependency everywhere). The same script works unchanged
from both front ends:

- `nyx script run` — the CLI owns the terminal, so a prompt just blocks
  normally.
- `nyx tui` — Textual owns the terminal instead; a `ui.*` call
  transparently wraps itself in `App.suspend()`, which hands the real
  terminal back for exactly as long as the prompt needs it, then restores
  the TUI. The script doesn't know or care which front end is running it.

| Function | Signature | Returns |
|---|---|---|
| `ui.confirm` | `ui.confirm("Proceed?")` | `bool` |
| `ui.input` | `ui.input("Target:")` | `string` |
| `ui.select` | `ui.select("Pick one:", ["a", "b", "c"])` | `string`, one of the options |
| `ui.table` | `ui.table(["col1", "col2"], [["a","b"], ["c","d"]])` | prints a table, no return value |
| `ui.banner` | `ui.banner("Section title")` | prints a rule, no return value |
| `ui.status` | `ui.status("Scanning...")` | prints a status line, no return value |

```
if ui.confirm("Audit {target}?"):
    set label = ui.input("Report label:")
    run audit target as result

    set rows = []
    foreach r in result:
        set rows = rows + [[r.module, str(len(r.findings))]]
    end
    ui.table(["module", "findings"], rows)
    ui.banner("Done")
end
```

## Diagnostics

```
print EXPR                 # write a line to the script's output log
assert EXPR[, "message"]   # abort the script if EXPR is false
fail "message"              # abort the script unconditionally
sleep SECONDS               # pause (float seconds)
```

## The REPL

```
$ nyx script repl
NyxScript REPL — variables persist across lines. 'exit' or Ctrl+D/Ctrl+C to quit.
nyx> set d = {}
nyx> set d["found"] = 0
nyx> func bump():
...     set d["found"] = d["found"] + 1
... end
nyx> bump()
nyx> print d
{found: 1}
nyx> exit
```

`nyx script repl` (optionally with `--unsafe`) evaluates each line — or
each complete `if`/`foreach`/`while`/`func`/`try`/`python:` block, once
its matching `end` arrives — against one long-lived `Interpreter`, so
everything `set` or `func`-defined earlier is still there on the next
line. It's a scratchpad for trying out a snippet before it goes in a real
`.nyx` file, not a replacement for `nyx script run`.

## Escape hatches: `python:` and `pip`

Both are **disabled by default** and refuse to run without `--unsafe`
(CLI) / the Unsafe toggle (TUI) — enabling either is an explicit,
visible choice, not a silent default.

```
pip "requests"

python:
    import requests
    response = requests.get(f"https://{target}/robots.txt")
    status = response.status_code
end

print "status: {status}"
```

`python:` blocks get read/write access to the script's current scope
(global or local, whichever is active) — anything the block sets becomes
a NyxScript variable afterward, in that same scope. `pip` shells out to
`uv pip install` (falling back to `python -m pip install` if `uv` isn't
on `PATH`) as an argv list, never through a shell, so a package name
can't smuggle in shell metacharacters.

The linter still flags both with a warning (not an error — they're valid,
just unsafe) and, past a `python:` block, stops checking for undefined
variables in the rest of that scope, since it can't know what the block
set.

## The linter

`nyx script lint file.nyx` (and the LSP's live diagnostics) run
`lint_source()` — the same pure static analysis, zero execution, zero
network access. It catches:

- undefined variables (including inside `"{...}"` interpolation and
  function-call arguments)
- unknown `run` modules and unknown function calls, both with a "did you
  mean" suggestion via `difflib`
- unknown `ui.*` members
- `break`/`continue` outside a loop, `return` outside a function
- empty `if`/`foreach`/`while`/`func`/`try` bodies (warning)
- a variable used after `try`/`except` that isn't guaranteed defined on
  every path that reaches it (see [Error handling](#error-handling--tryexcept))
- `python:`/`pip` usage (warning — valid, but requires `--unsafe`)

It does **not** catch: function-call arity mismatches (that's a runtime
check, since it needs the actual call site), type errors (`"a" + 1`), or
missing members on an imported library (see
[Libraries](#libraries--import)).

## Errors

Every NyxScript exception (`LexError`, `ParseError`, `RuntimeScriptError`)
carries the source line it happened on. `nyx script run` and `nyx script
repl` print the offending source line itself alongside the message, with
a caret under where it starts:

```
Error: cannot apply '+' to int and str
3 | print x + y
    ^
```

`nyx script run` stops at the first uncaught error; nothing after it
executes. `try`/`except` (see [Error handling](#error-handling--tryexcept))
lets a script catch one and keep going instead.

## Full grammar

```
program        := statement*

statement      := set_stmt | index_set_stmt | if_stmt | foreach_stmt
                | while_stmt | break_stmt | continue_stmt | func_stmt
                | return_stmt | import_stmt | try_stmt | run_stmt
                | save_stmt | print_stmt | sleep_stmt | assert_stmt
                | fail_stmt | pip_stmt | python_block | expr_stmt | doc_stmt

set_stmt       := "set" IDENT "=" expr
index_set_stmt := "set" IDENT index_suffix+ "=" expr
if_stmt        := "if" expr ":" statement* ("else" ":" statement*)? "end"
foreach_stmt   := "foreach" IDENT "in" expr ":" statement* "end"
while_stmt     := "while" expr ":" statement* "end"
break_stmt     := "break"
continue_stmt  := "continue"
func_stmt      := "func" IDENT "(" (IDENT ("," IDENT)*)? ")" ":" statement* "end"
return_stmt    := "return" expr?
import_stmt    := "import" expr "as" IDENT
try_stmt       := "try" ":" statement* "except" IDENT ":" statement* "end"
run_stmt       := "run" IDENT expr ("as" IDENT)?
save_stmt      := "save" IDENT "to" expr
print_stmt     := "print" expr
sleep_stmt     := "sleep" expr
assert_stmt    := "assert" expr ("," expr)?
fail_stmt      := "fail" expr
pip_stmt       := "pip" expr
python_block   := "python:" <raw source lines> "end"
expr_stmt      := call_expr                      # a call used for its side effect
doc_stmt       := STRING                          # a docstring — a no-op at run time

expr           := or_expr
or_expr        := and_expr ("or" and_expr)*
and_expr       := not_expr ("and" not_expr)*
not_expr       := "not" not_expr | comparison
comparison     := additive (("==" | "!=" | "<" | "<=" | ">" | ">=") additive)?
additive       := multiplicative (("+" | "-") multiplicative)*
multiplicative := unary (("*" | "/") unary)*
unary          := "-" unary | postfix
postfix        := primary (call_suffix | index_suffix | slice_suffix | attr_suffix)*
call_suffix    := "(" (expr ("," expr)*)? ")"
index_suffix   := "[" expr "]"
slice_suffix   := "[" expr? ":" expr? "]"
attr_suffix    := "." IDENT
primary        := NUMBER | STRING | "true" | "false"
                | "[" (expr ("," expr)*)? "]"
                | "{" (expr ":" expr ("," expr ":" expr)*)? "}"
                | "(" expr ")"
                | "lambda" "(" (IDENT ("," IDENT)*)? ")" ":" expr
                | IDENT                            # a variable, or a call/index base
```

`IDENT` may itself be dotted (`network.discover`, `math.square`,
`ui.confirm`) — the lexer merges `name.name` into one token when there's
no whitespace around the `.` and it directly follows an identifier, which
is what makes `run` module names and simple `lib.member`/`ui.member`
access work without the parser needing to see two tokens. The `attr_suffix`
production above is the general case: a literal `.` that shows up
*anywhere else* (after `]`, after `)`, or with a space around it) — e.g.
`result[0].module` — where the lexer can't merge it, so the parser
consumes it as its own postfix step instead. Both paths end up calling the
same member-lookup code, so they behave identically; two mechanisms exist
only because ripping out the older one would break the existing
`run network.discover`-style module-name convention.
