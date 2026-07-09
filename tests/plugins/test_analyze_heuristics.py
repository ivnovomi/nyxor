from __future__ import annotations

from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.plugins.analyze.heuristics import summarize
from nyxor.plugins.analyze.ollama import build_prompt


def _result(module: str, *severities: Severity) -> ModuleResult:
    return ModuleResult(
        module=module,
        target="example.com",
        findings=[
            Finding(title=f"finding-{i}", severity=s, description="desc")
            for i, s in enumerate(severities)
        ],
    )


def test_summarize_with_no_findings_says_so() -> None:
    text = summarize("example.com", [_result("dns")])
    assert "no findings" in text
    assert "example.com" in text


def test_summarize_flags_high_priority_when_present() -> None:
    text = summarize("example.com", [_result("http", Severity.CRITICAL, Severity.INFO)])
    assert "high-priority" in text
    assert "critical" in text


def test_summarize_reports_clean_posture_for_info_only() -> None:
    text = summarize("example.com", [_result("dns", Severity.INFO, Severity.INFO)])
    assert "clean" in text


def test_summarize_lists_top_findings_ranked_by_severity() -> None:
    text = summarize(
        "example.com",
        [_result("http", Severity.LOW, Severity.CRITICAL, Severity.MEDIUM)],
    )
    lines = text.splitlines()
    top_items = [line for line in lines if line.strip().startswith("-")]
    assert top_items[0].startswith("  - [critical]")


def test_build_prompt_includes_domain_and_findings() -> None:
    prompt = build_prompt("example.com", [_result("dns", Severity.MEDIUM)])
    assert "example.com" in prompt
    assert "[medium]" in prompt
    assert "(dns)" in prompt


def test_build_prompt_handles_no_findings() -> None:
    prompt = build_prompt("example.com", [_result("dns")])
    assert "(no findings)" in prompt
