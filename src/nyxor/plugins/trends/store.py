"""Persistent per-domain history of security-grade scores.

Every `nyx trends <domain>` run (unless `--no-record`) appends one sample
so later runs can compute a real trend line instead of comparing two points
by eye.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict

from platformdirs import user_data_dir

APP_NAME = "nyxor"


class Sample(TypedDict):
    timestamp: str
    points: int
    grade: str


def default_trends_path() -> Path:
    return Path(user_data_dir(APP_NAME)) / "trends.json"


class TrendStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_trends_path()

    def _load(self) -> dict[str, list[Sample]]:
        if not self.path.is_file():
            return {}
        data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        return data

    def _save(self, data: dict[str, list[Sample]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def record(self, domain: str, points: int, grade: str) -> None:
        data = self._load()
        history = data.setdefault(domain, [])
        history.append(
            {"timestamp": datetime.now(UTC).isoformat(), "points": points, "grade": grade}
        )
        self._save(data)

    def history(self, domain: str, limit: int | None = None) -> list[Sample]:
        """
        Retrieve the recorded samples for a domain.
        
        Parameters:
        	domain (str): The domain whose history to retrieve.
        	limit (int | None): The maximum number of most recent samples to return. Values less than or equal to zero return the full history.
        
        Returns:
        	list[Sample]: The domain's recorded samples, limited to the most recent entries when applicable.
        """
        samples = self._load().get(domain, [])
        if limit is not None and limit > 0:
            samples = samples[-limit:]
        return samples

    def all_domains(self) -> dict[str, list[Sample]]:
        """
        Return the recorded history for every domain.
        
        Returns:
        	dict[str, list[Sample]]: A mapping of domain names to their recorded samples.
        """
        return self._load()

    def clear(self, domain: str) -> bool:
        """Remove all stored samples for a domain.
        
        Parameters:
            domain (str): The domain whose history should be removed.
        
        Returns:
            bool: `true` if the domain was found and removed, `false` otherwise.
        """
        data = self._load()
        if domain not in data:
            return False
        del data[domain]
        self._save(data)
        return True
