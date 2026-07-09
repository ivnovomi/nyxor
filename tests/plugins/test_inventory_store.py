from __future__ import annotations

from pathlib import Path

from nyxor.core.models import Asset
from nyxor.plugins.inventory.store import InventoryStore


def test_add_and_list_round_trips(tmp_path: Path) -> None:
    store = InventoryStore(path=tmp_path / "inventory.json")
    asset = Asset(kind="host", identifier="10.0.0.1")

    added = store.add([asset])

    assert added == 1
    assets = store.list()
    assert len(assets) == 1
    assert assets[0].identifier == "10.0.0.1"


def test_add_deduplicates_by_kind_and_identifier(tmp_path: Path) -> None:
    store = InventoryStore(path=tmp_path / "inventory.json")
    asset = Asset(kind="host", identifier="10.0.0.1")

    store.add([asset])
    added_again = store.add([Asset(kind="host", identifier="10.0.0.1")])

    assert added_again == 0
    assert len(store.list()) == 1


def test_clear_empties_the_store(tmp_path: Path) -> None:
    store = InventoryStore(path=tmp_path / "inventory.json")
    store.add([Asset(kind="host", identifier="10.0.0.1")])

    store.clear()

    assert store.list() == []
