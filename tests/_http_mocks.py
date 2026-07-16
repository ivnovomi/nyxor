"""Shared test doubles for mocking ``httpx.AsyncClient.stream()``."""

from __future__ import annotations

import httpx


class FakeStream:
    """Mimics the async context manager ``httpx.AsyncClient.stream()`` returns."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    async def __aenter__(self) -> httpx.Response:
        return self._response

    async def __aexit__(self, *exc_info: object) -> None:
        return None
