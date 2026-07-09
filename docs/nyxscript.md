# NyxScript language reference

NyxScript is the automation language that ships inside NYXOR. It has its
own lexer, recursive-descent parser, AST, tree-walking interpreter, and a
standalone static linter — not a config format, not a YAML dialect, an
actual small language. This document is the full reference: every
statement, every expression form, functions, imports/libraries, the
interactive `ui.*` module, and the two escape hatches.

Run `nyx script new myfile.nyx` to get a starter file, `nyx script lint
myfile.nyx` to check one without running it, and `nyx script run
myfile.nyx` to execute it. Every editor with an LSP client (VS Code,
Neovim, Helix, ...) gets diagnostics/completion/hover for free from `nyx
script lsp` — see [plugin-development.md](plugin-development.md) if
you're embedding NyxScript somewhere new.

## Contents

- [The shape of a script](#the-shape-of-a-script)
- [Types and literals](#types-and-literals)
- [Variables](#variables)
- [Expressions and operators](#expressions-and-operators)
- [String interpolation](#string-interpolation)
- [Control flow](#control-flow)
- [Running scan modules](#running-scan-modules-run)
- [Saving reports](#saving-reports-save)
- [Functions](#functions)
- [Libraries — `import`](#libraries--import)
- [Built-in functions](#built-in-functions)
- [Interactive UI — `ui.*`](#interactive-ui--ui)
- [Diagnostics — `print` / `assert` / `fail` / `sleep`](#diagnostics)
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
| list | `[1, 2, 3]`, `["a", "b"]` | heterogeneous, indexable, no dict/map type |

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
and int`) rather than silently coercing.

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
| `type_of` | `type_of(x)` | `"string"`, `"int"`, `"float"`, `"bool"`, `"list"` |

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
- empty `if`/`foreach`/`while`/`func` bodies (warning)
- `python:`/`pip` usage (warning — valid, but requires `--unsafe`)

It does **not** catch: function-call arity mismatches (that's a runtime
check, since it needs the actual call site), type errors (`"a" + 1`), or
missing members on an imported library (see
[Libraries](#libraries--import)).

## Errors

Every NyxScript exception (`LexError`, `ParseError`, `RuntimeScriptError`)
carries the source line it happened on and prints as `line N: message`.
`nyx script run` stops at the first uncaught error; nothing after it
executes.

## Full grammar

```
program        := statement*

statement      := set_stmt | if_stmt | foreach_stmt | while_stmt
                | break_stmt | continue_stmt | func_stmt | return_stmt
                | import_stmt | run_stmt | save_stmt | print_stmt
                | sleep_stmt | assert_stmt | fail_stmt | pip_stmt
                | python_block | expr_stmt | doc_stmt

set_stmt       := "set" IDENT "=" expr
if_stmt        := "if" expr ":" statement* ("else" ":" statement*)? "end"
foreach_stmt   := "foreach" IDENT "in" expr ":" statement* "end"
while_stmt     := "while" expr ":" statement* "end"
break_stmt     := "break"
continue_stmt  := "continue"
func_stmt      := "func" IDENT "(" (IDENT ("," IDENT)*)? ")" ":" statement* "end"
return_stmt    := "return" expr?
import_stmt    := "import" expr "as" IDENT
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
postfix        := primary (call_suffix | index_suffix | attr_suffix)*
call_suffix    := "(" (expr ("," expr)*)? ")"
index_suffix   := "[" expr "]"
attr_suffix    := "." IDENT
primary        := NUMBER | STRING | "true" | "false"
                | "[" (expr ("," expr)*)? "]"
                | "(" expr ")"
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
