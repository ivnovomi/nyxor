# Contributing

## How this project is built

NYXOR is built with [Claude Code](https://claude.com/claude-code) as a
development tool — a lot of the code, tests, and docs in this repo were
written with an AI pair-programmer, and the commit history says so
(`Co-Authored-By: Claude` on the commits where that's true). That's not
a footnote, it's just how this project is made.

What that doesn't change: every feature exists because the maintainer
decided it should — what to build, what to cut, what "done" means, what
ships and what doesn't. Every change is reviewed and, wherever
practical, run for real against real targets before being called
finished. An AI pair-programmer is fast at writing code and bad at
knowing what's actually worth building; that half stays human.

If you don't like that this project is built this way, that's a
reasonable position to hold — but judge it by what's in the repo: the
tests, the CI, whether the thing actually works when you run it. That's
true regardless of how any individual line got typed. See
[Security § How this project is built](Security#how-this-project-is-built)
too.

## Setup

```bash
git clone https://github.com/ivnovomi/nyxor.git
cd nyxor
uv sync --extra dev
```

## Before opening a PR

```bash
uv run ruff format .
uv run ruff check .
uv run mypy src
uv run pytest
```

CI runs the same checks on Linux, Windows, and macOS, plus a VS Code
extension compile check, on every push and PR.

## Guidelines

- **Core stays small.** New features are plugins (see
  [Plugin Development](Plugin-Development)), not additions to
  `nyxor/core`. If a change to `core/` seems necessary, say why in the
  PR description.
- **Modules return `ModuleResult`.** Never print scan output directly
  from plugin logic — return structured data and let `core/output.py` /
  `core/reporting/` render it, so `--json`/`--yaml`/`--output` keep
  working everywhere.
- **Stay cross-platform.** No platform-specific shell commands without a
  guarded adapter (see `plugins/network/discovery.py` for the pattern).
- **Stay safe.** NYXOR performs authorized, non-destructive checks only:
  TCP-connect scans, standard DNS/TLS/HTTP requests. No exploitation, no
  raw sockets, no credential brute-forcing. See [Security](Security) for
  the full set of design constraints, including what's expected of code
  that touches user-supplied input (SSRF/XSS considerations if you're
  adding anything HTTP-facing).
- **Type hints everywhere**, docstrings on public functions/classes
  where the *why* isn't obvious from the signature — not restating what
  the code already says.
- **Tests accompany behavior changes.** Prefer testing module logic
  directly over going through the Typer CLI layer, and actually run
  what you built against a real target (or a mocked one with realistic
  data) before calling it done, not just "looks right."

## Cutting a release

Release process — version bump, changelog, PyPI Trusted Publishing, and
moving the GitHub Action's floating `v1` tag — is documented separately:
[`docs/publishing.md`](https://github.com/ivnovomi/nyxor/blob/main/docs/publishing.md).
That's a maintainer task, not something a contributor PR needs to touch.

## Where things live

See [Architecture](Architecture) for the full layout — the short
version: plugin logic in `src/nyxor/plugins/<name>/`, NyxScript's
standard library in `lib/*.nyx` (written in NyxScript itself — see
[NyxScript Standard Library Reference](NyxScript-Standard-Library-Reference)
before adding a new module, to avoid duplicating an existing one or
naming a function the same as a builtin), tests mirroring the source
tree under `tests/`.
