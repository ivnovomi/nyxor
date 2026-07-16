from __future__ import annotations

import asyncio
import socket

import pytest

from nyxor.api.app import _ensure_public_target, _hostname_from_target


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


def test_audit_endpoint_rejects_cgnat_shared_address_space(nyxor_test_client) -> None:
    # 100.64.0.0/10 (RFC 6598) is neither is_private nor is_global in Python's
    # ipaddress module — it routes to cloud-internal infra (AWS ENIs, etc.)
    # and must still be blocked.
    resp = nyxor_test_client.get("/dns/100.64.0.1")
    assert resp.status_code == 400
    assert "non-public" in resp.json()["detail"]


async def test_ensure_public_target_returns_none_for_a_literal_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A literal address involves no DNS resolution to pin -- connecting to
    # it directly *is* the validated address.
    assert await _ensure_public_target("8.8.8.8") is None


async def test_ensure_public_target_returns_the_resolved_ip_to_pin_to(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_getaddrinfo(host: str, port: object) -> list[tuple]:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)

    assert await _ensure_public_target("example.com") == "93.184.216.34"


async def test_dns_rebinding_cannot_bypass_the_guard_via_a_second_resolution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The classic DNS-rebinding attack: a nameserver with a very short TTL
    # answers the *first* lookup (the one this SSRF check performs) with a
    # public address, then a *second*, independent lookup — the one the
    # actual connection would normally trigger on its own — with a private
    # one. If the connection re-resolves the hostname instead of reusing
    # the address this check already validated, the attacker wins.
    import httpx

    from nyxor.plugins.http_.inspector import inspect

    call_count = 0

    async def fake_getaddrinfo(host: str, port: object) -> list[tuple]:
        nonlocal call_count
        call_count += 1
        # First call (the only one that should ever happen): a public IP.
        # Any further call returning a private one would mean the guard
        # was bypassed by a second resolution.
        ip = "93.184.216.34" if call_count == 1 else "127.0.0.1"
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", fake_getaddrinfo)

    seen_requests: list[tuple[str, dict]] = []

    class _FakeStream:
        def __init__(self, response: httpx.Response) -> None:
            self._response = response

        async def __aenter__(self) -> httpx.Response:
            return self._response

        async def __aexit__(self, *exc_info: object) -> None:
            return None

    def fake_stream(self, method, url, **kwargs):  # noqa: ANN001
        seen_requests.append((str(url), kwargs))
        return _FakeStream(httpx.Response(200, request=httpx.Request(method, url)))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    await inspect(
        "https://rebinding.example/",
        timeout=5.0,
        follow_redirects=True,
        max_redirects=5,
        validate_url=_ensure_public_target,
    )

    # Only the one resolution this SSRF check itself performed — the actual
    # connection must not have triggered a second, independent lookup.
    assert call_count == 1
    assert len(seen_requests) == 1
    url, kwargs = seen_requests[0]
    assert url.startswith("https://93.184.216.34")
    assert kwargs["headers"]["Host"] == "rebinding.example"
    assert kwargs["extensions"]["sni_hostname"] == "rebinding.example"


def test_http_endpoint_rejects_a_redirect_to_a_metadata_ip(nyxor_test_client, monkeypatch) -> None:
    # The initial URL is public and passes _ensure_public_target, but the
    # server it points at 302s to the cloud metadata address — the SSRF
    # guard must also apply to redirect hops, not just the request the
    # caller typed in.
    import httpx

    class _FakeStream:
        def __init__(self, response: httpx.Response) -> None:
            self._response = response

        async def __aenter__(self) -> httpx.Response:
            return self._response

        async def __aexit__(self, *exc_info: object) -> None:
            return None

    def fake_stream(self, method, url, **kwargs):  # noqa: ANN001
        if "169.254.169.254" in str(url):
            return _FakeStream(httpx.Response(200, request=httpx.Request(method, url)))
        return _FakeStream(
            httpx.Response(
                302,
                headers={"location": "http://169.254.169.254/latest/meta-data/"},
                request=httpx.Request(method, url),
            )
        )

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    resp = nyxor_test_client.get("/http", params={"url": "https://public-redirector.example"})

    assert resp.status_code == 200  # errors are surfaced per-module, not as a hard failure
    body = resp.json()
    assert body["errors"]
    assert "169.254.169.254" in body["errors"][0]
    assert "non-public" in body["errors"][0]
