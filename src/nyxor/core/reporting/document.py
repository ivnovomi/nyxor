"""The single structured object every report writer renders from."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from nyxor.core.models import ModuleResult


class ReportDocument(BaseModel):
    """Aggregates one or more :class:`ModuleResult` objects into a report."""

    title: str = "NYXOR Report"
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    profile: str | None = None
    results: list[ModuleResult] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def finding_count(self) -> int:
        return sum(len(r.findings) for r in self.results)

    @property
    def asset_count(self) -> int:
        return sum(len(r.assets) for r in self.results)
