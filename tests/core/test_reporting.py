from __future__ import annotations

import pytest

from nyxor.core.errors import ReportError
from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.core.reporting import ReportDocument, get_writer


def _sample_document() -> ReportDocument:
    result = ModuleResult(
        module="dns.lookup",
        target="example.com",
        findings=[
            Finding(title="A record(s)", severity=Severity.INFO, description="93.184.216.34")
        ],
    )
    return ReportDocument(title="Test Report", results=[result])


def test_json_writer_round_trips() -> None:
    document = _sample_document()
    writer = get_writer("json")
    rendered = writer.render(document)

    restored = ReportDocument.model_validate_json(rendered)
    assert restored.results[0].module == "dns.lookup"


def test_markdown_writer_includes_findings() -> None:
    writer = get_writer("markdown")
    rendered = writer.render(_sample_document())

    assert "# Test Report" in rendered
    assert "A record(s)" in rendered


def test_html_writer_escapes_and_includes_findings() -> None:
    writer = get_writer("html")
    rendered = writer.render(_sample_document())

    assert "<html" in rendered
    assert "A record(s)" in rendered


def test_get_writer_rejects_unknown_format() -> None:
    with pytest.raises(ReportError):
        get_writer("pdf")


def test_write_creates_parent_directories(tmp_path) -> None:
    writer = get_writer("json")
    target = tmp_path / "nested" / "report.json"

    writer.write(_sample_document(), target)

    assert target.is_file()
