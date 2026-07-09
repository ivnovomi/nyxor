# Contributing

## Setup

```bash
uv sync --extra dev
```

## Before opening a PR

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run pytest
```

## Guidelines

- **Core stays small.** New features are plugins (see
  [plugin-development.md](plugin-development.md)), not additions to
  `nyxor/core`. If a change to `core/` seems necessary, say why in the PR
  description.
- **Modules return `ModuleResult`.** Never print scan output directly from
  plugin logic — return structured data and let `core/output.py` /
  `core/reporting/` render it, so `--json`/`--yaml`/`--output` keep working
  everywhere.
- **Stay cross-platform.** No platform-specific shell commands without a
  guarded adapter (see `plugins/network/discovery.py` for the pattern).
- **Stay safe.** NYXOR performs authorized, non-destructive checks only:
  TCP-connect scans, standard DNS/TLS/HTTP requests. No exploitation, no
  raw sockets, no credential brute-forcing.
- **Type hints everywhere**, docstrings on public functions/classes where
  the *why* isn't obvious from the signature.
- **Tests accompany behavior changes.** Prefer testing module logic
  directly over going through the Typer CLI layer.
