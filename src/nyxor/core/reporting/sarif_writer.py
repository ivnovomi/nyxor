"""SARIF 2.1.0 output — the format GitHub Code Scanning, most CI security

dashboards, and tools like DefectDojo expect. `nyx audit example.com
--output results.sarif` (or any module command, or `nyx report convert
--to sarif`) turns findings into SARIF results that
`github/codeql-action/upload-sarif` can push straight into a repo's
Security tab as inline alerts — no separate conversion tool needed.
"""

from __future__ import annotations

import json
import re
from typing import Any

from nyxor import __version__
from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.core.reporting.base import ReportWriter
from nyxor.core.reporting.document import ReportDocument

# GitHub Code Scanning only recognizes these three SARIF levels.
_LEVEL_BY_SEVERITY = {
    Severity.CRITICAL: "error",
    Severity.HIGH: "error",
    Severity.MEDIUM: "warning",
    Severity.LOW: "note",
    Severity.INFO: "note",
}

# "security-severity" is a de facto GitHub extension (0.0-10.0) that
# ranks/colors alerts in the Security tab beyond SARIF's 3 levels.
_SCORE_BY_SEVERITY = {
    Severity.CRITICAL: "9.5",
    Severity.HIGH: "7.5",
    Severity.MEDIUM: "5.0",
    Severity.LOW: "2.5",
    Severity.INFO: "0.0",
}

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _rule_id(module: str, title: str) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-") or "finding"
    return f"nyxor/{module}/{slug}"


def _rule(module: str, finding: Finding) -> dict[str, Any]:
    return {
        "id": _rule_id(module, finding.title),
        "name": finding.title,
        "shortDescription": {"text": finding.title},
        "fullDescription": {"text": finding.description or finding.title},
        "defaultConfiguration": {"level": _LEVEL_BY_SEVERITY[finding.severity]},
        "properties": {
            "security-severity": _SCORE_BY_SEVERITY[finding.severity],
            "tags": list(finding.tags),
        },
    }


def _result(module: str, finding: Finding, module_target: str) -> dict[str, Any]:
    # SARIF results need at least one location; NYXOR's findings aren't
    # about a line in a file, so the "artifact" is the scanned target
    # itself (a hostname, "host:port", or URL) rather than a repo path.
    return {
        "ruleId": _rule_id(module, finding.title),
        "level": _LEVEL_BY_SEVERITY[finding.severity],
        "message": {"text": finding.description or finding.title},
        "locations": [
            {"physicalLocation": {"artifactLocation": {"uri": finding.target or module_target}}}
        ],
    }


def _build_sarif(results: list[ModuleResult]) -> dict[str, Any]:
    rules: dict[str, dict[str, Any]] = {}
    sarif_results: list[dict[str, Any]] = []

    for module_result in results:
        for finding in module_result.findings:
            rule = _rule(module_result.module, finding)
            rules.setdefault(rule["id"], rule)
            sarif_results.append(_result(module_result.module, finding, module_result.target))

    return {
        "$schema": (
            "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/"
            "Schemata/sarif-schema-2.1.0.json"
        ),
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "NYXOR",
                        "version": __version__,
                        "informationUri": "https://github.com/ivnovomi/nyxor",
                        "rules": list(rules.values()),
                    }
                },
                "results": sarif_results,
            }
        ],
    }


class SarifReportWriter(ReportWriter):
    format_name = "sarif"

    def render(self, document: ReportDocument) -> str:
        return json.dumps(_build_sarif(document.results), indent=2)
