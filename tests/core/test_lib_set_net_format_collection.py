from __future__ import annotations

from pathlib import Path

from nyxor.core.config import load_config
from nyxor.core.scripting import lint_source, run_script

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULES = ("set", "net", "format", "collection")


def test_new_lib_modules_lint_clean() -> None:
    for name in _MODULES:
        source = (_REPO_ROOT / "lib" / f"{name}.nyx").read_text(encoding="utf-8")
        assert lint_source(source) == [], f"lib/{name}.nyx has lint issues"


async def _run(body: str) -> list[str]:
    lines: list[str] = []
    imports = "".join(f'import "lib/{name}.nyx" as {name}\n' for name in _MODULES)
    await run_script(imports + body, load_config(), output=lines.append, base_dir=_REPO_ROOT)
    return lines


# ---------- lib/set.nyx ----------


async def test_set_union_dedupes_across_both_lists() -> None:
    lines = await _run("print set.union([1, 2, 3], [3, 4])\n")
    assert lines == ["[1, 2, 3, 4]"]


async def test_set_intersect_keeps_only_shared_items() -> None:
    lines = await _run("print set.intersect([1, 2, 3], [2, 3, 4])\n")
    assert lines == ["[2, 3]"]


async def test_set_difference_keeps_items_unique_to_a() -> None:
    lines = await _run("print set.difference([1, 2, 3], [2, 3])\n")
    assert lines == ["[1]"]


async def test_set_symmetric_difference() -> None:
    lines = await _run("print set.symmetric_difference([1, 2], [2, 3])\n")
    assert lines == ["[1, 3]"]


async def test_set_is_subset() -> None:
    lines = await _run(
        """
print set.is_subset([1, 2], [1, 2, 3])
print set.is_subset([1, 9], [1, 2, 3])
"""
    )
    assert lines == ["true", "false"]


async def test_set_is_disjoint() -> None:
    lines = await _run(
        """
print set.is_disjoint([1, 2], [3, 4])
print set.is_disjoint([1, 2], [2, 3])
"""
    )
    assert lines == ["true", "false"]


# ---------- lib/net.nyx ----------


async def test_host_from_target_handles_a_full_url() -> None:
    lines = await _run('print net.host_from_target("https://example.com:8443/path")\n')
    assert lines == ["example.com"]


async def test_host_from_target_handles_host_port() -> None:
    lines = await _run('print net.host_from_target("example.com:443")\n')
    assert lines == ["example.com"]


async def test_host_from_target_handles_bracketed_ipv6() -> None:
    lines = await _run('print net.host_from_target("[::1]:443")\n')
    assert lines == ["::1"]


async def test_host_from_target_passes_through_a_bare_ipv6_literal() -> None:
    # A bare (unbracketed) IPv6 address has multiple colons, so it must not
    # be mistaken for a host:port pair and truncated at the first one.
    lines = await _run('print net.host_from_target("2001:4860:4860::8888")\n')
    assert lines == ["2001:4860:4860::8888"]


async def test_port_from_target_parses_a_valid_port() -> None:
    lines = await _run('print net.port_from_target("example.com:8443", 443)\n')
    assert lines == ["8443"]


async def test_port_from_target_falls_back_to_the_default() -> None:
    lines = await _run('print net.port_from_target("example.com", 443)\n')
    assert lines == ["443"]


async def test_is_private_ipv4_flags_rfc1918_and_loopback() -> None:
    lines = await _run(
        """
print net.is_private_ipv4("10.0.0.5")
print net.is_private_ipv4("192.168.1.1")
print net.is_private_ipv4("127.0.0.1")
print net.is_private_ipv4("169.254.1.1")
print net.is_private_ipv4("172.20.0.1")
"""
    )
    assert lines == ["true", "true", "true", "true", "true"]


async def test_is_private_ipv4_is_precise_about_the_172_range() -> None:
    # 172.16.0.0/12 only covers the second octet 16-31 — a naive "starts
    # with 172" check would wrongly flag 172.10.x.x or 172.32.x.x as private.
    lines = await _run(
        """
print net.is_private_ipv4("172.10.0.1")
print net.is_private_ipv4("172.32.0.1")
"""
    )
    assert lines == ["false", "false"]


async def test_is_private_ipv4_rejects_public_addresses() -> None:
    lines = await _run('print net.is_private_ipv4("8.8.8.8")\n')
    assert lines == ["false"]


async def test_is_private_ipv4_rejects_a_malformed_address() -> None:
    lines = await _run('print net.is_private_ipv4("not-an-ip")\n')
    assert lines == ["false"]


# ---------- lib/format.nyx ----------


async def test_pad_left_and_pad_right() -> None:
    lines = await _run(
        """
print format.pad_left("7", 3, "0")
print format.pad_right("ab", 5, ".")
"""
    )
    assert lines == ["007", "ab..."]


async def test_human_bytes_scales_units() -> None:
    lines = await _run(
        """
print format.human_bytes(512)
print format.human_bytes(1536)
"""
    )
    assert lines == ["512 B", "1.5 KB"]


async def test_human_duration_drops_zero_leading_units() -> None:
    lines = await _run(
        """
print format.human_duration(3725)
print format.human_duration(65)
print format.human_duration(5)
"""
    )
    assert lines == ["1h 2m 5s", "1m 5s", "5s"]


async def test_bullet_list_joins_with_newlines() -> None:
    lines = await _run('print format.bullet_list(["a", "b"])\n')
    assert lines == ["- a\n- b"]


# ---------- lib/collection.nyx additions ----------


async def test_flatten_concatenates_one_level() -> None:
    lines = await _run("print collection.flatten([[1, 2], [3], [4, 5]])\n")
    assert lines == ["[1, 2, 3, 4, 5]"]


async def test_partition_splits_by_predicate() -> None:
    lines = await _run("print collection.partition([1, 2, 3, 4], lambda(x): x > 2)\n")
    assert lines == ["[[3, 4], [1, 2]]"]


async def test_take_and_drop() -> None:
    lines = await _run(
        """
print collection.take([1, 2, 3, 4, 5], 2)
print collection.drop([1, 2, 3, 4, 5], 2)
print collection.take([1, 2], 10)
print collection.drop([1, 2], 10)
"""
    )
    assert lines == ["[1, 2]", "[3, 4, 5]", "[1, 2]", "[]"]


async def test_sum_by_maps_then_sums() -> None:
    lines = await _run("print collection.sum_by([1, 2, 3], lambda(x): x * x)\n")
    assert lines == ["14"]
