from __future__ import annotations

import pytest
import typer

from nyxor.core.config import NetworkConfig
from nyxor.plugins.network import plugin as network_plugin
from nyxor.plugins.network.plugin import MAX_SWEEP_HOSTS, _expand_targets, run_discover
from nyxor.plugins.network.ports import COMMON_PORTS


def test_expand_single_host_returns_itself() -> None:
    assert _expand_targets("example.com") == ["example.com"]


def test_expand_single_ip_returns_one_address() -> None:
    assert _expand_targets("10.0.0.5") == ["10.0.0.5"]


def test_expand_small_cidr_returns_usable_hosts() -> None:
    hosts = _expand_targets("192.168.1.0/30")
    assert hosts == ["192.168.1.1", "192.168.1.2"]


def test_expand_huge_cidr_is_rejected() -> None:
    with pytest.raises(typer.BadParameter):
        _expand_targets("10.0.0.0/8")


def test_common_ports_cover_well_known_services() -> None:
    assert COMMON_PORTS[80] == "http"
    assert COMMON_PORTS[443] == "https"
    assert len(COMMON_PORTS) < MAX_SWEEP_HOSTS


@pytest.mark.asyncio
async def test_run_discover_surfaces_an_error_when_ping_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A missing 'ping' binary (minimal container images) must not look like
    # "every host is down" — it has to show up as a module error instead.
    monkeypatch.setattr(network_plugin, "ping_binary_available", lambda: False)

    result = await run_discover("10.0.0.1", NetworkConfig())

    assert result.errors
    assert "ping" in result.errors[0]
    assert result.findings == []
    assert result.raw_data == {"scanned": 1, "reachable": 0}


@pytest.mark.asyncio
async def test_run_discover_reports_reachable_hosts_when_ping_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(network_plugin, "ping_binary_available", lambda: True)

    async def fake_ping_sweep(hosts, timeout, max_concurrency):
        return {host: True for host in hosts}

    monkeypatch.setattr(network_plugin, "ping_sweep", fake_ping_sweep)

    result = await run_discover("10.0.0.1", NetworkConfig())

    assert not result.errors
    assert len(result.findings) == 1
    assert result.raw_data == {"scanned": 1, "reachable": 1}
