from __future__ import annotations

from nyxor.core.models import Severity
from nyxor.plugins.system.doctor import run_diagnostics


def test_run_diagnostics_reports_python_version() -> None:
    result = run_diagnostics()

    titles = [f.title for f in result.findings]
    assert "Python version" in titles
    assert result.module == "system.doctor"


def test_run_diagnostics_flags_missing_dependency(monkeypatch) -> None:
    import nyxor.plugins.system.doctor as doctor_module

    monkeypatch.setattr(doctor_module, "REQUIRED_DEPENDENCIES", ("definitely_not_a_real_module",))

    result = run_diagnostics()

    missing = next(
        f for f in result.findings if f.title == "Dependency: definitely_not_a_real_module"
    )
    assert missing.severity == Severity.CRITICAL
