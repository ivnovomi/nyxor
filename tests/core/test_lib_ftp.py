from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script
from nyxor.core.scripting.errors import RuntimeScriptError

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_ftp_lints_clean() -> None:
    source = (_REPO_ROOT / "lib" / "ftp.nyx").read_text(encoding="utf-8")
    issues = lint_source(source)
    assert all(issue.severity == "warning" for issue in issues), issues
    assert issues, "expected socket.* lint warnings"


class _MockFtpServer:
    """A minimal control+PASV FTP server, just enough to exercise lib/ftp.nyx."""

    def __init__(self) -> None:
        self.files = {"test.txt": "hello from ftp\n"}
        self.listing = "-rw-r--r-- 1 owner group 15 Jan 01 00:00 test.txt\r\n"
        self._pending_data_conn: tuple[asyncio.StreamReader, asyncio.StreamWriter] | None = None

    async def start(self) -> int:
        self.control_server = await asyncio.start_server(self._handle_control, "127.0.0.1", 0)
        return self.control_server.sockets[0].getsockname()[1]

    async def _handle_control(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        writer.write(b"220 Mock FTP Ready\r\n")
        await writer.drain()
        while True:
            line = await reader.readline()
            if not line:
                break
            cmd = line.decode(errors="replace").strip()
            if cmd.startswith("USER"):
                writer.write(b"331 Password required\r\n")
            elif cmd.startswith("PASS"):
                writer.write(b"230 Logged in\r\n")
            elif cmd == "PWD":
                writer.write(b'257 "/" is current directory\r\n')
            elif cmd.startswith("CWD"):
                writer.write(b"250 Directory changed\r\n")
            elif cmd.startswith("TYPE"):
                writer.write(b"200 Type set\r\n")
            elif cmd == "PASV":
                data_server = await asyncio.start_server(self._handle_data, "127.0.0.1", 0)
                data_port = data_server.sockets[0].getsockname()[1]
                self._data_server = data_server
                p1, p2 = divmod(data_port, 256)
                writer.write(f"227 Entering Passive Mode (127,0,0,1,{p1},{p2})\r\n".encode())
            elif cmd == "LIST" or cmd.startswith("LIST "):
                writer.write(b"150 Here comes the directory listing\r\n")
                await writer.drain()
                _, data_writer = await self._wait_for_data_conn()
                data_writer.write(self.listing.encode())
                await data_writer.drain()
                data_writer.close()
                writer.write(b"226 Transfer complete\r\n")
            elif cmd.startswith("RETR "):
                filename = cmd[len("RETR ") :].strip()
                writer.write(b"150 Opening data connection\r\n")
                await writer.drain()
                _, data_writer = await self._wait_for_data_conn()
                data_writer.write(self.files.get(filename, "").encode())
                await data_writer.drain()
                data_writer.close()
                writer.write(b"226 Transfer complete\r\n")
            elif cmd == "QUIT":
                writer.write(b"221 Goodbye\r\n")
                await writer.drain()
                writer.close()
                break
            else:
                writer.write(b"500 Unknown command\r\n")
            await writer.drain()

    async def _wait_for_data_conn(
        self,
    ) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
        for _ in range(200):
            if self._pending_data_conn is not None:
                conn = self._pending_data_conn
                self._pending_data_conn = None
                return conn
            await asyncio.sleep(0.01)
        raise TimeoutError("mock ftp: no data connection arrived")

    async def _handle_data(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        self._pending_data_conn = (reader, writer)
        await writer.wait_closed()


@pytest.fixture
async def ftp_server() -> AsyncIterator[int]:
    server = _MockFtpServer()
    port = await server.start()
    async with server.control_server:
        task = asyncio.ensure_future(server.control_server.serve_forever())
        try:
            yield port
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


async def _run(body: str, *, port: int, unsafe: bool = True) -> list[str]:
    lines: list[str] = []
    source = f'import "lib/ftp.nyx" as ftp\n{body}'
    await run_script(
        source,
        load_config(),
        output=lines.append,
        base_dir=_REPO_ROOT,
        unsafe=unsafe,
    )
    return lines


async def test_ftp_connect_login_pwd_list_retr_quit(ftp_server: int) -> None:
    lines = await _run(
        f"""
set conn = ftp.connect("127.0.0.1", {ftp_server})
print conn["code"]

set login_result = ftp.anonymous_login(conn)
print login_result[0]

print ftp.pwd(conn)

set listing = ftp.list(conn, "")
print listing

set content = ftp.retr(conn, "test.txt")
print content

ftp.quit(conn)
""",
        port=ftp_server,
    )
    assert lines[0] == "220"
    assert lines[1] == "230"
    assert lines[2] == '257 "/" is current directory'
    assert "test.txt" in lines[3]
    assert lines[4] == "hello from ftp\n"


async def test_ftp_retr_of_a_missing_file_returns_empty_string(ftp_server: int) -> None:
    lines = await _run(
        f"""
set conn = ftp.connect("127.0.0.1", {ftp_server})
ftp.anonymous_login(conn)
print ftp.retr(conn, "nope.txt")
ftp.quit(conn)
""",
        port=ftp_server,
    )
    assert lines == [""]


async def test_ftp_requires_unsafe(ftp_server: int) -> None:
    with pytest.raises(RuntimeScriptError, match="'socket' is disabled by default"):
        await _run(f'ftp.connect("127.0.0.1", {ftp_server})\n', port=ftp_server, unsafe=False)
