"""Structured logging setup shared by the Core and every plugin.

Two renderers are supported: a human-friendly Rich console renderer for
interactive use, and a JSON renderer for machine consumption (``--json`` /
CI pipelines). Modules never configure logging themselves — they only ever
call :func:`get_logger`.
"""

from __future__ import annotations

import logging
import sys

import structlog
from rich.console import Console

_CONFIGURED = False


def configure_logging(
    *, level: str = "INFO", json_output: bool = False, console: Console | None = None
) -> None:
    """Configure structlog + stdlib logging. Safe to call multiple times."""
    global _CONFIGURED

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stderr,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_output:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=console is None or console.is_terminal)

    structlog.configure(
        processors=[*shared_processors, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, renderer],
        foreign_pre_chain=shared_processors,
    )
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Third-party libraries are chatty at INFO; keep them quiet unless the
    # user explicitly asked for debug output.
    if level.upper() != "DEBUG":
        for noisy in ("httpx", "httpcore"):
            logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a structured logger bound to ``name`` (typically ``__name__``)."""
    if not _CONFIGURED:
        configure_logging()
    logger: structlog.stdlib.BoundLogger = structlog.get_logger(name)
    return logger
