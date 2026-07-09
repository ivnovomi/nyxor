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
