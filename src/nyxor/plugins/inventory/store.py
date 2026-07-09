"""A minimal, dependency-free asset inventory backed by a JSON file.

This is intentionally the simplest thing that could work for an MVP; a
database-backed store (see the project's future-expansion goals) can
implement the same interface without touching any plugin that uses it.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

from nyxor.core.models import Asset

APP_NAME = "nyxor"


def default_inventory_path() -> Path:
    return Path(user_data_dir(APP_NAME)) / "inventory.json"


class InventoryStore:
    """Deduplicated (kind, identifier) storage of discovered assets."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_inventory_path()

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        data: list[dict[str, Any]] = json.loads(self.path.read_text(encoding="utf-8"))
        return data

    def _save(self, records: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")

    def add(self, assets: list[Asset]) -> int:
        """Add new assets, skipping ones already present. Returns count added."""
        records = self._load()
        existing = {(r["kind"], r["identifier"]) for r in records}
        added = 0
        for asset in assets:
            key = (asset.kind, asset.identifier)
            if key in existing:
                continue
            records.append(json.loads(asset.model_dump_json()))
            existing.add(key)
            added += 1
        if added:
            self._save(records)
        return added

    def list(self) -> list[Asset]:
        return [Asset.model_validate(r) for r in self._load()]

    def clear(self) -> None:
        self._save([])
