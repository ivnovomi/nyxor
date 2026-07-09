"""Safe TCP-connect service enumeration.

Only completes the standard TCP handshake via ``asyncio.open_connection`` —
no packet crafting, no half-open (SYN) scanning, which would require raw
sockets and elevated privileges anyway.
"""

from __future__ import annotations

import asyncio
import contextlib

COMMON_PORTS: dict[int, str] = {
    21: "ftp",
    22: "ssh",
    23: "telnet",
    25: "smtp",
    53: "dns",
    80: "http",
    110: "pop3",
    111: "rpcbind",
    135: "msrpc",
    139: "netbios-ssn",
    143: "imap",
    443: "https",
    445: "microsoft-ds",
    3306: "mysql",
    3389: "rdp",
    5432: "postgresql",
    6379: "redis",
    8080: "http-alt",
    8443: "https-alt",
}


async def scan_port(host: str, port: int, timeout: float) -> bool:
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except (OSError, TimeoutError):
        return False
    writer.close()
    with contextlib.suppress(OSError):
        await writer.wait_closed()
    return True


async def scan_ports(
    host: str, ports: list[int], timeout: float, max_concurrency: int
) -> dict[int, bool]:
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _check(port: int) -> tuple[int, bool]:
        async with semaphore:
            return port, await scan_port(host, port, timeout)

    results = await asyncio.gather(*(_check(p) for p in ports))
    return dict(results)


async def grab_banner(host: str, port: int, timeout: float, max_bytes: int = 256) -> str | None:
    """Passively read whatever a service sends immediately after connecting.

    No data is sent — this only surfaces banners for protocols that greet
    first (SSH, FTP, SMTP, POP3, IMAP, ...). Request-first protocols like
    HTTP won't produce anything without a request, which is expected: this
    stays a pure TCP-connect observation, not active probing.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except (OSError, TimeoutError):
        return None

    try:
        data = await asyncio.wait_for(reader.read(max_bytes), timeout=min(timeout, 1.5))
    except (OSError, TimeoutError):
        data = b""
    finally:
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()

    text = data.decode("utf-8", errors="replace").strip()
    return text or None


async def grab_banners(
    host: str, ports: list[int], timeout: float, max_concurrency: int
) -> dict[int, str | None]:
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _grab(port: int) -> tuple[int, str | None]:
        async with semaphore:
            return port, await grab_banner(host, port, timeout)

    results = await asyncio.gather(*(_grab(p) for p in ports))
    return dict(results)
