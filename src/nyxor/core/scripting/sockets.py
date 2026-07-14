"""``socket.*`` — direct TCP/UDP network access for NyxScript.

This is deliberately gated behind ``--unsafe`` (checked by the interpreter
before dispatching any call here, same mechanism as ``python:``/``pip``):
unlike ``run dns``/``run tls``/``run http``/``network.discover``/
``network.scan`` — every one of which is a bounded, passive, read-only
observation NYXOR can describe and score — a raw socket lets a script talk
whatever protocol it wants to whatever host:port it wants. That's a real
capability expansion past NYXOR's "passive audit" identity, not just
another builtin, so it gets the same opt-in treatment.

Every blocking call (connect/send/recv) runs via `asyncio.to_thread` with
an explicit timeout, mirroring the same "never let one script call hang
the whole interpreter" discipline as the regex_* builtins' subprocess
timeout — a script that mistypes a hostname or hits a silent host gets a
clean timeout error back, not a frozen `nyx script run`.

NyxScript has no bytes type, so received/sent data crosses this boundary
either as a UTF-8 string (`send`, `recv_text`) or as a list of ints 0-255
(`recv`) — see `bytes_to_hex`/`bytes_from_hex`/`pack_uint16`/etc. in
`builtins.py` for building/parsing binary protocol messages out of that.
"""

from __future__ import annotations

import asyncio
import socket as socket_module
from typing import Any

_DEFAULT_TIMEOUT = 10.0
#: A script asking for more than this in one recv() is almost certainly a
#: mistake (or a runaway server), not a real protocol need — same spirit
#: as the regex input-length cap.
_MAX_RECV_BYTES = 1_048_576


def _to_bytes(data: Any, *, who: str) -> bytes:
    if isinstance(data, str):
        return data.encode("utf-8")
    if isinstance(data, list):
        try:
            return bytes(int(b) for b in data)
        except (TypeError, ValueError) as exc:
            raise TypeError(f"{who}: list data must contain integers 0-255") from exc
    raise TypeError(f"{who}: data must be a string or a list of byte values (0-255)")


class _Connection:
    __slots__ = ("sock", "protocol")

    def __init__(self, sock: socket_module.socket, protocol: str) -> None:
        self.sock = sock
        self.protocol = protocol


class ScriptSocket:
    """TCP/UDP primitives exposed to NyxScript as ``socket.*`` — one instance

    per running script (``Interpreter.__init__``), so connection handles
    don't leak across unrelated script runs. ``Interpreter.run()`` closes
    every connection still open when the script ends (success, error, or
    otherwise), so a script that forgets to call ``socket.close()`` doesn't
    leave a live OS socket behind.
    """

    def __init__(self) -> None:
        self._connections: dict[int, _Connection] = {}
        self._next_handle = 1

    def _get(self, handle: Any) -> _Connection:
        conn = self._connections.get(handle)
        if conn is None:
            raise TypeError(f"{handle!r} is not an open socket connection (already closed?)")
        return conn

    async def connect(self, args: list[Any]) -> int:
        if not (2 <= len(args) <= 4):
            raise TypeError("socket.connect() expects (host, port[, protocol][, timeout])")
        host = str(args[0])
        port = int(args[1])
        protocol = str(args[2]).lower() if len(args) >= 3 else "tcp"
        timeout = float(args[3]) if len(args) >= 4 else _DEFAULT_TIMEOUT
        if protocol not in ("tcp", "udp"):
            raise TypeError(f"socket.connect(): protocol must be 'tcp' or 'udp', got {protocol!r}")
        if not (1 <= port <= 65535):
            raise TypeError(f"socket.connect(): port {port} is out of range")

        def _do_connect() -> socket_module.socket:
            kind = socket_module.SOCK_STREAM if protocol == "tcp" else socket_module.SOCK_DGRAM
            sock = socket_module.socket(socket_module.AF_INET, kind)
            sock.settimeout(timeout)
            sock.connect((host, port))
            return sock

        try:
            sock = await asyncio.to_thread(_do_connect)
        except OSError as exc:
            raise TimeoutError(f"socket.connect(): could not reach {host}:{port} — {exc}") from exc

        handle = self._next_handle
        self._next_handle += 1
        self._connections[handle] = _Connection(sock, protocol)
        return handle

    async def send(self, args: list[Any]) -> int:
        if len(args) != 2:
            raise TypeError("socket.send() expects (handle, data)")
        handle, data = args
        conn = self._get(handle)
        payload = _to_bytes(data, who="socket.send()")
        try:
            await asyncio.to_thread(conn.sock.sendall, payload)
        except OSError as exc:
            raise OSError(f"socket.send(): {exc}") from exc
        return len(payload)

    async def recv(self, args: list[Any]) -> list[int]:
        if not (1 <= len(args) <= 3):
            raise TypeError("socket.recv() expects (handle[, max_bytes][, timeout])")
        handle = args[0]
        max_bytes = int(args[1]) if len(args) >= 2 else 4096
        timeout = float(args[2]) if len(args) >= 3 else None
        if not (0 < max_bytes <= _MAX_RECV_BYTES):
            raise ValueError(f"socket.recv(): max_bytes must be in (0, {_MAX_RECV_BYTES}]")
        conn = self._get(handle)

        def _do_recv() -> bytes:
            if timeout is not None:
                conn.sock.settimeout(timeout)
            try:
                return conn.sock.recv(max_bytes)
            except TimeoutError:
                # No data within the timeout isn't an error here — an empty
                # result lets the script decide what "nothing arrived" means
                # for its own protocol, same as a 0-length read anywhere else.
                return b""

        try:
            raw = await asyncio.to_thread(_do_recv)
        except OSError as exc:
            raise OSError(f"socket.recv(): {exc}") from exc
        return list(raw)

    async def recv_text(self, args: list[Any]) -> str:
        raw = await self.recv(args)
        try:
            return bytes(raw).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(
                "socket.recv_text(): received bytes aren't valid UTF-8 — use socket.recv() "
                "instead and decode with bytes_to_hex()/your own protocol logic"
            ) from exc

    async def close(self, args: list[Any]) -> None:
        if len(args) != 1:
            raise TypeError("socket.close() expects (handle)")
        conn = self._connections.pop(args[0], None)
        if conn is not None:
            await asyncio.to_thread(conn.sock.close)

    async def close_all(self) -> None:
        """Called by the interpreter at the end of every script run — never

        leave a live OS socket behind just because the script itself forgot
        to close it (or errored before reaching a `socket.close()` call).
        """
        handles = list(self._connections)
        for handle in handles:
            await self.close([handle])


#: Method names reachable as ``socket.<name>(...)`` from NyxScript.
SOCKET_FUNCTIONS = frozenset({"connect", "send", "recv", "recv_text", "close"})
