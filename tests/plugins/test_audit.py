from __future__ import annotations

import pytest

from nyxor.core.config import load_config
from nyxor.core.models import ModuleResult
from nyxor.plugins.audit.plugin import _hostname_for_dns, run_audit


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "example.com"),
        ("example.com:8443", "example.com"),
        ("https://example.com/", "example.com"),
        ("https://example.com:8443/path", "example.com"),
        ("http://example.com", "example.com"),
    ],
)
def test_hostname_for_dns(raw: str, expected: str) -> None:
    assert _hostname_for_dns(raw) == expected


async def test_run_audit_resolves_a_bare_hostname_for_dns_given_a_full_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: `nyx audit https://example.com/` used to crash inside
    # tls.inspect's target parser, and (once that's fixed) DNS would still
    # silently look up the literal string "https://example.com/" instead
    # of "example.com". Assert DNS gets the bare hostname it needs.
    seen_dns_target = None

    async def fake_dns_run_lookup(
        domain: str, resolvers: list[str], timeout: float
    ) -> ModuleResult:
        nonlocal seen_dns_target
        seen_dns_target = domain
        return ModuleResult(module="dns.lookup", target=domain)

    async def fake_tls_run_inspect(target: str, timeout: float) -> ModuleResult:
        return ModuleResult(module="tls.inspect", target=target)

    async def fake_http_run_inspect(url: str, config: object) -> ModuleResult:
        return ModuleResult(module="http.inspect", target=url)

    monkeypatch.setattr("nyxor.plugins.audit.plugin.dns_run_lookup", fake_dns_run_lookup)
    monkeypatch.setattr("nyxor.plugins.audit.plugin.tls_run_inspect", fake_tls_run_inspect)
    monkeypatch.setattr("nyxor.plugins.audit.plugin.http_run_inspect", fake_http_run_inspect)

    await run_audit("https://example.com/", load_config())

    assert seen_dns_target == "example.com"
