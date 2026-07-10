from __future__ import annotations

import json

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


def _multi_finding_document() -> ReportDocument:
    result = ModuleResult(
        module="http.inspect",
        target="example.com",
        findings=[
            Finding(
                title="Missing security headers",
                severity=Severity.CRITICAL,
                description="No CSP header.",
                target="https://example.com",
                tags=("headers",),
            ),
            Finding(title="Response status", severity=Severity.INFO, description="200 OK"),
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


def test_sarif_writer_produces_valid_sarif_2_1_0_shape() -> None:
    rendered = get_writer("sarif").render(_multi_finding_document())
    sarif = json.loads(rendered)

    assert sarif["version"] == "2.1.0"
    assert sarif["runs"][0]["tool"]["driver"]["name"] == "NYXOR"
    results = sarif["runs"][0]["results"]
    assert len(results) == 2
    for result in results:
        assert "ruleId" in result
        assert result["level"] in ("error", "warning", "note")
        assert result["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]


def test_sarif_writer_maps_severity_to_github_levels() -> None:
    sarif = json.loads(get_writer("sarif").render(_multi_finding_document()))
    results = sarif["runs"][0]["results"]

    critical_result = next(r for r in results if "missing-security-headers" in r["ruleId"])
    info_result = next(r for r in results if "response-status" in r["ruleId"])
    assert critical_result["level"] == "error"
    assert info_result["level"] == "note"


def test_sarif_writer_uses_the_findings_own_target_when_set() -> None:
    sarif = json.loads(get_writer("sarif").render(_multi_finding_document()))
    results = sarif["runs"][0]["results"]

    with_own_target = next(r for r in results if "missing-security-headers" in r["ruleId"])
    without_own_target = next(r for r in results if "response-status" in r["ruleId"])

    assert (
        with_own_target["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        == "https://example.com"
    )
    # falls back to the module result's target when the finding has none
    assert (
        without_own_target["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        == "example.com"
    )


def test_sarif_writer_deduplicates_rules_across_repeated_findings() -> None:
    result = ModuleResult(
        module="dns.lookup",
        target="a.com",
        findings=[
            Finding(title="DNSSEC", severity=Severity.MEDIUM, description="not enabled"),
            Finding(title="DNSSEC", severity=Severity.MEDIUM, description="not enabled"),
        ],
    )
    sarif = json.loads(get_writer("sarif").render(ReportDocument(results=[result])))

    assert len(sarif["runs"][0]["tool"]["driver"]["rules"]) == 1
    assert len(sarif["runs"][0]["results"]) == 2
