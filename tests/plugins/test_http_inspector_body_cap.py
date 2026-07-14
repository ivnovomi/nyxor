from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from nyxor.plugins.http_.inspector import MAX_BODY_BYTES, _read_capped_body


class _FakeResponse:
    """A minimal stand-in for httpx.Response exposing only aiter_bytes()."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = chunks
        self.chunks_yielded = 0

    async def aiter_bytes(self) -> AsyncIterator[bytes]:
        for chunk in self._chunks:
            self.chunks_yielded += 1
            yield chunk


@pytest.mark.asyncio
async def test_read_capped_body_returns_full_content_under_the_cap() -> None:
    response = _FakeResponse([b"hello ", b"world"])
    body = await _read_capped_body(response)  # type: ignore[arg-type]
    assert body == b"hello world"
    assert response.chunks_yielded == 2


@pytest.mark.asyncio
async def test_read_capped_body_stops_reading_once_the_cap_is_reached() -> None:
    chunk = b"x" * (MAX_BODY_BYTES // 2 + 1)
    # Three chunks would total well past MAX_BODY_BYTES; only the first two
    # are needed to cross the cap, so the third must never be consumed.
    response = _FakeResponse([chunk, chunk, chunk])

    body = await _read_capped_body(response)  # type: ignore[arg-type]

    assert len(body) >= MAX_BODY_BYTES
    assert response.chunks_yielded == 2
