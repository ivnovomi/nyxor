from __future__ import annotations

import pytest

from nyxor.api.app import _hostname_from_target


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "example.com"),
        ("example.com:443", "example.com"),
        ("https://example.com/path", "example.com"),
        ("http://example.com:8080/x?y=1", "example.com"),
        ("8.8.8.8", "8.8.8.8"),
        ("8.8.8.8:53", "8.8.8.8"),
        ("2001:4860:4860::8888", "2001:4860:4860::8888"),
        ("[::1]:443", "::1"),
        ("[2001:4860:4860::8888]:443", "2001:4860:4860::8888"),
    ],
)
def test_hostname_from_target(raw: str, expected: str) -> None:
    assert _hostname_from_target(raw) == expected


def test_audit_endpoint_rejects_loopback_literal(nyxor_test_client) -> None:
    resp = nyxor_test_client.get("/dns/127.0.0.1")
    assert resp.status_code == 400
    assert "non-public" in resp.json()["detail"]


def test_audit_endpoint_rejects_localhost_hostname(nyxor_test_client) -> None:
    resp = nyxor_test_client.get("/tls/localhost:443")
    assert resp.status_code == 400


def test_http_endpoint_rejects_metadata_ip(nyxor_test_client) -> None:
    resp = nyxor_test_client.get(
        "/http", params={"url": "http://169.254.169.254/latest/meta-data/"}
    )
    assert resp.status_code == 400


def test_audit_endpoint_rejects_private_ip_literal(nyxor_test_client) -> None:
    resp = nyxor_test_client.get("/dns/10.0.0.5")
    assert resp.status_code == 400


def test_http_endpoint_rejects_a_redirect_to_a_metadata_ip(nyxor_test_client, monkeypatch) -> None:
    # The initial URL is public and passes _ensure_public_target, but the
    # server it points at 302s to the cloud metadata address — the SSRF
    # guard must also apply to redirect hops, not just the request the
    # caller typed in.
    import httpx

    async def fake_get(self, url, **kwargs):  # noqa: ANN001
        if "169.254.169.254" in str(url):
            return httpx.Response(200, request=httpx.Request("GET", url))
        return httpx.Response(
            302,
            headers={"location": "http://169.254.169.254/latest/meta-data/"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    resp = nyxor_test_client.get("/http", params={"url": "https://public-redirector.example"})

    assert resp.status_code == 200  # errors are surfaced per-module, not as a hard failure
    body = resp.json()
    assert body["errors"]
    assert "169.254.169.254" in body["errors"][0]
    assert "non-public" in body["errors"][0]
