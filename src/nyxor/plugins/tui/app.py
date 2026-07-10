"""NYXOR's interactive terminal dashboard, built on Textual.

The TUI is a thin presentation layer over the exact same building blocks
the CLI uses — :class:`~nyxor.core.models.ModuleResult`, the plugin loader,
and the inventory store. It never reimplements scan logic; it calls the
``run_*`` coroutines exported by each domain plugin (see
``plugins/network/plugin.py``, ``plugins/dns_/plugin.py``, etc.) so the two
front-ends can never drift apart.
"""

from __future__ import annotations

import inspect
import re
from datetime import datetime
from pathlib import Path

from rich.markup import escape as escape_markup
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, VerticalScroll
from textual.geometry import Offset
from textual.reactive import reactive
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    RichLog,
    Select,
    Static,
    Switch,
    TabbedContent,
    TabPane,
    TextArea,
)

from nyxor import __version__
from nyxor.core.config import NyxorConfig, load_config
from nyxor.core.errors import NyxorError
from nyxor.core.models import ModuleResult, Severity
from nyxor.core.plugins import DiscoveredPlugin, discover_plugins
from nyxor.core.reporting import ReportDocument, get_writer
from nyxor.core.scripting import TEMPLATE as SCRIPT_TEMPLATE
from nyxor.core.scripting import LintIssue, ScriptError, ScriptUI, lint_source, run_script
from nyxor.plugins.audit.plugin import run_audit
from nyxor.plugins.dns_.plugin import run_lookup as dns_run_lookup
from nyxor.plugins.http_.plugin import run_inspect as http_run_inspect
from nyxor.plugins.inventory.store import InventoryStore
from nyxor.plugins.network.plugin import run_discover as network_run_discover
from nyxor.plugins.network.plugin import run_scan as network_run_scan
from nyxor.plugins.recon.plugin import run_recon
from nyxor.plugins.system.doctor import run_diagnostics
from nyxor.plugins.tls_.plugin import run_inspect as tls_run_inspect
from nyxor.plugins.tui.browser import ScriptBrowserScreen
from nyxor.plugins.tui.editor import CompletionPopup, NyxScriptEditor

PLUGIN_SKELETON = '''\
"""The ``{name}`` plugin."""

from __future__ import annotations

import typer

from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata


def _run(ctx: typer.Context) -> None:
    """TODO: describe what `nyx {name}` does."""
    context: NyxorContext = ctx.obj
    context.console.print("Hello from the {name} plugin!")


class {class_name}Plugin:
    metadata = PluginMetadata(
        name="{name}",
        description="TODO: describe this plugin.",
        version="0.1.0",
        author="you",
        commands=("{name}",),
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        app.command("{name}")(_run)


PLUGIN = {class_name}Plugin()
'''

SEVERITY_STYLE: dict[Severity, str] = {
    Severity.CRITICAL: "bold #ff4d6d",
    Severity.HIGH: "bold #ff9f43",
    Severity.MEDIUM: "#f5d76e",
    Severity.LOW: "#2ecc71",
    Severity.INFO: "#7f95b3",
}

MODULE_CHOICES: list[tuple[str, str]] = [
    ("Audit — full (DNS + TLS + HTTP)", "audit.full"),
    ("Network — discover (ping sweep / CIDR)", "network.discover"),
    ("Network — scan (TCP services)", "network.scan"),
    ("DNS — lookup", "dns.lookup"),
    ("TLS — inspect", "tls.inspect"),
    ("HTTP — inspect", "http.inspect"),
    ("Recon — subdomains (passive)", "recon.subdomains"),
]


def _severity_text(severity: Severity) -> Text:
    return Text(severity.value.upper(), style=SEVERITY_STYLE[severity])


class StatCard(Static):
    """A small labeled metric tile used on the Overview tab."""

    def __init__(self, label: str, value: str, *, tone: str = "") -> None:
        super().__init__(classes="stat-card")
        self._label = label
        self._value = value
        self._tone = tone

    def compose(self) -> ComposeResult:
        yield Label(self._value, classes=f"stat-value {self._tone}")
        yield Label(self._label, classes="stat-label")


