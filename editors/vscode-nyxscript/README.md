# NyxScript for VS Code

Syntax highlighting, diagnostics, and completion for `.nyx` files —
[NyxScript](../../README.md#nyxscript), the small automation language for
[NYXOR](../../README.md).

## Features

- Syntax highlighting for keywords (including `func`/`return`/`while`/
  `break`/`continue`/`import`), function definitions and calls
  (`square(4)`, `math.square(4)`, `ui.confirm(...)`), built-in functions
  (`len`, `range`, `upper`, `join`, ...), module names, docstrings
  (highlighted separately from ordinary strings), strings (with
  `{interpolation}` highlighted inside), numbers, booleans, operators, and
  `python: ... end` blocks (highlighted as embedded Python).
- Real-time diagnostics: undefined variables, unknown `run` modules and
  unknown function calls (both with "did you mean" suggestions), stray
  `break`/`continue`/`return`, empty control-flow bodies — powered by
  NyxScript's own static linter, running over the Language Server Protocol.
- Completion for keywords, module names, built-in functions, `ui.*`
  functions, and variables already `set` in the open file — plus **import
  path completion**: type `import "` and get every `.nyx` file in the
  workspace, path relative to the workspace root (the file you're editing
  is excluded).
- **Hover** shows the signature and [docstring](../../docs/nyxscript.md#docstrings)
  of any function you point at — including calls through an import alias
  (`math.square(4)` shows `square`'s docstring from wherever `math` was
  imported from).
- **Go to Definition** (F12 / Ctrl-click) on a function call jumps straight
  to its `func` line, in the current file or an imported library.
- Comment toggling (`#`), bracket/quote auto-closing, and
  `if`/`foreach`/`while`/`func`/`python` block indentation (indent after a
  line ending in `:`, outdent on `end`/`else`).

## Requirements

The extension is a thin LSP client — the actual language server is
NYXOR's `nyx script lsp`, so you need NYXOR installed with the `lsp` extra:

```bash
uv sync --extra lsp
```

By default the extension runs `nyx script lsp`. If `nyx` isn't on your
`PATH` (e.g. you only have it inside a project's `uv` environment), set:

```json
{
  "nyxscript.serverCommand": "uv",
  "nyxscript.serverArgs": ["run", "nyx", "script", "lsp"]
}
```

in your workspace settings (and make sure VS Code's cwd for that setting
is the NYXOR project directory).

## Development

```bash
npm install
npm run compile   # or: npm run watch
```

Then press F5 in VS Code (with this folder open) to launch an Extension
Development Host with NyxScript support loaded.
