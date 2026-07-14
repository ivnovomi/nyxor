from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import run_script
from nyxor.core.scripting.errors import RuntimeScriptError


async def _echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    data = await reader.read(4096)
    writer.write(b"ECHO:" + data)
    await writer.drain()
    writer.close()


@pytest.fixture
async def echo_server() -> AsyncIterator[int]:
    server = await asyncio.start_server(_echo, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        task = asyncio.ensure_future(server.serve_forever())
        try:
            yield port
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


async def _run(source: str, *, unsafe: bool = True) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append, unsafe=unsafe)
    return lines


async def test_socket_functions_are_refused_without_unsafe(echo_server: int) -> None:
    with pytest.raises(RuntimeScriptError, match="'socket' is disabled by default"):
        await _run(f'socket.connect("127.0.0.1", {echo_server})\n', unsafe=False)


async def test_socket_functions_work_with_unsafe(echo_server: int) -> None:
    lines = await _run(
        f"""
set h = socket.connect("127.0.0.1", {echo_server})
socket.send(h, "hello")
print socket.recv_text(h, 4096, 3.0)
socket.close(h)
"""
    )
    assert lines == ["ECHO:hello"]


async def test_socket_functions_work_via_the_unsafe_statement(echo_server: int) -> None:
    # unsafe=False on the caller side, but the script itself flips it on —
    # exactly the same mechanism python:/pip already use.
    lines = await _run(
        f"""
unsafe
set h = socket.connect("127.0.0.1", {echo_server})
socket.send(h, "via statement")
print socket.recv_text(h, 4096, 3.0)
""",
        unsafe=False,
    )
    assert lines == ["ECHO:via statement"]


async def test_socket_send_accepts_a_list_of_byte_values(echo_server: int) -> None:
    lines = await _run(
        f"""
set h = socket.connect("127.0.0.1", {echo_server})
socket.send(h, [104, 105])
print socket.recv_text(h, 4096, 3.0)
socket.close(h)
"""
    )
    assert lines == ["ECHO:hi"]


async def test_socket_recv_returns_a_list_of_byte_values(echo_server: int) -> None:
    lines = await _run(
        f"""
set h = socket.connect("127.0.0.1", {echo_server})
socket.send(h, "hi")
print socket.recv(h, 4096, 3.0)
socket.close(h)
"""
    )
    assert lines == ["[69, 67, 72, 79, 58, 104, 105]"]  # "ECHO:hi" as byte values


async def test_socket_connect_rejects_an_unknown_protocol(echo_server: int) -> None:
    with pytest.raises(RuntimeScriptError, match="protocol must be"):
        await _run(f'socket.connect("127.0.0.1", {echo_server}, "icmp")\n')


async def test_socket_connect_rejects_an_out_of_range_port() -> None:
    with pytest.raises(RuntimeScriptError, match="out of range"):
        await _run('socket.connect("127.0.0.1", 999999)\n')


async def test_socket_connect_refused_raises_a_clean_error() -> None:
    # Nothing listens on port 1 in a test environment.
    with pytest.raises(RuntimeScriptError, match="socket.connect"):
        await _run('socket.connect("127.0.0.1", 1, "tcp", 1.0)\n')


async def test_socket_recv_on_an_unknown_handle_raises() -> None:
    with pytest.raises(RuntimeScriptError, match="not an open socket connection"):
        await _run("socket.recv(999)\n")


async def test_socket_recv_max_bytes_is_capped() -> None:
    with pytest.raises(RuntimeScriptError, match="max_bytes"):
        await _run("socket.recv(1, 999999999)\n")


async def test_run_script_closes_sockets_left_open_by_the_script(echo_server: int) -> None:
    # The script never calls socket.close() — run_script() must clean up
    # after it regardless, so the connection doesn't leak past this call.
    lines: list[str] = []
    await run_script(
        f'set h = socket.connect("127.0.0.1", {echo_server})\nprint "connected"\n',
        load_config(),
        output=lines.append,
        unsafe=True,
    )
    assert lines == ["connected"]


async def test_socket_functions_are_lint_warnings_not_errors() -> None:
    from nyxor.core.scripting import lint_source

    issues = lint_source('unsafe\nset h = socket.connect("127.0.0.1", 80)\nsocket.close(h)\n')
    assert all(issue.severity == "warning" for issue in issues)
    assert any("socket.connect" in issue.message for issue in issues)


async def test_unknown_socket_function_is_a_lint_error() -> None:
    from nyxor.core.scripting import lint_source

    issues = lint_source('unsafe\nsocket.nope("x")\n')
    assert any(
        issue.severity == "error" and "unknown function 'socket.nope'" in issue.message
        for issue in issues
    )


# ---------- raw_send / raw_recv / raw_read ----------
#
# Raw IP sockets are privilege- and platform-gated in ways a CI runner can't
# control (root on Linux/macOS, and even then blocked outright on Windows —
# confirmed empirically during development: IP_HDRINCL raw sockets failed to
# open at all in a Windows environment with administrator rights). These
# tests assert the --unsafe gate and clean, catchable error surface rather
# than a specific outcome, since "succeeds" vs. "refused by the OS" both
# need to be acceptable depending on where the suite runs.


async def test_raw_send_is_refused_without_unsafe() -> None:
    with pytest.raises(RuntimeScriptError, match="'socket' is disabled by default"):
        await _run('socket.raw_send("127.0.0.1", [1, 2, 3])\n', unsafe=False)


async def test_raw_recv_is_refused_without_unsafe() -> None:
    with pytest.raises(RuntimeScriptError, match="'socket' is disabled by default"):
        await _run('socket.raw_recv("127.0.0.1")\n', unsafe=False)


async def test_raw_send_either_works_or_fails_with_a_clean_permission_error() -> None:
    try:
        sent = await _run(
            'set pkt = build_ip_header("127.0.0.1", "127.0.0.1", 1, [])\n'
            'print socket.raw_send("127.0.0.1", pkt)\n'
        )
        assert sent == ["20"]
    except RuntimeScriptError as exc:
        assert "raw_send" in str(exc)


async def test_raw_recv_either_works_or_fails_with_a_clean_permission_error() -> None:
    try:
        lines = await _run(
            'set h = socket.raw_recv("127.0.0.1", 1.0)\nprint "opened"\nsocket.close(h)\n'
        )
        assert lines == ["opened"]
    except RuntimeScriptError as exc:
        assert "raw_recv" in str(exc)


async def test_raw_functions_are_lint_warnings_not_errors() -> None:
    from nyxor.core.scripting import lint_source

    issues = lint_source(
        'unsafe\nsocket.raw_send("127.0.0.1", [1])\nset h = socket.raw_recv("127.0.0.1")\n'
    )
    assert all(issue.severity == "warning" for issue in issues)
    assert any("raw_send" in issue.message for issue in issues)
    assert any("raw_recv" in issue.message for issue in issues)
