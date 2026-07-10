# Publishing a release

Two things happen when a `vX.Y.Z` tag is pushed: a GitHub Release gets
created (manually, via `gh release create` — see the release process
used throughout this project's history), and — once the one-time setup
below is done — `.github/workflows/publish-pypi.yml` builds and publishes
the package to PyPI automatically.

## One-time setup (only the project owner can do this)

PyPI publishing uses [Trusted Publishing](https://docs.pypi.org/trusted-publishers/) —
no API token lives in this repo or anywhere else. Instead, PyPI trusts
this specific GitHub Actions workflow directly via OIDC. To wire that up:

1. Go to <https://pypi.org/manage/account/publishing/> (log in, or create
   a PyPI account first if you don't have one).
2. Under "Add a new pending publisher", fill in:
   - **PyPI Project Name**: `nyxor`
   - **Owner**: `ivnovomi`
   - **Repository name**: `nyxor`
   - **Workflow name**: `publish-pypi.yml`
   - **Environment name**: `pypi`
3. Save it. Nothing else to configure — no token to copy anywhere.

That's the only step that needs your PyPI login. Everything else already
happens automatically: `dist/` builds via `uv build`, then
`pypa/gh-action-pypi-publish` publishes it using the OIDC identity of the
`publish-pypi.yml` workflow run.

## Cutting a release

The process this project already uses, unchanged:

```bash
# bump pyproject.toml + src/nyxor/__init__.py, update CHANGELOG.md, then:
uv sync --extra dev --extra lsp --extra api --extra mcp   # resync uv.lock
uv run pytest && uv run ruff check . && uv run mypy src
git add -A && git commit -m "Bump to X.Y.Z: ..."
git push origin main
git tag -a vX.Y.Z -m "vX.Y.Z" && git push origin vX.Y.Z
gh release create vX.Y.Z --title "..." --notes "..."
```

Pushing the `vX.Y.Z` tag is also what triggers `publish-pypi.yml` — once
the trusted-publisher setup above is done, that tag push is the entire
PyPI release process. Check the Actions tab if you want to watch it
happen, or just check <https://pypi.org/project/nyxor/> a minute later.

## The GitHub Action's own version tag

Separately from PyPI, the GitHub Action (`action.yml` at the repo root)
is referenced by users as `uses: ivnovomi/nyxor@v1` — a floating major
version tag, by GitHub Actions convention, not the same as the package's
`vX.Y.Z` semver tags. Move it to point at the latest stable commit after
a release you're confident in:

```bash
git tag -f v1 vX.Y.Z
git push origin v1 --force
```

(`--force` here is normal and expected for a floating major-version tag —
it's how `actions/checkout@v4`-style version pins work across the whole
GitHub Actions ecosystem, not a footgun specific to this repo.)
