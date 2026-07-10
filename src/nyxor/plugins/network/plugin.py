"""The ``network`` plugin: ``nyx network discover|scan``.

The actual scan logic lives in :func:`run_discover` / :func:`run_scan` so it
can be reused by other front-ends (the TUI) without going through Typer.
"""

from __future__ import annotations

import asyncio
import ipaddress

import typer

from nyxor.core.config import NetworkConfig
from nyxor.core.context import NyxorContext
from nyxor.core.interfaces import PluginMetadata
from nyxor.core.models import Asset, Finding, ModuleResult, Severity
from nyxor.core.output import emit_results
from nyxor.plugins.inventory.store import InventoryStore
from nyxor.plugins.network.discovery import ping_sweep
from nyxor.plugins.network.ports import COMMON_PORTS, grab_banners, scan_ports

network_app = typer.Typer(
    name="network", help="Host discovery and service enumeration.", no_args_is_help=True
)

MAX_SWEEP_HOSTS = 1024


def _expand_targets(target: str) -> list[str]:
    try:
        network = ipaddress.ip_network(target, strict=False)
    except ValueError:
        return [target]

    if network.num_addresses == 1:
        return [str(network.network_address)]

    hosts = [str(ip) for ip in network.hosts()]
    if len(hosts) > MAX_SWEEP_HOSTS:
        raise typer.BadParameter(
            f"{target} expands to {len(hosts)} hosts; the safety limit is {MAX_SWEEP_HOSTS}."
        )
    return hosts


async def run_discover(target: str, config: NetworkConfig) -> ModuleResult:
    """Ping-sweep ``target`` (a host or CIDR range) and return a ModuleResult."""
    hosts = _expand_targets(target)
    reachable = await ping_sweep(hosts, config.timeout_seconds, config.max_concurrency)

    result = ModuleResult(module="network.discover", target=target)
    assets: list[Asset] = []
    for host, up in reachable.items():
        if not up:
            continue
        result.findings.append(
            Finding(
                title="Host is reachable",
                severity=Severity.INFO,
                target=host,
                description=f"{host} responded to ICMP echo.",
            )
        )
        assets.append(Asset(kind="host", identifier=host, source_module="network.discover"))
    result.assets = assets
    result.raw_data = {"scanned": len(hosts), "reachable": len(assets)}
    return result


async def run_scan(host: str, ports: str, config: NetworkConfig) -> ModuleResult:
    """Enumerate open TCP services on ``host`` and return a ModuleResult."""
    port_list = (
        [int(p.strip()) for p in ports.split(",") if p.strip()] if ports else list(COMMON_PORTS)
    )
    open_ports = await scan_ports(host, port_list, config.timeout_seconds, config.max_concurrency)
    open_port_list = sorted(port for port, is_open in open_ports.items() if is_open)

    banners = await grab_banners(
        host, open_port_list, config.timeout_seconds, config.max_concurrency
    )

    result = ModuleResult(module="network.scan", target=host)
    assets: list[Asset] = []
    for port in open_port_list:
        service = COMMON_PORTS.get(port, "unknown")
        banner = banners.get(port)
        description = f"{host}:{port} accepted a TCP connection ({service})."
        if banner:
            description += f" Banner: {banner}"
        evidence: dict[str, object] = {"port": port, "service": service}
        if banner:
            evidence["banner"] = banner

        result.findings.append(
            Finding(
                title=f"Open port {port}/tcp ({service})",
                severity=Severity.INFO,
                target=host,
                description=description,
                evidence=evidence,
            )
        )
        assets.append(
            Asset(
                kind="service",
                identifier=f"{host}:{port}",
                attributes={"service": service, "banner": banner}
                if banner
                else {"service": service},
                source_module="network.scan",
            )
        )
    result.assets = assets
    result.raw_data = {"scanned_ports": len(port_list), "open_ports": len(assets)}
    return result


@network_app.command("discover")
def discover(
    ctx: typer.Context, target: str, no_inventory: bool = typer.Option(False, "--no-inventory")
) -> None:
    """Ping-sweep a host or CIDR range (e.g. `nyx network discover 192.168.1.0/24`)."""
    context: NyxorContext = ctx.obj
    result = asyncio.run(run_discover(target, context.config.network))

    if result.assets and not no_inventory:
        InventoryStore().add(result.assets)

    emit_results(context, [result], title="NYXOR Network Discovery")


@network_app.command("scan")
def scan(
    ctx: typer.Context,
    host: str,
    ports: str = typer.Option(
        "", "--ports", help="Comma-separated ports; defaults to a common set."
    ),
    no_inventory: bool = typer.Option(False, "--no-inventory"),
) -> None:
    """Enumerate open TCP services on a single host via connect scanning."""
    context: NyxorContext = ctx.obj
    result = asyncio.run(run_scan(host, ports, context.config.network))

    if result.assets and not no_inventory:
        InventoryStore().add(result.assets)

    emit_results(context, [result], title="NYXOR Network Scan")


class NetworkPlugin:
    metadata = PluginMetadata(
        name="network",
        description="Host discovery, service enumeration, and network inventory.",
        version="0.1.0",
        author="NYXOR",
        commands=("discover", "scan"),
        category="Scanning",
    )

    def register(self, app: typer.Typer, context: NyxorContext) -> None:
        """
        Register the network command group with the application.
        
        Parameters:
        	app (typer.Typer): Application to which the network commands are added.
        	context (NyxorContext): Application context.
        """
        app.add_typer(network_app, rich_help_panel=self.metadata.category)


PLUGIN = NetworkPlugin()
