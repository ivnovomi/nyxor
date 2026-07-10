"""Report generation framework: structured documents rendered by pluggable writers."""

from __future__ import annotations

from nyxor.core.errors import ReportError
from nyxor.core.reporting.base import ReportWriter
from nyxor.core.reporting.document import ReportDocument
from nyxor.core.reporting.html_writer import HtmlReportWriter
from nyxor.core.reporting.json_writer import JsonReportWriter
from nyxor.core.reporting.markdown_writer import MarkdownReportWriter
from nyxor.core.reporting.sarif_writer import SarifReportWriter

WRITERS: dict[str, type[ReportWriter]] = {
    "json": JsonReportWriter,
    "markdown": MarkdownReportWriter,
    "html": HtmlReportWriter,
    "sarif": SarifReportWriter,
}


def get_writer(format_name: str) -> ReportWriter:
    try:
        return WRITERS[format_name]()
    except KeyError as exc:
        raise ReportError(
            f"Unknown report format: {format_name!r}",
            hint=f"Supported formats: {', '.join(sorted(WRITERS))}",
        ) from exc


__all__ = [
    "ReportDocument",
    "ReportWriter",
    "JsonReportWriter",
    "MarkdownReportWriter",
    "HtmlReportWriter",
    "SarifReportWriter",
    "get_writer",
    "WRITERS",
]
