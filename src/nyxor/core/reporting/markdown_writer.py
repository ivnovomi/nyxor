from __future__ import annotations

from nyxor.core.reporting.base import ReportWriter
from nyxor.core.reporting.document import ReportDocument


class MarkdownReportWriter(ReportWriter):
    format_name = "markdown"

    def render(self, document: ReportDocument) -> str:
        lines: list[str] = [
            f"# {document.title}",
            "",
            f"Generated: {document.generated_at.isoformat()}",
        ]
        if document.profile:
            lines.append(f"Profile: `{document.profile}`")
        lines += [
            "",
            f"**{len(document.results)}** module run(s), "
            f"**{document.finding_count}** finding(s), "
            f"**{document.asset_count}** asset(s).",
            "",
        ]

        for result in document.results:
            lines.append(f"## {result.module} — {result.target}")
            lines.append("")
            if result.errors:
                lines.append("**Errors:**")
                lines += [f"- {err}" for err in result.errors]
                lines.append("")

            if result.findings:
                lines.append("| Severity | Title | Description |")
                lines.append("|---|---|---|")
                for finding in result.findings:
                    desc = finding.description.replace("|", "\\|").replace("\n", " ")
                    lines.append(f"| {finding.severity.value} | {finding.title} | {desc} |")
                lines.append("")
            else:
                lines.append("_No findings._")
                lines.append("")

            if result.assets:
                lines.append("**Assets:**")
                for asset in result.assets:
                    lines.append(f"- `{asset.kind}`: {asset.identifier}")
                lines.append("")

        return "\n".join(lines)