class NyxorApp(App[None]):
    """The `nyx tui` dashboard."""

    TITLE = "NYXOR"
    SUB_TITLE = f"Security Assessment Toolkit · v{__version__}"

    CSS = """
    Screen {
        background: #0b0e14;
        layers: base popup;
    }

    Header {
        background: #141a26;
        color: #7ee7e1;
    }

    Footer {
        background: #141a26;
    }

    TabbedContent {
        background: #0b0e14;
    }

    Tabs {
        background: #10141f;
    }

    #stats-row {
        height: auto;
        padding: 1 1 0 1;
    }

    .stat-card {
        border: round #2a3550;
        background: #10141f;
        width: 1fr;
        height: 5;
        margin: 0 1 1 0;
        align: center middle;
    }

    .stat-value {
        text-align: center;
        text-style: bold;
        color: #7ee7e1;
        width: 100%;
    }

    .stat-label {
        text-align: center;
        color: #6b7a99;
        width: 100%;
    }

    .panel-title {
        color: #b98cff;
        text-style: bold;
        padding: 1 0 0 1;
    }

    DataTable {
        background: #10141f;
        border: round #2a3550;
        margin: 0 1 1 1;
    }

    #scan-form {
        height: auto;
        padding: 1;
    }

    #scan-form Select, #scan-form Input {
        margin-right: 1;
    }

    #target-input {
        width: 2fr;
    }

    #ports-input {
        width: 1fr;
    }

    #run-scan {
        background: #7c3aed;
        color: white;
    }

    #run-scan:hover {
        background: #8b5cf6;
    }

    #scan-status {
        padding: 0 1 1 1;
        color: #7ee7e1;
        text-style: italic;
    }

    #inventory-toolbar {
        height: auto;
        padding: 1;
    }

    #inventory-toolbar Button {
        margin-right: 1;
    }

    .danger-button {
        background: #7f1d3d;
        color: white;
    }

    Button {
        background: #1f2b45;
        color: #d7e0f5;
    }

    Button:hover {
        background: #2a3d63;
    }

    #script-toolbar, #plugins-toolbar {
        height: auto;
        padding: 1;
    }

    #script-toolbar Button, #plugins-toolbar Button {
        margin-right: 1;
    }

    #script-path, #new-plugin-name {
        width: 1fr;
        margin-right: 1;
    }

    #unsafe-row {
        height: auto;
        padding: 0 1 1 1;
    }

    #unsafe-toggle {
        margin-right: 1;
    }

    #unsafe-row Label {
        color: #ff9f43;
        text-style: italic;
    }

    TextArea {
        border: round #2a3550;
        margin: 0 1 1 1;
        height: 1fr;
    }

    TextArea .text-area--suggestion {
        color: #4d5b7a;
        text-style: italic;
    }

    RichLog {
        border: round #2a3550;
        background: #10141f;
        margin: 0 1 1 1;
        height: 12;
    }

    #plugins-table {
        height: 10;
    }

    #plugin-status, #script-status {
        padding: 0 1 0 1;
        color: #7ee7e1;
        text-style: italic;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh_all", "Refresh"),
        Binding("1", "goto_overview", "Overview", show=False),
        Binding("2", "goto_inventory", "Inventory", show=False),
        Binding("3", "goto_scan", "Scan", show=False),
        Binding("4", "goto_script", "Script", show=False),
        Binding("5", "goto_plugins", "Plugins", show=False),
        Binding("escape", "dismiss_popup", "Dismiss", show=False),
    ]

    inventory_count: reactive[int] = reactive(0)

    def __init__(self) -> None:
        super().__init__()
        self.config: NyxorConfig = load_config()
        self.inventory = InventoryStore()
        self._plugins: list[DiscoveredPlugin] = []
        self._current_plugin_path: Path | None = None

    # ------------------------------------------------------------------ #
    # Layout
    # ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with TabbedContent(initial="overview"):
            with TabPane("Overview", id="overview"):
                with Horizontal(id="stats-row"):
                    yield StatCard("Plugins loaded", "…")
                    yield StatCard("Findings", "…")
                    yield StatCard("Inventory assets", "…")
                with VerticalScroll():
                    yield Label("Environment diagnostics", classes="panel-title")
                    yield DataTable(id="doctor-table", cursor_type="row")
            with TabPane("Inventory", id="inventory"):
                with Horizontal(id="inventory-toolbar"):
                    yield Button("Refresh", id="refresh-inventory", variant="primary")
                    yield Button("Export HTML", id="export-inventory")
                    yield Button("Clear inventory", id="clear-inventory", classes="danger-button")
                yield DataTable(id="inventory-table", cursor_type="row")
            with TabPane("Scan", id="scan"):
                with Horizontal(id="scan-form"):
                    yield Select(
                        MODULE_CHOICES, id="module-select", value="audit.full", allow_blank=False
                    )
                    yield Input(placeholder="target: host, domain, URL, or CIDR", id="target-input")
                    yield Input(placeholder="ports (network.scan only)", id="ports-input")
                    yield Button("Run", id="run-scan", variant="primary")
                yield Label("", id="scan-status")
                yield DataTable(id="scan-table", cursor_type="row")
            with TabPane("Script", id="script"):
                with Horizontal(id="script-toolbar"):
                    yield Input(value="script.nyx", id="script-path")
                    yield Button("Browse…", id="script-browse")
                    yield Button("Open", id="script-open")
                    yield Button("Save", id="script-save")
                    yield Button("Lint", id="script-lint")
                    yield Button("Run", id="script-run-btn", variant="primary")
                with Horizontal(id="unsafe-row"):
                    yield Switch(value=False, id="unsafe-toggle")
                    yield Label("Unsafe: allow 'python:' blocks and 'pip' to actually run")
                yield Label("", id="script-status")
                yield NyxScriptEditor(SCRIPT_TEMPLATE, id="script-editor", tab_behavior="indent")
                yield CompletionPopup(id="completion-popup")
                yield RichLog(id="script-log", markup=True, wrap=True, highlight=False)
            with TabPane("Plugins", id="plugins"):
                with Horizontal(id="plugins-toolbar"):
                    yield Button("Reload list", id="reload-plugins", variant="primary")
                    yield Button("Save changes", id="plugin-save")
                    yield Input(placeholder="new plugin name (e.g. shodan)", id="new-plugin-name")
                    yield Button("Scaffold new plugin", id="plugin-new")
                yield DataTable(id="plugins-table", cursor_type="row")
                yield Label("Select a plugin above to view its source.", id="plugin-status")
                yield TextArea("", id="plugin-editor", language="python", read_only=True)
            with TabPane("About", id="about"):
                yield Static(id="about-body")
        yield Footer()

    def on_mount(self) -> None:
        for table_id, columns in (
            ("doctor-table", ("Severity", "Check", "Detail")),
            ("inventory-table", ("Kind", "Identifier", "Source", "Discovered")),
            ("scan-table", ("Severity", "Title", "Description")),
            ("plugins-table", ("Name", "Version", "Description")),
        ):
            table = self.query_one(f"#{table_id}", DataTable)
            table.add_columns(*columns)

        self._render_about()
        self.refresh_plugins_table()
        self.action_refresh_all()
        self.query_one("#script-status", Label).update(
            "[dim]Type to see completions ghosted in — press → to accept.[/]"
        )

    # ------------------------------------------------------------------ #
    # Actions / bindings
    # ------------------------------------------------------------------ #

    def action_refresh_all(self) -> None:
        self.refresh_doctor()
        self.refresh_inventory()

    def action_goto_overview(self) -> None:
        self.query_one(TabbedContent).active = "overview"

    def action_goto_inventory(self) -> None:
        self.query_one(TabbedContent).active = "inventory"

    def action_goto_scan(self) -> None:
        self.query_one(TabbedContent).active = "scan"

    def action_goto_script(self) -> None:
        self.query_one(TabbedContent).active = "script"

    def action_goto_plugins(self) -> None:
        self.query_one(TabbedContent).active = "plugins"

    def action_dismiss_popup(self) -> None:
        self.query_one("#completion-popup", CompletionPopup).display = False

    # ------------------------------------------------------------------ #
    # Overview tab
    # ------------------------------------------------------------------ #

    @work(exclusive=True, thread=False)
    async def refresh_doctor(self) -> None:
        result = run_diagnostics()
        table = self.query_one("#doctor-table", DataTable)
        table.clear()
        for finding in result.findings:
            table.add_row(_severity_text(finding.severity), finding.title, finding.description)

        plugin_count = len(discover_plugins(disabled=self.config.plugins.disabled))
        row = self.query_one("#stats-row", Horizontal)
        await row.remove_children()
        await row.mount(
            StatCard("Plugins loaded", str(plugin_count)),
            StatCard("Findings", str(len(result.findings))),
            StatCard("Inventory assets", str(len(self.inventory.list()))),
        )

    # ------------------------------------------------------------------ #
    # Inventory tab
    # ------------------------------------------------------------------ #

    def refresh_inventory(self) -> None:
        table = self.query_one("#inventory-table", DataTable)
        table.clear()
        assets = self.inventory.list()
        for asset in sorted(assets, key=lambda a: (a.kind, a.identifier)):
            table.add_row(
                asset.kind,
                asset.identifier,
                asset.source_module or "-",
                asset.discovered_at.strftime("%Y-%m-%d %H:%M"),
            )
        self.inventory_count = len(assets)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "refresh-inventory":
            self.refresh_inventory()
        elif event.button.id == "clear-inventory":
            self.inventory.clear()
            self.refresh_inventory()
            self.notify("Inventory cleared.", severity="warning")
        elif event.button.id == "export-inventory":
            self.export_inventory()
        elif event.button.id == "run-scan":
            self.run_scan()
        elif event.button.id == "script-browse":
            self.browse_for_script()
        elif event.button.id == "script-open":
            self.open_script()
        elif event.button.id == "script-save":
            self.save_script()
        elif event.button.id == "script-lint":
            self.lint_nyxscript()
        elif event.button.id == "script-run-btn":
            self.run_nyxscript()
        elif event.button.id == "reload-plugins":
            self.refresh_plugins_table()
        elif event.button.id == "plugin-save":
            self.save_plugin_source()
        elif event.button.id == "plugin-new":
            self.scaffold_plugin()

    def export_inventory(self) -> None:
        assets = self.inventory.list()
        if not assets:
            self.notify("Inventory is empty — nothing to export.", severity="warning")
            return

        document = ReportDocument(
            title="NYXOR Inventory Export",
            results=[ModuleResult(module="inventory", target="local", assets=assets)],
        )
        output_dir = Path(self.config.general.output_dir)
        path = output_dir / f"inventory-{datetime.now().strftime('%Y%m%d-%H%M%S')}.html"
        get_writer("html").write(document, path)
        self.notify(f"Exported {len(assets)} asset(s) to {path}", title="Export complete")

    # ------------------------------------------------------------------ #
    # Script tab — a small editor + runner for NyxScript files
    # ------------------------------------------------------------------ #

    def open_script(self) -> None:
        path = Path(self.query_one("#script-path", Input).value.strip())
        status = self.query_one("#script-status", Label)
        if not path.is_file():
            status.update(f"[bold #ff4d6d]Not found:[/] {path}")
            return
        self.query_one("#script-editor", TextArea).text = path.read_text(encoding="utf-8")
        status.update(f"[#2ecc71]Loaded[/] {path}")

    def browse_for_script(self) -> None:
        current = Path(self.query_one("#script-path", Input).value.strip())
        start_dir = current.parent if current.parent.is_dir() else Path.cwd()
        self.push_screen(ScriptBrowserScreen(start_dir), self._on_script_chosen)

    def _on_script_chosen(self, path: Path | None) -> None:
        if path is None:
            return
        try:
            display_path = path.relative_to(Path.cwd())
        except ValueError:
            display_path = path
        self.query_one("#script-path", Input).value = str(display_path)
        self.open_script()

    def save_script(self) -> None:
        path = Path(self.query_one("#script-path", Input).value.strip())
        status = self.query_one("#script-status", Label)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.query_one("#script-editor", TextArea).text, encoding="utf-8")
        status.update(f"[#2ecc71]Saved[/] {path}")

    def _write_lint_issues(self, log: RichLog, issues: list[LintIssue]) -> None:
        for issue in issues:
            color = "#ff4d6d" if issue.severity == "error" else "#f5d76e"
            log.write(f"[{color}]{issue.severity}[/] {issue}")

    def lint_nyxscript(self) -> None:
        source = self.query_one("#script-editor", TextArea).text
        log = self.query_one("#script-log", RichLog)
        status = self.query_one("#script-status", Label)
        log.clear()

        issues = lint_source(source)
        if not issues:
            log.write("[#2ecc71]No issues found.[/]")
            status.update("[#2ecc71]Lint clean.[/]")
            return

        self._write_lint_issues(log, issues)
        errors = sum(1 for issue in issues if issue.severity == "error")
        warnings = len(issues) - errors
        status.update(f"[bold #ff4d6d]{errors} error(s)[/], [#f5d76e]{warnings} warning(s)[/]")

    @work(exclusive=True, thread=False, group="script")
    async def run_nyxscript(self) -> None:
        source = self.query_one("#script-editor", TextArea).text
        log = self.query_one("#script-log", RichLog)
        status = self.query_one("#script-status", Label)
        log.clear()

        issues = lint_source(source)
        errors = [issue for issue in issues if issue.severity == "error"]
        if errors:
            self._write_lint_issues(log, issues)
            status.update("[bold #ff4d6d]Lint errors — fix them before running.[/]")
            return
        if issues:
            self._write_lint_issues(log, issues)

        unsafe = self.query_one("#unsafe-toggle", Switch).value
        if unsafe:
            log.write("[bold #ff9f43]Unsafe mode:[/] 'python:' and 'pip' will execute for real.")
        status.update("[#7ee7e1]Running…[/]")

        def emit(line: str) -> None:
            # This is raw script output (e.g. `print [1, 2, 3]`), not our own
            # Rich markup — escape it so the log widget (markup=True, for our
            # own "[bold]...[/]" status lines) renders a literal "[1, 2, 3]"
            # instead of trying to parse it as a style tag and eating it.
            log.write(escape_markup(line))

        # ui.confirm/input/select need the real terminal, which Textual is
        # currently holding onto — ScriptUI(app=self) wraps each of those in
        # App.suspend(), which hands the terminal back for just that prompt.
        ui = ScriptUI(app=self)

        try:
            await run_script(
                source, self.config, output=emit, base_dir=Path.cwd(), unsafe=unsafe, ui=ui
            )
        except ScriptError as exc:
            log.write(f"[bold #ff4d6d]Error:[/] {escape_markup(exc.reason)}")
            if exc.line is not None:
                lines = source.splitlines()
                if 1 <= exc.line <= len(lines):
                    snippet = lines[exc.line - 1]
                    gutter = f"{exc.line} | "
                    log.write(f"[dim]{gutter}[/]{escape_markup(snippet)}")
                    caret_col = len(snippet) - len(snippet.lstrip())
                    log.write(" " * (len(gutter) + caret_col) + "[bold #ff4d6d]^[/]")
            status.update("[bold #ff4d6d]Script failed.[/]")
            return
        except NyxorError as exc:
            log.write(f"[bold #ff4d6d]Error:[/] {exc.message}")
            status.update("[bold #ff4d6d]Script failed.[/]")
            return
        except Exception as exc:  # keep the TUI alive no matter what a script does
            log.write(f"[bold #ff4d6d]Unexpected error:[/] {exc}")
            status.update("[bold #ff4d6d]Script failed.[/]")
            return

        self.refresh_inventory()
        status.update("[#2ecc71]Script finished.[/]")

    # ------------------------------------------------------------------ #
    # Script tab — floating completion box
    # ------------------------------------------------------------------ #

    def on_text_area_changed(self, event: TextArea.Changed) -> None:
        if event.text_area.id == "script-editor":
            self._update_completion_popup()

    def _update_completion_popup(self) -> None:
        editor = self.query_one("#script-editor", NyxScriptEditor)
        popup = self.query_one("#completion-popup", CompletionPopup)
        _prefix, matches = editor.completion_context()

        if not matches:
            popup.display = False
            return

        popup.clear_options()
        for match in matches[:8]:
            popup.add_option(match)
        popup.display = True
        popup.absolute_offset = editor.cursor_screen_offset + Offset(0, 1)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id != "completion-popup":
            return
        editor = self.query_one("#script-editor", NyxScriptEditor)
        word = str(event.option.prompt)
        editor.insert_completion(word)
        self.query_one("#completion-popup", CompletionPopup).display = False
        editor.focus()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        self.query_one("#completion-popup", CompletionPopup).display = False

    # ------------------------------------------------------------------ #
    # Plugins tab — browse and lightly edit installed plugins' source
    # ------------------------------------------------------------------ #

    def refresh_plugins_table(self) -> None:
        table = self.query_one("#plugins-table", DataTable)
        table.clear()
        self._plugins = sorted(
            discover_plugins(disabled=self.config.plugins.disabled),
            key=lambda d: d.plugin.metadata.name,
        )
        for discovered in self._plugins:
            meta = discovered.plugin.metadata
            table.add_row(meta.name, meta.version, meta.description)

    @staticmethod
    def _plugin_source_path(discovered: DiscoveredPlugin) -> Path | None:
        try:
            return Path(inspect.getfile(type(discovered.plugin)))
        except (TypeError, OSError):
            return None

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id != "plugins-table":
            return
        index = event.cursor_row
        if index < 0 or index >= len(self._plugins):
            return
        discovered = self._plugins[index]
        path = self._plugin_source_path(discovered)
        editor = self.query_one("#plugin-editor", TextArea)
        status = self.query_one("#plugin-status", Label)

        if path is None or not path.is_file():
            editor.text = ""
            editor.read_only = True
            status.update(
                f"[yellow]No editable source found for {discovered.plugin.metadata.name}.[/]"
            )
            self._current_plugin_path = None
            return

        editor.text = path.read_text(encoding="utf-8")
        editor.read_only = False
        self._current_plugin_path = path
        status.update(f"Editing {path}  [dim](save requires a restart to take effect)[/]")

    def save_plugin_source(self) -> None:
        status = self.query_one("#plugin-status", Label)
        path = self._current_plugin_path
        if path is None:
            status.update("[yellow]Select a plugin first.[/]")
            return
        path.write_text(self.query_one("#plugin-editor", TextArea).text, encoding="utf-8")
        status.update(f"[#2ecc71]Saved[/] {path} [dim](restart `nyx tui` to reload it)[/]")

    def scaffold_plugin(self) -> None:
        status = self.query_one("#plugin-status", Label)
        raw_name = self.query_one("#new-plugin-name", Input).value.strip().lower()
        name = re.sub(r"[^a-z0-9_]+", "_", raw_name).strip("_")
        if not name:
            status.update("[bold #ff4d6d]Enter a plugin name first.[/]")
            return

        target_dir = Path.cwd() / "nyxor_plugins" / name
        target_dir.mkdir(parents=True, exist_ok=True)
        (target_dir / "__init__.py").touch(exist_ok=True)
        plugin_file = target_dir / "plugin.py"
        if plugin_file.exists():
            status.update(f"[yellow]{plugin_file} already exists.[/]")
            return

        class_name = "".join(part.capitalize() for part in name.split("_"))
        plugin_file.write_text(
            PLUGIN_SKELETON.format(name=name, class_name=class_name), encoding="utf-8"
        )
        status.update(
            f"[#2ecc71]Scaffolded[/] {plugin_file} — add an entry point under "
            f'[project.entry-points."nyxor.plugins"] and reinstall to load it.'
        )

    # ------------------------------------------------------------------ #
    # Scan tab
    # ------------------------------------------------------------------ #

    @work(exclusive=True, thread=False, group="scan")
    async def run_scan(self) -> None:
        module = self.query_one("#module-select", Select).value
        target = self.query_one("#target-input", Input).value.strip()
        ports = self.query_one("#ports-input", Input).value.strip()
        status = self.query_one("#scan-status", Label)
        table = self.query_one("#scan-table", DataTable)
        run_button = self.query_one("#run-scan", Button)

        if not target:
            status.update("[bold #ff4d6d]Enter a target first.[/]")
            return

        status.update(f"[#7ee7e1]Running {module} against {target}…[/]")
        run_button.disabled = True
        table.clear()

        try:
            results = await self._dispatch(str(module), target, ports)
        except Exception as exc:  # keep the TUI alive no matter what a module raises
            status.update(f"[bold #ff4d6d]Error:[/] {exc}")
            run_button.disabled = False
            return

        multi = len(results) > 1
        total_findings = 0
        all_assets = []
        all_errors = []
        for result in results:
            prefix = f"[dim]{result.module}[/] " if multi else ""
            for finding in result.findings:
                table.add_row(
                    _severity_text(finding.severity),
                    Text.from_markup(f"{prefix}{finding.title}"),
                    finding.description,
                )
            total_findings += len(result.findings)
            all_assets.extend(result.assets)
            all_errors.extend(result.errors)

        added = 0
        if all_assets:
            added = self.inventory.add(all_assets)
            self.refresh_inventory()

        if all_errors:
            status.update(f"[bold #ff4d6d]{'; '.join(all_errors)}[/]")
        else:
            status.update(
                f"[#2ecc71]Done.[/] {total_findings} finding(s), "
                f"{len(all_assets)} asset(s), {added} new in inventory."
            )
        run_button.disabled = False

    async def _dispatch(self, module: str, target: str, ports: str) -> list[ModuleResult]:
        if module == "network.discover":
            return [await network_run_discover(target, self.config.network)]
        if module == "network.scan":
            return [await network_run_scan(target, ports, self.config.network)]
        if module == "dns.lookup":
            return [
                await dns_run_lookup(
                    target, self.config.dns.resolvers, self.config.dns.timeout_seconds
                )
            ]
        if module == "tls.inspect":
            return [await tls_run_inspect(target, self.config.tls.timeout_seconds)]
        if module == "http.inspect":
            return [await http_run_inspect(target, self.config.http)]
        if module == "audit.full":
            return await run_audit(target, self.config)
        if module == "recon.subdomains":
            return await run_recon(target)
        raise ValueError(f"Unknown module: {module}")

    # ------------------------------------------------------------------ #
    # About tab
    # ------------------------------------------------------------------ #

    def _render_about(self) -> None:
        plugins = discover_plugins(disabled=self.config.plugins.disabled)
        lines = [
            f"[bold #7ee7e1]NYXOR[/] v{__version__}",
            "",
            "A modular, cross-platform security assessment and infrastructure",
            "auditing toolkit. Not a hacking framework — every check here is a",
            "safe, non-destructive observation (TCP-connect, DNS, TLS handshake,",
            "HTTP requests).",
            "",
            "[bold #b98cff]Installed plugins[/]",
        ]
        for discovered in sorted(plugins, key=lambda d: d.plugin.metadata.name):
            meta = discovered.plugin.metadata
            lines.append(f"  • [#7ee7e1]{meta.name}[/] v{meta.version} — {meta.description}")
        lines += [
            "",
            "[dim]q[/] quit   [dim]r[/] refresh   [dim]1/2/3[/] switch tabs",
        ]
        self.query_one("#about-body", Static).update("\n".join(lines))


def run() -> None:
    NyxorApp().run()
