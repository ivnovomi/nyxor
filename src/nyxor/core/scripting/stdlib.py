"""The modules a NyxScript ``run`` statement can call.

Every entry wraps one of the domain plugins' ``run_*`` coroutines — NyxScript
is one of several front-ends over the same logic (alongside the CLI, TUI,
REST API, MCP server, and GitHub Action), not a reimplementation of it.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from nyxor.core.config import NyxorConfig
from nyxor.core.models import ModuleResult

RunnerFn = Callable[[str, NyxorConfig], Awaitable[list[ModuleResult]]]


async def _run_audit(target: str, config: NyxorConfig) -> list[ModuleResult]:
    from nyxor.plugins.audit.plugin import run_audit

    return await run_audit(target, config)


async def _run_dns(target: str, config: NyxorConfig) -> list[ModuleResult]:
    from nyxor.plugins.dns_.plugin import run_lookup

    return [await run_lookup(target, config.dns.resolvers, config.dns.timeout_seconds)]


async def _run_tls(target: str, config: NyxorConfig) -> list[ModuleResult]:
    from nyxor.plugins.tls_.plugin import run_inspect

    return [await run_inspect(target, config.tls.timeout_seconds)]


async def _run_http(target: str, config: NyxorConfig) -> list[ModuleResult]:
    from nyxor.plugins.http_.plugin import run_inspect

    return [await run_inspect(target, config.http)]


async def _run_network_discover(target: str, config: NyxorConfig) -> list[ModuleResult]:
    from nyxor.plugins.network.plugin import run_discover

    return [await run_discover(target, config.network)]


async def _run_network_scan(target: str, config: NyxorConfig) -> list[ModuleResult]:
    from nyxor.plugins.network.plugin import run_scan

    return [await run_scan(target, "", config.network)]


async def _run_recon(target: str, config: NyxorConfig) -> list[ModuleResult]:
    from nyxor.plugins.recon.plugin import run_recon

    return await run_recon(target)


MODULE_RUNNERS: dict[str, RunnerFn] = {
    "audit": _run_audit,
    "dns": _run_dns,
    "tls": _run_tls,
    "http": _run_http,
    "network.discover": _run_network_discover,
    "network.scan": _run_network_scan,
    "recon": _run_recon,
}
