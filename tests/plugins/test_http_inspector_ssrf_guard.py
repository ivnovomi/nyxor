from __future__ import annotations

import httpx2 as httpx
import pytest

from nyxor.plugins.http_.inspector import _pin_url_to_ip, inspect
from tests._http_mocks import FakeStream


def test_pin_url_to_ip_fails_fast_on_a_url_with_no_hostname() -> None:
    # _pin_url_to_ip is only ever called with a pinned IP already in hand,
    # which itself only happens after validate_url resolved a hostname out
    # of this same URL -- a missing hostname here means that invariant
    # broke, and this should fail loudly rather than silently send a
    # request with a blank Host header.
    with pytest.raises(ValueError, match="no hostname"):
        _pin_url_to_ip("not-a-real-url", "93.184.216.34")


async def test_validate_url_is_checked_on_the_initial_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_stream(self, method, url, **kwargs):  # noqa: ANN001
        return FakeStream(httpx.Response(200, request=httpx.Request(method, url)))

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    seen: list[str] = []

    async def validate_url(url: str) -> None:
        seen.append(url)

    await inspect(
        "https://example.com",
        timeout=5.0,
        follow_redirects=True,
        max_redirects=5,
        validate_url=validate_url,
    )

    assert seen == ["https://example.com"]


async def test_validate_url_is_checked_on_every_redirect_hop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A public URL can 302 to an internal one; the SSRF guard must not stop
    # checking after the first request just because it passed.
    hops = iter(["https://hop1.example/", "https://hop2.example/"])

    def fake_stream(self, method, url, **kwargs):  # noqa: ANN001
        try:
            location = next(hops)
        except StopIteration:
            return FakeStream(httpx.Response(200, request=httpx.Request(method, url)))
        return FakeStream(
            httpx.Response(302, headers={"location": location}, request=httpx.Request(method, url))
        )

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    seen: list[str] = []

    async def validate_url(url: str) -> None:
        seen.append(url)

    await inspect(
        "https://start.example",
        timeout=5.0,
        follow_redirects=True,
        max_redirects=5,
        validate_url=validate_url,
    )

    assert seen == ["https://start.example", "https://hop1.example/", "https://hop2.example/"]


async def test_a_rejected_redirect_hop_aborts_the_inspection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_stream(self, method, url, **kwargs):  # noqa: ANN001
        return FakeStream(
            httpx.Response(
                302,
                headers={"location": "http://169.254.169.254/latest/meta-data/"},
                request=httpx.Request(method, url),
            )
        )

    monkeypatch.setattr(httpx.AsyncClient, "stream", fake_stream)

    async def validate_url(url: str) -> None:
        if "169.254.169.254" in url:
            raise ValueError(f"refusing to scan {url!r}: non-public address")

    with pytest.raises(ValueError, match="169.254.169.254"):
        await inspect(
            "https://start.example",
            timeout=5.0,
            follow_redirects=True,
            max_redirects=5,
            validate_url=validate_url,
        )
