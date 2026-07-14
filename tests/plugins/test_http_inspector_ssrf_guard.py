from __future__ import annotations

import httpx
import pytest

from nyxor.plugins.http_.inspector import inspect


async def test_validate_url_is_checked_on_the_initial_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(200, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

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

    async def fake_get(self, url, **kwargs):  # noqa: ANN001
        try:
            location = next(hops)
        except StopIteration:
            return httpx.Response(200, request=httpx.Request("GET", url))
        return httpx.Response(
            302, headers={"location": location}, request=httpx.Request("GET", url)
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

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
    async def fake_get(self, url, **kwargs):  # noqa: ANN001
        return httpx.Response(
            302,
            headers={"location": "http://169.254.169.254/latest/meta-data/"},
            request=httpx.Request("GET", url),
        )

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

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
