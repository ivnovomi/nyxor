from __future__ import annotations

import httpx2 as httpx
import pytest

from nyxor.plugins.analyze.ollama import OllamaUnavailable, generate


class _FakeResponse:
    def __init__(self, *, status_code: int = 200, json_body: object = None) -> None:
        self.status_code = status_code
        self._json_body = json_body

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            request = httpx.Request("POST", "http://localhost:11434/api/generate")
            response = httpx.Response(self.status_code, request=request)
            raise httpx.HTTPStatusError("bad status", request=request, response=response)

    def json(self) -> object:
        if self._json_body is _INVALID_JSON:
            raise ValueError("not valid JSON")
        return self._json_body


_INVALID_JSON = object()


async def _patch_post(monkeypatch: pytest.MonkeyPatch, effect) -> None:
    async def fake_post(self, url, *, json):  # noqa: ANN001 - matching httpx's signature loosely
        return effect()

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)


@pytest.mark.asyncio
async def test_generate_returns_stripped_text_on_success(monkeypatch: pytest.MonkeyPatch) -> None:
    await _patch_post(monkeypatch, lambda: _FakeResponse(json_body={"response": "  hello  "}))
    result = await generate("prompt", timeout_seconds=1.0)
    assert result == "hello"


@pytest.mark.asyncio
async def test_generate_raises_ollama_unavailable_on_connect_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post(self, url, *, json):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(OllamaUnavailable):
        await generate("prompt", timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_generate_raises_ollama_unavailable_on_bad_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _patch_post(monkeypatch, lambda: _FakeResponse(status_code=404))
    with pytest.raises(OllamaUnavailable):
        await generate("prompt", timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_generate_raises_ollama_unavailable_on_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_post(self, url, *, json):
        raise httpx.ReadTimeout("timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(OllamaUnavailable):
        await generate("prompt", timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_generate_raises_ollama_unavailable_on_other_transport_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: a non-Connect/Status/Timeout httpx error (e.g. a protocol
    # error, a bad --host) used to propagate raw instead of being folded
    # into OllamaUnavailable like every other failure mode.
    async def fake_post(self, url, *, json):
        raise httpx.RemoteProtocolError("server closed connection")

    monkeypatch.setattr(httpx.AsyncClient, "post", fake_post)
    with pytest.raises(OllamaUnavailable):
        await generate("prompt", timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_generate_raises_ollama_unavailable_on_invalid_json_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Regression: if `--host` points at something that isn't Ollama at all,
    # response.json() raising used to propagate a raw ValueError.
    await _patch_post(monkeypatch, lambda: _FakeResponse(json_body=_INVALID_JSON))
    with pytest.raises(OllamaUnavailable):
        await generate("prompt", timeout_seconds=1.0)


@pytest.mark.asyncio
async def test_generate_raises_ollama_unavailable_on_empty_response_field(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await _patch_post(monkeypatch, lambda: _FakeResponse(json_body={"response": ""}))
    with pytest.raises(OllamaUnavailable):
        await generate("prompt", timeout_seconds=1.0)
