from __future__ import annotations

import pytest
import typer

from nyxor.plugins.network.plugin import MAX_SWEEP_HOSTS, _expand_targets
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
