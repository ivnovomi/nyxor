"""Shared data models produced and consumed by every module.

Modules never return ad-hoc dicts to the Core — they return these Pydantic
models, which is what makes the reporting framework format-agnostic: any
writer (JSON, Markdown, HTML, future PDF) only ever has to know how to
render a :class:`ModuleResult`.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    """Relative importance of a finding, used for sorting and filtering."""

    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Finding(BaseModel):
    """A single observation produced by a module.

    Findings are informational by design (NYXOR is an auditing platform,
    not an exploitation framework) — they describe what was observed, not
    an exploit outcome.
    """

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    title: str
    severity: Severity = Severity.INFO
    description: str = ""
    target: str | None = None
    evidence: dict[str, Any] = Field(default_factory=dict)
    tags: tuple[str, ...] = ()


class Asset(BaseModel):
    """A discovered piece of infrastructure (host, service, domain, ...)."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4)
    kind: str
    identifier: str
    attributes: dict[str, Any] = Field(default_factory=dict)
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    source_module: str | None = None


class ModuleResult(BaseModel):
    """The structured output of a single module run.

    This is the unit the reporting framework operates on: every report is
    ultimately a collection of ``ModuleResult`` objects.
    """

    module: str
    target: str
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    findings: list[Finding] = Field(default_factory=list)
    assets: list[Asset] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict)
    errors: list[str] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors
