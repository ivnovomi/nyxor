# NyxScript for VS Code

Syntax highlighting, diagnostics, and completion for `.nyx` files —
[NyxScript](../../README.md#nyxscript), the small automation language for
[NYXOR](../../README.md).

## Features

- Syntax highlighting for keywords, module names, strings (with
  `{interpolation}` highlighted inside), numbers, booleans, operators, and
  `python: ... end` blocks (highlighted as embedded Python).
- Real-time diagnostics: undefined variables, unknown `run` modules (with
  "did you mean" suggestions), empty control-flow bodies — powered by
  NyxScript's own static linter, running over the Language Server Protocol.
- Completion for keywords, module names, and variables already `set` in
  the open file.
- Comment toggling (`#`), bracket/quote auto-closing, and `if`/`foreach`/
  `python` block indentation.

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
