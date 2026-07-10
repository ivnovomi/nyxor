---
name: nyxscript
description: Write, lint, and run NyxScript (.nyx) automation files for NYXOR — a small language for batch-driving audit/dns/tls/http/network/recon scan modules. Use whenever the user asks to write a .nyx script, automate a NYXOR scan, or debug NyxScript syntax/lint/runtime errors.
---

# NyxScript

NyxScript is NYXOR's own small automation language — not YAML, not a
config format, an actual lexer/parser/interpreter/linter language that
batch-drives NYXOR's scan modules (`audit`, `dns`, `tls`, `http`,
`network.discover`, `network.scan`, `recon.subdomains`). Every `run`
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

**Types**: string (`"..."`/`'...'`, with `\n \t \\ \" \'` escapes and
`{expr}` interpolation), number (`int`/`float`), `true`/`false`, list
(`[1, 2, 3]`, heterogeneous, indexable). No `null` — an unset variable is
a lint error, not a value.

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
`abs`, `round`, `sorted`, `reversed`, `min`, `max`, `sum`, `type_of`.

**Interactive UI — `ui.*`** (works unchanged from both CLI and TUI):
`ui.confirm(msg) -> bool`, `ui.input(prompt) -> string`,
`ui.select(prompt, options) -> string`, `ui.table(headers, rows)`,
`ui.banner(title)`, `ui.status(msg)`.

**Diagnostics**: `print EXPR`, `assert EXPR[, "message"]`, `fail
"message"`, `sleep SECONDS`.

**Escape hatches — `python:` / `pip`**: disabled by default, refuse to
run without `--unsafe` (CLI) or the MCP `run_nyxscript` tool (which
*never* enables `--unsafe` — an MCP call can't get arbitrary code
execution through this path, by design). Don't reach for these unless
the task genuinely needs a Python library NyxScript has no built-in for;
prefer the built-ins and scan modules first.

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
- Assuming closures — a function can't see a caller's local variables;
  only its own locals and its *defining* scope's globals.
- Reaching for `python:`/`pip` for things the built-ins already cover
  (string ops, list ops, math) — adds an unsafe flag for no reason.
- Forgetting that `run`'s module names use dotted syntax
  (`network.discover`, `recon.subdomains`) but these are single tokens,
  not attribute access.

## Full grammar and worked examples

See [docs/nyxscript.md](../../../docs/nyxscript.md) in the repo root for
the complete EBNF grammar, the full built-in/`ui.*` tables, and more
worked examples (fibonacci, a full audit-and-report script, a library
with sibling calls).
