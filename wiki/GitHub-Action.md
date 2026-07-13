# GitHub Action

NYXOR ships as a GitHub Action (`action.yml` at the repo root) — a
composite action that installs and runs NYXOR on GitHub-hosted runners
via `uv tool run`, no Python setup step and no PyPI publish required in
your own workflow.

```yaml
name: Security audit
on: [pull_request]

permissions:
  pull-requests: write   # only needed for the PR-comment step below

jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - id: nyxor
        uses: ivnovomi/nyxor@v1
        with:
          target: example.com
          badge-path: nyxor-badge.svg
          fail-on: high   # optional — see below

      # Only needed if you set fail-on above.
      - if: steps.nyxor.outputs.exceeded-fail-on == 'true'
        run: exit 1
```

## Inputs

| Input | Default | Purpose |
|---|---|---|
| `target` | *(required)* | Domain to audit |
| `report-path` | `nyxor-report.html` | Where to write the report; format inferred from extension (`.json`/`.md`/`.html`/`.sarif`). Empty string skips writing one |
| `badge-path` | `nyxor-badge.svg` | Where to write the SVG grade badge. Empty string skips |
| `unsafe` | `"false"` | Allow NyxScript's `python:`/`pip` escape hatches (not used by this action itself — only matters if you extend the workflow to run your own `.nyx` script) |
| `nyxor-ref` | `main` | Git ref of `ivnovomi/nyxor` to install (branch, tag, or commit) |
| `pr-comment` | `"true"` | Post the grade as a PR comment. Only fires on `pull_request` events; needs `permissions: pull-requests: write` |
| `fail-on` | `""` (disabled) | Severity to gate on: `critical`, `high`, `medium`, `low`, `info` |

## Outputs

| Output | Meaning |
|---|---|
| `grade` | Letter grade, `A+` down to `F` |
| `exceeded-fail-on` | `"true"`/`"false"` — whether `fail-on`'s threshold was met or exceeded |

## Why `fail-on` doesn't fail the action itself

This is the one design choice worth understanding before you use
`fail-on`: **the action never exits non-zero over findings, even when
you set `fail-on`.** You add your own tiny step to act on the
`exceeded-fail-on` output instead:

```yaml
- if: steps.nyxor.outputs.exceeded-fail-on == 'true'
  run: exit 1
```

This isn't arbitrary — it's a direct consequence of how GitHub Actions
composite actions work: **if any internal step of a composite action
fails, none of its declared `outputs:` reach the calling workflow** —
including `grade`, which has nothing to do with `fail-on`. An earlier
version of this action *did* fail internally on a `fail-on` breach, and
`grade` silently came back empty in every downstream job as a result.
Splitting "was the threshold hit" (an output, always reliable) from
"should the build actually fail" (your own explicit step) fixes that —
reports/badges/PR comments get written either way, regardless of what
your `exit 1` step does or when it runs relative to later steps.

## SARIF → GitHub Code Scanning

Point `report-path` at a `.sarif` file and feed it to GitHub's own
uploader — findings show up as native alerts in the repo's **Security →
Code scanning** tab, the same place CodeQL results land:

```yaml
permissions:
  security-events: write   # required by upload-sarif

steps:
  - uses: ivnovomi/nyxor@v1
    with:
      target: example.com
      report-path: results.sarif
  - uses: github/codeql-action/upload-sarif@v3
    with:
      sarif_file: results.sarif
```

## Version tags

`uses: ivnovomi/nyxor@v1` tracks a floating major-version tag (standard
GitHub Actions convention) — it gets moved to point at the latest
compatible release rather than pinning a single commit. Pin
`nyxor-ref`, or use a full commit SHA in `uses:`, if you need exact
reproducibility.

## See also

- [`.github/workflows/cloud-demo.yml`](https://github.com/ivnovomi/nyxor/blob/main/.github/workflows/cloud-demo.yml)
  — a working example that runs on a schedule and commits the result.
- [`action.yml`](https://github.com/ivnovomi/nyxor/blob/main/action.yml)
  — the source of truth for every input/output, and the composite steps
  themselves.
- [REST API](REST-API) — for running audits from a long-lived server
  instead of per-CI-run.
