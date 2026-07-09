from __future__ import annotations

from nyxor.core.reporting.base import ReportWriter
from nyxor.core.reporting.document import ReportDocument


class JsonReportWriter(ReportWriter):
    format_name = "json"

    def render(self, document: ReportDocument) -> str:
        return document.model_dump_json(indent=2)
