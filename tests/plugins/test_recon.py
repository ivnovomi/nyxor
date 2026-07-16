from __future__ import annotations

import httpx
import pytest

from nyxor.plugins.recon.plugin import run_recon
from nyxor.plugins.recon.sources import crtsh_subdomains

CRTSH_ENTRIES = [
    {"name_value": "example.com"},
    {"name_value": "*.example.com\napi.example.com"},
    {"name_value": "www.example.com\nWWW.EXAMPLE.COM"},  # dupe, different case
    {"name_value": "unrelated-domain.org"},  # not a subdomain of example.com
]


def _mock_transport(entries: list[dict[str, str]]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=entries)

    return httpx.MockTransport(handler)


async def test_crtsh_subdomains_parses_and_dedupes(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, url, params=None, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=CRTSH_ENTRIES, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    names = await crtsh_subdomains("example.com")

    assert names == {"example.com", "api.example.com", "www.example.com"}


async def test_crtsh_subdomains_excludes_other_domains(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, url, params=None, **kwargs):  # noqa: ANN001
        return httpx.Response(200, json=CRTSH_ENTRIES, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    names = await crtsh_subdomains("example.com")

    assert "unrelated-domain.org" not in names


@pytest.mark.parametrize(
    "mode",
    [
        "network-failure",
        "bad-json",
        # crt.sh (or a proxy in front of it) can return valid JSON that isn't
        # a list of certificate entries, e.g. a rate-limit response like
        # {"error": "..."} — this must not crash the whole recon run.
        "well-formed-but-unexpected-json",
    ],
)
async def test_crtsh_subdomains_returns_empty_set_on_failure_modes(
    monkeypatch: pytest.MonkeyPatch, mode: str
) -> None:
    async def fake_get(self, url, params=None, **kwargs):  # noqa: ANN001
        if mode == "network-failure":
            raise httpx.ConnectError("no route to host")
        if mode == "bad-json":
            return httpx.Response(200, text="not json", request=httpx.Request("GET", url))
        return httpx.Response(
            200, json={"error": "rate limited"}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    names = await crtsh_subdomains("example.com")

    assert names == set()


async def test_crtsh_subdomains_skips_non_dict_entries(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get(self, url, params=None, **kwargs):  # noqa: ANN001
        return httpx.Response(
            200,
            json=["not-a-dict", {"name_value": "api.example.com"}],
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    names = await crtsh_subdomains("example.com")

    assert names == {"api.example.com"}


async def test_run_recon_reports_an_error_when_nothing_is_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_crtsh(domain: str, timeout: float = 15.0) -> set[str]:
        return set()

    monkeypatch.setattr("nyxor.plugins.recon.plugin.crtsh_subdomains", fake_crtsh)

    results = await run_recon("example.com")

    assert len(results) == 1
    assert results[0].errors


async def test_run_recon_marks_live_vs_historical(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_crtsh(domain: str, timeout: float = 15.0) -> set[str]:
        return {"live.example.com", "dead.example.com"}

    async def fake_resolves(name: str, timeout: float, semaphore: object) -> bool:
        return name == "live.example.com"

    monkeypatch.setattr("nyxor.plugins.recon.plugin.crtsh_subdomains", fake_crtsh)
    monkeypatch.setattr("nyxor.plugins.recon.plugin._resolves", fake_resolves)

    results = await run_recon("example.com", resolve=True)
    findings = {f.title: f.evidence["live"] for f in results[0].findings}

    assert findings == {"live.example.com": True, "dead.example.com": False}


async def test_run_recon_skips_resolution_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_crtsh(domain: str, timeout: float = 15.0) -> set[str]:
        return {"sub.example.com"}

    monkeypatch.setattr("nyxor.plugins.recon.plugin.crtsh_subdomains", fake_crtsh)

    results = await run_recon("example.com", resolve=False)

    assert results[0].findings[0].evidence["live"] is None


async def test_run_recon_respects_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_crtsh(domain: str, timeout: float = 15.0) -> set[str]:
        return {f"sub{i}.example.com" for i in range(10)}

    monkeypatch.setattr("nyxor.plugins.recon.plugin.crtsh_subdomains", fake_crtsh)

    results = await run_recon("example.com", resolve=False, limit=3)

    assert len(results[0].findings) == 3
    assert results[0].raw_data["total_found"] == 10
