from __future__ import annotations

from nyxor.core.models import Asset, Finding, ModuleResult, Severity


def test_finding_defaults() -> None:
    finding = Finding(title="Something")
    assert finding.severity == Severity.INFO
    assert finding.evidence == {}
    assert finding.id is not None


def test_module_result_ok_reflects_errors() -> None:
    result = ModuleResult(module="dns.lookup", target="example.com")
    assert result.ok is True

    result.errors.append("timeout")
    assert result.ok is False


def test_asset_is_frozen() -> None:
    asset = Asset(kind="host", identifier="10.0.0.1")
    try:
        asset.identifier = "10.0.0.2"  # type: ignore[misc]
        raised = False
    except Exception:
        raised = True
    assert raised
