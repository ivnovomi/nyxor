"""Turns a set of findings into a single, at-a-glance security grade.

Not a rigorous scoring methodology — a deliberately simple, transparent one
in the spirit of SSL Labs' letter grades: start at 100 points, subtract a
fixed penalty per finding by severity, floor at 0, map to a letter. Good
enough for "did this get better or worse since last time", which is the
job it's actually used for (`nyx audit`, `nyx watch`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from xml.sax.saxutils import escape as xml_escape

from rich.text import Text

from nyxor.core.models import ModuleResult, Severity

_PENALTY: dict[Severity, int] = {
    Severity.CRITICAL: 30,
    Severity.HIGH: 15,
    Severity.MEDIUM: 6,
    Severity.LOW: 2,
    Severity.INFO: 0,
}

_GRADE_THRESHOLDS: tuple[tuple[int, str], ...] = (
    (97, "A+"),
    (93, "A"),
    (90, "A-"),
    (87, "B+"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
)

GRADE_COLOR: dict[str, str] = {
    "A+": "#2ecc71",
    "A": "#2ecc71",
    "A-": "#7ee7e1",
    "B+": "#7ee7e1",
    "B": "#f5d76e",
    "C": "#ff9f43",
    "D": "#ff6b4a",
    "F": "#ff4d6d",
}


_SEVERITY_ORDER = list(Severity)


@dataclass(frozen=True)
class SecurityScore:
    points: int
    grade: str
    finding_counts: dict[Severity, int] = field(default_factory=dict)

    @property
    def color(self) -> str:
        return GRADE_COLOR[self.grade]

    @property
    def worst_severity(self) -> Severity | None:
        """The single worst severity with at least one finding, or ``None``

        if there are no findings at all.
        """
        for severity in reversed(_SEVERITY_ORDER):
            if self.finding_counts.get(severity, 0) > 0:
                return severity
        return None

    def meets_or_exceeds(self, threshold: Severity) -> bool:
        """True if the worst finding is at least as severe as ``threshold``

        (e.g. for a ``--fail-on high`` CI gate).
        """
        worst = self.worst_severity
        if worst is None:
            return False
        return _SEVERITY_ORDER.index(worst) >= _SEVERITY_ORDER.index(threshold)


def score_results(results: list[ModuleResult]) -> SecurityScore:
    """Compute a letter grade from every finding across ``results``."""
    counts: dict[Severity, int] = dict.fromkeys(Severity, 0)
    points = 100
    for result in results:
        for finding in result.findings:
            counts[finding.severity] += 1
            points -= _PENALTY[finding.severity]
    points = max(points, 0)
    grade = next(letter for threshold, letter in _GRADE_THRESHOLDS if points >= threshold)
    return SecurityScore(points=points, grade=grade, finding_counts=counts)


def render_badge(score: SecurityScore, *, label: str = "security") -> str:
    """Render a shields.io-style flat SVG badge for ``score`` (e.g. "security: A+")."""
    value = score.grade
    # Widths are computed from the raw (unescaped) lengths so the layout
    # isn't thrown off by entity expansion — only the text actually written
    # into the SVG needs escaping.
    label_width = int(len(label) * 6.5) + 20
    value_width = int(len(value) * 7.5) + 20
    total_width = label_width + value_width
    color = score.color
    label_x = label_width / 2
    value_x = label_width + value_width / 2

    # `label` can be attacker-controlled (e.g. the REST API's
    # /badge/{domain}.svg passes the raw URL path segment) — escape before
    # interpolating into XML/SVG to prevent markup/script injection. Both
    # land inside a double-quoted attribute (aria-label) as well as text
    # content, so quotes need escaping too, not just the default `&<>`.
    _attr_entities = {'"': "&quot;", "'": "&apos;"}
    safe_label = xml_escape(label, _attr_entities)
    safe_value = xml_escape(value, _attr_entities)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="20" \
role="img" aria-label="{safe_label}: {safe_value}">
  <linearGradient id="s" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="r"><rect width="{total_width}" height="20" rx="3" fill="#fff"/></clipPath>
  <g clip-path="url(#r)">
    <rect width="{label_width}" height="20" fill="#2b2f3a"/>
    <rect x="{label_width}" width="{value_width}" height="20" fill="{color}"/>
    <rect width="{total_width}" height="20" fill="url(#s)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,sans-serif" font-size="11">
    <text x="{label_x}" y="14">{safe_label}</text>
    <text x="{value_x}" y="14">{safe_value}</text>
  </g>
</svg>
"""


def render_terminal_badge(score: SecurityScore, *, label: str = "security") -> Text:
    """A shields.io-style pill badge for the terminal — same colors as

    :func:`render_badge`'s SVG, rendered with Rich truecolor backgrounds
    instead of `<rect>` elements. Plain color blocks rather than rounded
    Nerd Font/Powerline glyphs on purpose: those need a patched font the
    user's terminal may not have, and would show as broken boxes instead.
    """
    badge = Text()
    badge.append(f" {label} ", style="bold white on #2b2f3a")
    badge.append(f" {score.grade} ", style=f"bold #14171a on {score.color}")
    return badge
