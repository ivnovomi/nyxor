from __future__ import annotations

from pathlib import Path

import pytest

from nyxor.core.config import load_config
from nyxor.core.models import Asset, ModuleResult
from nyxor.core.scripting import lint_source, run_script
from nyxor.core.scripting.stdlib import MODULE_RUNNERS

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_asset_module_lints_clean() -> None:
    source = (_REPO_ROOT / "lib" / "asset.nyx").read_text(encoding="utf-8")
    assert lint_source(source) == []


async def _fake_discover(target: str, config: object) -> list[ModuleResult]:
    return [
        ModuleResult(
            module="network.discover",
            target=target,
            assets=[
                Asset(
                    kind="host",
                    identifier="192.168.1.1",
                    attributes={"open_ports": [22, 80]},
                    source_module="network.discover",
                ),
                Asset(kind="host", identifier="192.168.1.2", attributes={}),
                Asset(
                    kind="service", identifier="192.168.1.1:22", attributes={"proto": "ssh"}
                ),
            ],
        )
    ]


@pytest.fixture(autouse=True)
def _stub_network_discover(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(MODULE_RUNNERS, "network.discover", _fake_discover)


async def _run(body: str) -> list[str]:
    lines: list[str] = []
    source = (
        'import "lib/asset.nyx" as asset\n'
        'run network.discover "192.168.1.0/24" as results\n'
        "set assets = results[0].assets\n" + body
    )
    await run_script(source, load_config(), output=lines.append, base_dir=_REPO_ROOT)
    # `run` itself emits two chrome lines ("→ run ..." and a finding count)
    # before anything the script's own `print` statements produce.
    return lines[2:]


async def test_by_kind_filters_to_the_matching_kind() -> None:
    lines = await _run("print asset.identifiers(asset.by_kind(assets, \"host\"))\n")
    assert lines == ["[192.168.1.1, 192.168.1.2]"]


async def test_kinds_lists_distinct_kinds_in_first_seen_order() -> None:
    lines = await _run("print asset.kinds(assets)\n")
    assert lines == ["[host, service]"]


async def test_count_by_kind() -> None:
    lines = await _run("print asset.count_by_kind(assets)\n")
    assert lines == ["{host: 2, service: 1}"]


async def test_group_by_kind_buckets_full_assets() -> None:
    lines = await _run(
        """
set grouped = asset.group_by_kind(assets)
print len(grouped["host"])
print len(grouped["service"])
"""
    )
    assert lines == ["2", "1"]


async def test_attr_and_has_attr() -> None:
    lines = await _run(
        """
set host = asset.by_kind(assets, "host")[0]
print asset.attr(host, "open_ports", [])
print asset.attr(host, "missing_key", "fallback")
print asset.has_attr(host, "open_ports")
print asset.has_attr(host, "missing_key")
"""
    )
    assert lines == ["[22, 80]", "fallback", "true", "false"]


async def test_has_source_and_source_or_handle_the_none_case() -> None:
    # The first host has source_module set; the second (built with no
    # source_module kwarg) is Python's None under the hood.
    lines = await _run(
        """
set with_source = asset.by_kind(assets, "host")[0]
set without_source = asset.by_kind(assets, "host")[1]
print asset.has_source(with_source)
print asset.source_or(with_source, "unknown")
print asset.has_source(without_source)
print asset.source_or(without_source, "unknown")
"""
    )
    assert lines == ["true", "network.discover", "false", "unknown"]


async def test_summary_line() -> None:
    lines = await _run(
        """
set host = asset.by_kind(assets, "host")[0]
print asset.summary_line(host)
"""
    )
    assert lines == ["host: 192.168.1.1"]
