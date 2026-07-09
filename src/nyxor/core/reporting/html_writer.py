from __future__ import annotations

from jinja2 import Environment, select_autoescape

from nyxor.core.reporting.base import ReportWriter
from nyxor.core.reporting.document import ReportDocument

_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{{ document.title }}</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 2rem; color: #1a1a1a; }
  h1 { margin-bottom: 0.25rem; }
  .meta { color: #666; margin-bottom: 1.5rem; }
  .module { border: 1px solid #ddd; border-radius: 8px; padding: 1rem 1.25rem; margin-bottom: 1.25rem; }
  table { border-collapse: collapse; width: 100%; margin-top: 0.5rem; }
  th, td { text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #eee; font-size: 0.9rem; }
  .sev-critical { color: #b00020; font-weight: 600; }
  .sev-high { color: #d16b00; font-weight: 600; }
  .sev-medium { color: #a68b00; }
  .sev-low { color: #2a6f2a; }
  .sev-info { color: #555; }
  .errors { color: #b00020; }
</style>
</head>
<body>
  <h1>{{ document.title }}</h1>
  <div class="meta">
    Generated {{ document.generated_at.isoformat() }}
    {% if document.profile %}&middot; profile <code>{{ document.profile }}</code>{% endif %}
    &middot; {{ document.results|length }} module run(s)
    &middot; {{ document.finding_count }} finding(s)
    &middot; {{ document.asset_count }} asset(s)
  </div>

  {% for result in document.results %}
  <div class="module">
    <h2>{{ result.module }} &mdash; {{ result.target }}</h2>
    {% if result.errors %}
    <div class="errors">
      <strong>Errors:</strong>
      <ul>{% for err in result.errors %}<li>{{ err }}</li>{% endfor %}</ul>
    </div>
    {% endif %}
    {% if result.findings %}
    <table>
      <thead><tr><th>Severity</th><th>Title</th><th>Description</th></tr></thead>
      <tbody>
        {% for finding in result.findings %}
        <tr>
          <td class="sev-{{ finding.severity.value }}">{{ finding.severity.value }}</td>
          <td>{{ finding.title }}</td>
          <td>{{ finding.description }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p><em>No findings.</em></p>
    {% endif %}
    {% if result.assets %}
    <p><strong>Assets:</strong></p>
    <ul>{% for asset in result.assets %}<li><code>{{ asset.kind }}</code>: {{ asset.identifier }}</li>{% endfor %}</ul>
    {% endif %}
  </div>
  {% endfor %}
</body>
</html>
"""


class HtmlReportWriter(ReportWriter):
    format_name = "html"

    def __init__(self) -> None:
        self._env = Environment(autoescape=select_autoescape(["html"]))
        self._template = self._env.from_string(_TEMPLATE)

    def render(self, document: ReportDocument) -> str:
        return self._template.render(document=document)
