"""Environment diagnostics: the logic behind ``nyx doctor``.

Kept independent of Typer/Rich so it can be unit tested and reused (e.g. by
a future dashboard health-check endpoint).
"""

from __future__ import annotations

import importlib.util
import platform
import shutil
import sys
from importlib.metadata import entry_points

from nyxor.core.models import Finding, ModuleResult, Severity
from nyxor.core.plugins import PLUGIN_GROUP

REQUIRED_DEPENDENCIES = ("typer", "rich", "pydantic", "httpx", "dns", "cryptography", "structlog")
MIN_PYTHON = (3, 13)


def run_diagnostics() -> ModuleResult:
    """Run all environment checks and return them as a single ModuleResult."""
    result = ModuleResult(module="system.doctor", target=platform.node() or "localhost")

    result.findings.append(_check_python_version())
    result.findings.append(_check_platform())
    result.findings.append(_check_uv())
    for dep in REQUIRED_DEPENDENCIES:
        result.findings.append(_check_dependency(dep))
    result.findings.append(_check_plugins())

    return result


def _check_python_version() -> Finding:
    ok = sys.version_info[:2] >= MIN_PYTHON
    required = ".".join(map(str, MIN_PYTHON))
    return Finding(
        title="Python version",
        severity=Severity.INFO if ok else Severity.HIGH,
        description=f"Running Python {platform.python_version()} (requires >= {required}).",
        evidence={"version": platform.python_version(), "ok": ok},
        tags=("system",),
    )


def _check_platform() -> Finding:
    return Finding(
        title="Platform",
        severity=Severity.INFO,
        description=f"{platform.system()} {platform.release()} ({platform.machine()})",
        evidence={
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
        },
        tags=("system",),
    )


def _check_uv() -> Finding:
    path = shutil.which("uv")
    return Finding(
        title="uv package manager",
        severity=Severity.INFO if path else Severity.LOW,
        description=f"Found at {path}" if path else "`uv` was not found on PATH.",
        evidence={"path": path},
        tags=("system", "dependency"),
    )


def _check_dependency(module_name: str) -> Finding:
    found = importlib.util.find_spec(module_name) is not None
    return Finding(
        title=f"Dependency: {module_name}",
        severity=Severity.INFO if found else Severity.CRITICAL,
        description="Available." if found else "Missing — reinstall with `uv sync`.",
        evidence={"module": module_name, "available": found},
        tags=("system", "dependency"),
    )


def _check_plugins() -> Finding:
    count = len(list(entry_points(group=PLUGIN_GROUP)))
    return Finding(
        title="Registered plugins",
        severity=Severity.INFO if count else Severity.MEDIUM,
        description=f"{count} plugin(s) registered under the '{PLUGIN_GROUP}' entry-point group.",
        evidence={"count": count},
        tags=("system", "plugins"),
    )
