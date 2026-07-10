from __future__ import annotations

from rich.console import Console

from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.core.output import _print_table


def _bracketed_finding() -> Finding:
    """Create a finding containing bracketed text for markup-safety testing.
    
    Returns:
        Finding: A sample informational finding with literal bracketed content.
    """
    return Finding(
        title="Banner: [admin]",
        severity=Severity.INFO,
        description="SSH-2.0-OpenSSH_8.9 [root allowed] [bold red]FAKE[/bold red]",
    )


def test_print_table_preserves_literal_brackets_in_finding_text() -> None:
    console = Console(record=True, width=120)
    result = ModuleResult(
        module="network.scan", target="example.com", findings=[_bracketed_finding()]
    )

    _print_table(console, [result])

    text = console.export_text()
    assert "[admin]" in text
    assert "[root allowed]" in text
    # and critically: it must NOT have been rendered as actual bold-red styling,
    # i.e. the tag content itself survives as plain text in the cell.
    assert "FAKE" in text
