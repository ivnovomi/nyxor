# Plugin Development

Fifteen minutes from now you can have a new `nyx <yourthing>` command
shipping findings through the exact same reporting pipeline as `nyx
audit` — JSON, Markdown, HTML, SARIF, `--output`, all of it, for free. A
plugin is a Python package that declares an entry point in the
`nyxor.plugins` group and exposes an object satisfying the `Plugin`
protocol (`nyxor.core.interfaces.Plugin`). That's the entire contract —
there is no central registry to edit, in NYXOR itself or in your
package. See [Architecture](Architecture) for how this fits into the
rest of the system.

## 1. Implement the plugin

```python
# my_package/plugin.py
import typer
from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.core.output import emit_results

my_app = typer.Typer(name="mymodule", help="What this module does.")


@my_app.command("run")
def run(ctx: typer.Context, target: str) -> None:
    context: NyxorContext = ctx.obj  # populated after global options are parsed
    result = ModuleResult(module="mymodule.run", target=target)
    result.findings.append(Finding(title="Example", severity=Severity.INFO, description="..."))
    emit_results(context, [result], title="My Module Report")


class MyPlugin:
    metadata = PluginMetadata(
        name="mymodule",
        description="What this module does.",
        version="0.1.0",
        author="you",
        commands=("run",),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.add_typer(my_app)


PLUGIN = MyPlugin()
```

Key points:

- `register()` runs once at CLI startup, **before** global options are
  parsed. Use it only to attach commands — don't read `context.config`
  there for anything that should honor `--profile`.
- Command functions read the *runtime* context from `ctx.obj`, not from
  the `context` argument passed to `register()`.
- Always return a `ModuleResult` and call `emit_results()` so `--json`,
  `--yaml`, and `--output` work automatically. Don't hand-print with
  `print()` or bypass `context.console`.
- Findings are informational observations (`Finding(severity=...)`),
  not exploit outcomes. This is an auditing platform — see
  [Security](Security) for the passive-only design constraint every
  plugin needs to respect.

## 2. Declare the entry point

```toml
# my_package's pyproject.toml
[project.entry-points."nyxor.plugins"]
mymodule = "my_package.plugin:PLUGIN"
```

Install the package (`uv pip install -e .` or `pip install .`) in the
same environment as NYXOR. `nyx plugin list` should show it immediately
— nothing else needs to change, in your package or in NYXOR's.

## 3. Test it

Plugins should be testable without going through the CLI at all: import
your module-logic functions directly and assert on the `ModuleResult`
they return. Only wire up Typer/`ctx.obj` for a thin integration smoke
test.

## Reuse across front-ends

If your scan logic might be useful from `nyx tui` too (or any future
front-end), split it out as an `async def run_*(...) -> ModuleResult`
function with no Typer/Textual imports, and call it from your command —
see `plugins/dns_/plugin.py::run_lookup` for the pattern. The TUI's Scan
tab already does this for the built-in network/dns/tls/http plugins.

Want your module callable from [NyxScript](NyxScript-Language-Guide)
too — `run mymodule example.com as result`? Add it to `MODULE_RUNNERS`
in `nyxor/core/scripting/stdlib.py`:

```python
async def _run_mymodule(target: str, config: NyxorConfig) -> list[ModuleResult]:
    from my_package.plugin import run_mymodule
    return [await run_mymodule(target, config)]

MODULE_RUNNERS["mymodule"] = _run_mymodule
```

Do this and `nyx script lint` will validate `run mymodule ...`
statements, suggest it via "did you mean" on typos, and both the TUI's
completion box and the language server (`nyx script lsp`) will offer it
as a completion — automatically, because they all read from the same
`MODULE_RUNNERS` dict.

Want it reachable from the REST API too? Add a two-line route in
`api/app.py` calling the same `run_*` coroutine and returning it
directly — FastAPI serializes the `ModuleResult` Pydantic model without
any reshaping. Remember the [SSRF guard](REST-API#the-ssrf-guard) if
your module makes outbound requests based on user input.

## Disabling a plugin

Users can disable any plugin — built-in or third-party — via config:

```toml
[plugins]
disabled = ["mymodule"]
```

## Common building blocks

- `nyxor.core.models` — `Finding`, `Asset`, `ModuleResult`, `Severity`.
- `nyxor.core.output.emit_results` — renders results per the active
  output options.
- `nyxor.plugins.inventory.store.InventoryStore` — persist discovered
  `Asset`s so `nyx inventory list` picks them up.
- `nyxor.core.errors.NyxorError` (and subclasses) — raise these for
  expected failures; the CLI renders them cleanly instead of a
  traceback.

## Scaffolding one from the TUI

`nyx tui`'s **Plugins** tab has a "Scaffold new plugin" button that
generates a starter `nyxor_plugins/<name>/plugin.py` from a name you
type in — a working skeleton to edit rather than starting from a blank
file.
