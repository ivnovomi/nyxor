"""Exception hierarchy shared across the Core and all plugins.

Every exception NYXOR raises intentionally should derive from
:class:`NyxorError` so the CLI can catch a single type at the top level and
render a clean, non-crashing message instead of a raw traceback.
"""

from __future__ import annotations


class NyxorError(Exception):
    """Base class for all expected NYXOR failures."""

    def __init__(self, message: str, *, hint: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.hint = hint


class ConfigError(NyxorError):
    """Raised when configuration loading, merging, or validation fails."""


class PluginError(NyxorError):
    """Raised when a plugin fails to load or register itself."""


class PluginNotFoundError(PluginError):
    """Raised when a requested plugin name is not registered."""


class ModuleExecutionError(NyxorError):
    """Raised when a module (e.g. network, dns, tls, http) fails to run."""


class ReportError(NyxorError):
    """Raised when report generation or serialization fails."""
