"""Report writer contract. Adding a new output format (e.g. PDF) means
implementing this one class — nothing else in the Core changes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from nyxor.core.reporting.document import ReportDocument


class ReportWriter(ABC):
    """Renders a :class:`ReportDocument` to a specific output format."""

    format_name: str

    @abstractmethod
    def render(self, document: ReportDocument) -> str:
        """Return the report as a string."""

    def write(self, document: ReportDocument, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.render(document), encoding="utf-8")
        return path
