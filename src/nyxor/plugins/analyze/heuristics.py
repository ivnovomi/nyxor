"""A deterministic, no-model fallback summary.

Used whenever there's no local LLM to ask (Ollama not running) and the user
hasn't got Cloud. Not "AI" — just a plain-English rollup of what the rule
engine already knows, so `nyx analyze` is never a dead end.
"""

from __future__ import annotations

from nyxor.core.models import ModuleResult, Severity

_SEVERITY_WEIGHT = {
    Severity.CRITICAL: 4,
    Severity.HIGH: 3,
    Severity.MEDIUM: 2,
    Severity.LOW: 1,
    Severity.INFO: 0,
}


def summarize(domain: str, results: list[ModuleResult]) -> str:
    findings = [(result.module, finding) for result in results for finding in result.findings]

    if not findings:
        return f"{domain}: no findings recorded across {len(results)} module(s)."

    counts: dict[Severity, int] = {}
    for _module, finding in findings:
        counts[finding.severity] = counts.get(finding.severity, 0) + 1

    ranked = sorted(findings, key=lambda pair: _SEVERITY_WEIGHT[pair[1].severity], reverse=True)
    top = ranked[:3]

    lines = [f"{domain}: {len(findings)} finding(s) across {len(results)} module(s)."]

    breakdown = ", ".join(
        f"{count} {severity.value}"
        for severity, count in sorted(
            counts.items(), key=lambda item: _SEVERITY_WEIGHT[item[0]], reverse=True
        )
    )
    lines.append(f"Breakdown: {breakdown}.")

    worst_severity = ranked[0][1].severity
    if worst_severity in (Severity.CRITICAL, Severity.HIGH):
        lines.append("At least one high-priority issue needs attention before anything else.")
    elif worst_severity == Severity.MEDIUM:
        lines.append("Nothing critical, but a few things are worth fixing.")
    else:
        lines.append("Posture looks clean — only informational findings.")

    lines.append("Top items:")
    for module, finding in top:
        lines.append(f"  - [{finding.severity.value}] ({module}) {finding.title}")

    return "\n".join(lines)
