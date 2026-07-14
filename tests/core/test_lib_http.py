from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script
from nyxor.core.scripting.errors import RuntimeScriptError

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_http_lints_clean() -> None:
    source = (_REPO_ROOT / "lib" / "http.nyx").read_text(encoding="utf-8")
    issues = lint_source(source)
    assert all(issue.severity == "warning" for issue in issues), issues
    assert issues, "expected socket.* lint warnings"


class _MockHttpServer:
    """A canned-response HTTP/1.1 server, just enough to exercise lib/http.nyx."""

    def __init__(self) -> None:
        self.last_request: bytes | None = None

    async def start(self) -> int:
        self.server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        request = await reader.read(65536)
        self.last_request = request
        body = b'{"ok": true}'
        response = (
            b"HTTP/1.1 200 OK\r\n"
            b"Content-Type: application/json\r\n"
            b"X-Test: yes\r\n"
            b"Connection: close\r\n"
            b"\r\n" + body
        )
        writer.write(response)
        await writer.drain()
        writer.close()


@pytest.fixture
async def http_server() -> AsyncIterator[int]:
    server = _MockHttpServer()
    port = await server.start()
    async with server.server:
        task = asyncio.ensure_future(server.server.serve_forever())
        try:
            yield port
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


async def _run(body: str) -> list[str]:
    lines: list[str] = []
    source = f'import "lib/http.nyx" as http\n{body}'
    await run_script(source, load_config(), output=lines.append, base_dir=_REPO_ROOT, unsafe=True)
    return lines


async def test_http_get_against_a_mock_server(http_server: int) -> None:
    lines = await _run(
        f"""
set resp = http.get("http://127.0.0.1:{http_server}/status", {{}}, 5.0)
print resp["status_code"]
print resp["status_text"]
print resp["headers"]["content-type"]
print resp["headers"]["x-test"]
print resp["body"]
"""
    )
    assert lines == ["200", "OK", "application/json", "yes", '{"ok": true}']


async def test_http_get_sends_the_expected_request_line_and_host_header(
    http_server: int,
) -> None:
    await _run(f'http.get("http://127.0.0.1:{http_server}/status", {{}}, 5.0)\n')


async def test_http_post_sends_a_body_with_content_length(http_server: int) -> None:
    lines = await _run(
        f"""
set resp = http.post("http://127.0.0.1:{http_server}/submit", "hello=world", {{}}, 5.0)
print resp["status_code"]
"""
    )
    assert lines == ["200"]


async def test_build_request_default_headers() -> None:
    lines = await _run('print http.build_request("GET", "/x", "example.com", {}, "")\n')
    assert lines == ["GET /x HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\n\r\n"]


async def test_build_request_includes_content_length_for_a_body() -> None:
    lines = await _run('print http.build_request("POST", "/x", "example.com", {}, "abc")\n')
    assert lines == [
        "POST /x HTTP/1.1\r\nHost: example.com\r\nConnection: close\r\nContent-Length: 3\r\n\r\nabc"
    ]


async def test_build_request_respects_a_caller_supplied_host_header() -> None:
    lines = await _run(
        'print http.build_request("GET", "/x", "ignored.example", '
        '{"Host": "override.example"}, "")\n'
    )
    assert lines == ["GET /x HTTP/1.1\r\nHost: override.example\r\nConnection: close\r\n\r\n"]


async def test_parse_response_splits_status_headers_and_body() -> None:
    lines = await _run(
        r"""
set resp = http.parse_response("HTTP/1.1 404 Not Found\r\nContent-Type: text/plain\r\n\r\nnope")
print resp["status_code"]
print resp["status_text"]
print resp["headers"]["content-type"]
print resp["body"]
"""
    )
    assert lines == ["404", "Not Found", "text/plain", "nope"]


async def test_http_requires_unsafe(http_server: int) -> None:
    with pytest.raises(RuntimeScriptError, match="'socket' is disabled by default"):
        await run_script(
            f'import "lib/http.nyx" as http\n'
            f'http.get("http://127.0.0.1:{http_server}/", {{}}, 5.0)\n',
            load_config(),
            output=[].append,
            base_dir=_REPO_ROOT,
            unsafe=False,
        )
