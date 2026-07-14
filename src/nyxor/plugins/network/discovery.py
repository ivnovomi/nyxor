"""Host reachability checks via the system ``ping`` binary.

Deliberately does not build raw ICMP packets — that requires elevated
privileges on every OS. Shelling out to ``ping`` is the safe, portable
choice, at the cost of parsing plain text instead of a socket.
"""

from __future__ import annotations

import asyncio
import platform
import shutil


def ping_binary_available() -> bool:
    """Whether a ``ping`` executable exists on PATH.

    Minimal container images often ship without ``iputils``/``ping`` — when
    that's the case, every host silently "fails" its ping, which is
    indistinguishable from "every host is actually down" unless a caller
    checks this first and surfaces it as an error instead.
    """
    return shutil.which("ping") is not None


def _ping_args(host: str, timeout: float) -> list[str] | None:
    ping_path = shutil.which("ping")
    if ping_path is None:
        return None
    if platform.system().lower() == "windows":
        timeout_ms = max(1, int(timeout * 1000))
        return [ping_path, "-n", "1", "-w", str(timeout_ms), host]
    timeout_s = max(1, int(round(timeout)))
    return [ping_path, "-c", "1", "-W", str(timeout_s), host]


async def ping_host(host: str, timeout: float = 2.0) -> bool:
    """Return True if a single ICMP echo to ``host`` succeeds within ``timeout``."""
    args = _ping_args(host, timeout)
    if args is None:
        return False

    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL
        )
    except OSError:
        return False

    try:
        returncode = await asyncio.wait_for(proc.wait(), timeout=timeout + 2)
    except TimeoutError:
        proc.kill()
        return False
    return returncode == 0


async def ping_sweep(hosts: list[str], timeout: float, max_concurrency: int) -> dict[str, bool]:
    """Ping many hosts concurrently, bounded by ``max_concurrency``."""
    semaphore = asyncio.Semaphore(max_concurrency)

    async def _check(host: str) -> tuple[str, bool]:
        async with semaphore:
            return host, await ping_host(host, timeout)

    results = await asyncio.gather(*(_check(h) for h in hosts))
    return dict(results)
