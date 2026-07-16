from __future__ import annotations

import pytest
from textual.widgets import DataTable

from nyxor.core.models import Severity
from nyxor.plugins.tui.app import MODULE_CHOICES, NyxorApp, _severity_text


def test_severity_text_uses_uppercase_label() -> None:
    text = _severity_text(Severity.CRITICAL)
    assert str(text) == "CRITICAL"


def test_module_choices_cover_every_domain_plugin() -> None:
    values = {value for _, value in MODULE_CHOICES}
    assert values == {
        "audit.full",
        "network.discover",
        "network.scan",
        "dns.lookup",
        "tls.inspect",
        "http.inspect",
        "recon.subdomains",
    }


@pytest.mark.asyncio
async def test_app_boots_and_populates_overview() -> None:
    app = NyxorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        doctor_table = app.query_one("#doctor-table", DataTable)
        assert doctor_table.row_count > 0


@pytest.mark.asyncio
async def test_tabs_are_switchable_via_bindings() -> None:
    app = NyxorApp()
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("2")
        await pilot.pause()
        from textual.widgets import TabbedContent

        assert app.query_one(TabbedContent).active == "inventory"


@pytest.mark.asyncio
async def test_running_a_scan_populates_results_and_inventory(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    from nyxor.core.models import Asset, Finding, ModuleResult
    from nyxor.plugins.inventory.store import InventoryStore

    async def fake_lookup(domain: str, resolvers: list[str], timeout: float) -> ModuleResult:
        result = ModuleResult(module="dns.lookup", target=domain)
        result.findings.append(Finding(title="A record(s)", description="93.184.216.34"))
        result.assets.append(
            Asset(kind="dns:a", identifier="93.184.216.34", source_module="dns.lookup")
        )
        return result

    monkeypatch.setattr("nyxor.plugins.tui.app.dns_run_lookup", fake_lookup)

    app = NyxorApp()
    app.inventory = InventoryStore(path=tmp_path / "inventory.json")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import Input, Select

        await pilot.press("3")  # switch to the Scan tab so its widgets are laid out
        await pilot.pause()
        app.query_one("#module-select", Select).value = "dns.lookup"
        app.query_one("#target-input", Input).value = "example.com"
        await pilot.click("#run-scan")
        await app.workers.wait_for_complete()
        await pilot.pause()

        scan_table = app.query_one("#scan-table", DataTable)
        assert scan_table.row_count == 1
        assert len(app.inventory.list()) == 1


@pytest.mark.asyncio
async def test_a_finding_title_containing_brackets_does_not_crash_the_scan_tab(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    # A title like "Unexpected [/redirect] found" is real Rich markup
    # syntax — unescaped, Text.from_markup either silently drops the
    # bracketed text or raises rich.errors.MarkupError.
    from nyxor.core.models import Finding, ModuleResult
    from nyxor.plugins.inventory.store import InventoryStore

    async def fake_lookup(domain: str, resolvers: list[str], timeout: float) -> ModuleResult:
        result = ModuleResult(module="dns.lookup", target=domain)
        result.findings.append(
            Finding(title="TXT record(s)", description="unexpected [/redirect] value present")
        )
        return result

    monkeypatch.setattr("nyxor.plugins.tui.app.dns_run_lookup", fake_lookup)

    app = NyxorApp()
    app.inventory = InventoryStore(path=tmp_path / "inventory.json")

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        from textual.widgets import Input, Select

        await pilot.press("3")
        await pilot.pause()
        app.query_one("#module-select", Select).value = "dns.lookup"
        app.query_one("#target-input", Input).value = "example.com"
        await pilot.click("#run-scan")
        await app.workers.wait_for_complete()
        await pilot.pause()

        scan_table = app.query_one("#scan-table", DataTable)
        assert scan_table.row_count == 1
        status = app.query_one("#scan-status")
        assert "Error" not in str(status.render())


@pytest.mark.asyncio
async def test_an_asset_identifier_containing_brackets_does_not_crash_the_inventory_tab(
    tmp_path,
) -> None:
    # asset.identifier can hold target-controlled data (e.g. a raw DNS TXT
    # record) that may contain square brackets — same DataTable markup-
    # parsing hazard as finding.title/description on the Scan tab.
    from rich.markup import escape as escape_markup
    from rich.text import Text
    from textual.coordinate import Coordinate

    from nyxor.core.models import Asset
    from nyxor.plugins.inventory.store import InventoryStore

    identifier = "weird [id] value"
    app = NyxorApp()
    app.inventory = InventoryStore(path=tmp_path / "inventory.json")
    app.inventory.add([Asset(kind="dns:txt", identifier=identifier, source_module="dns.lookup")])

    async with app.run_test() as pilot:
        await pilot.pause()
        app.refresh_inventory()

        inventory_table = app.query_one("#inventory-table", DataTable)
        assert inventory_table.row_count == 1
        # The identifier column is index 1 (kind, identifier, source, discovered_at).
        # DataTable stores the pre-render cell value, i.e. the escape_markup()'d
        # string ("weird \[id] value") — Rich only resolves that escape into a
        # literal "[" when it's actually rendered. Round-tripping the stored
        # value back through Text.from_markup (what DataTable itself does at
        # paint time) proves it displays as the original, unmangled text
        # rather than being corrupted or exploded into extra cells.
        identifier_cell = str(inventory_table.get_cell_at(Coordinate(0, 1)))
        assert identifier_cell == escape_markup(identifier)
        assert Text.from_markup(identifier_cell).plain == identifier
