# Contributing

## How this project is built

NYXOR is built with [Claude Code](https://claude.com/claude-code) as a
development tool — a lot of the code, tests, and docs in this repo were
written with an AI pair-programmer, and the commit history says so
(`Co-Authored-By: Claude` on the commits where that's true). That's not
a footnote, it's just how this project is made.

What that doesn't change: every feature here exists because I decided it
should — what to build, what to cut, what "done" means, what ships and
what doesn't. Every change is reviewed and, wherever it's practical, run
for real against real targets before I call it finished — that's why the
commit history is full of "verified live against X" rather than "looks
right." An AI pair-programmer is fast at writing code and bad at knowing
what's actually worth building; that half stays mine.

If you don't like that this project was built this way, that's a
reasonable position to hold — but judge it by what's in the repo: the
tests, the CI, whether the thing actually works when you run it. That's
true regardless of how any individual line got typed.

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
