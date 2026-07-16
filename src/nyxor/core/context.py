"""The object every plugin command receives: shared config, logging, and
output preferences for the current invocation.

Passing this explicitly (rather than reaching for globals) is what keeps
modules independently testable — a test can construct a ``NyxorContext``
pointed at a temp directory without touching the real CLI.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from rich.console import Console
from structlog.stdlib import BoundLogger

from nyxor.core.config import NyxorConfig
from nyxor.core.logging import get_logger


@dataclass
class OutputOptions:
    """Resolved from the ``--json`` / ``--yaml`` / ``--output`` / ``--verbose`` flags."""

    format: str = "table"  # "table" | "json" | "yaml"
    output_path: Path | None = None
    verbose: bool = False


@dataclass
class NyxorContext:
    config: NyxorConfig
    console: Console = field(default_factory=Console)
    error_console: Console = field(default_factory=lambda: Console(stderr=True))
    output: OutputOptions = field(default_factory=OutputOptions)

    def get_logger(self, name: str) -> BoundLogger:
        return get_logger(name)
