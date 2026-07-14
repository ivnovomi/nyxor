from __future__ import annotations

import pytest

from nyxor.core.config import load_config
from nyxor.core.scripting import run_script
from nyxor.core.scripting.builtins import (
    _build_icmp_echo,
    _build_ip_header,
    _build_tcp_header,
    _build_udp_header,
    _internet_checksum,
)
from nyxor.core.scripting.errors import RuntimeScriptError


async def _run(source: str) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append)
    return lines


# ---------- checksum() ----------


async def test_checksum_builtin_matches_the_python_reference_implementation() -> None:
    data = [69, 0, 0, 28, 0, 1, 0, 0, 64, 1, 0, 0, 127, 0, 0, 1, 127, 0, 0, 1]
    lines = await _run(f"print checksum({data})\n")
    assert lines == [str(_internet_checksum(bytes(data)))]


async def test_checksum_rejects_a_non_list() -> None:
    with pytest.raises(RuntimeScriptError, match="checksum"):
        await _run('checksum("not a list")\n')


# ---------- build_ip_header() ----------


def test_build_ip_header_self_checksums_to_zero() -> None:
    # A packet's own checksum makes the whole header sum to 0 under the
    # one's-complement algorithm — the standard way to self-verify a
    # checksum implementation without an external reference packet.
    header = _build_ip_header(["10.0.0.1", "10.0.0.2", 6, [1, 2, 3]])
    assert len(header) == 20
    assert _internet_checksum(bytes(header)) == 0


def test_build_ip_header_encodes_version_ihl_and_addresses() -> None:
    header = _build_ip_header(["192.168.1.10", "192.168.1.20", 17, [], 32, 999, True])
    assert header[0] == 0x45  # version 4, IHL 5
    assert header[8] == 32  # ttl
    assert header[9] == 17  # protocol
    assert header[12:16] == [192, 168, 1, 10]
    assert header[16:20] == [192, 168, 1, 20]
    assert header[6] & 0x40  # don't-fragment bit set


def test_build_ip_header_rejects_an_invalid_ip() -> None:
    with pytest.raises(ValueError, match="invalid IPv4 address"):
        _build_ip_header(["not-an-ip", "10.0.0.2", 6, []])


async def test_build_ip_header_from_nyxscript() -> None:
    lines = await _run(
        'set h = build_ip_header("10.0.0.1", "10.0.0.2", 6, [])\nprint len(h)\nprint checksum(h)\n'
    )
    assert lines[0] == "20"
    assert lines[1] == "0"


# ---------- build_tcp_header() ----------


def test_build_tcp_header_self_checksums_to_zero_with_pseudo_header() -> None:
    src, dst = "10.0.0.1", "10.0.0.2"
    payload = [9, 9]
    header = _build_tcp_header([src, dst, 12345, 80, 1000, 0, "SYN", payload])
    assert len(header) == 20
    pseudo = bytes([10, 0, 0, 1, 10, 0, 0, 2, 0, 6]) + (20 + len(payload)).to_bytes(2, "big")
    assert _internet_checksum(pseudo + bytes(header) + bytes(payload)) == 0


def test_build_tcp_header_accepts_flags_as_a_string() -> None:
    header = _build_tcp_header(["10.0.0.1", "10.0.0.2", 1, 2, 0, 0, "SYN,ACK", []])
    assert header[13] == 0x12  # SYN | ACK


def test_build_tcp_header_rejects_an_unknown_flag_name() -> None:
    with pytest.raises(ValueError, match="unknown flag"):
        _build_tcp_header(["10.0.0.1", "10.0.0.2", 1, 2, 0, 0, "BOGUS", []])


def test_build_tcp_header_rejects_an_out_of_range_port() -> None:
    with pytest.raises(ValueError, match="out of range"):
        _build_tcp_header(["10.0.0.1", "10.0.0.2", 999999, 2, 0, 0, "SYN", []])


# ---------- build_udp_header() ----------


def test_build_udp_header_self_checksums_to_zero_with_pseudo_header() -> None:
    src, dst = "10.0.0.1", "10.0.0.2"
    payload = [1, 2, 3]
    header = _build_udp_header([src, dst, 12345, 53, payload])
    assert len(header) == 8
    pseudo = bytes([10, 0, 0, 1, 10, 0, 0, 2, 0, 17]) + (8 + len(payload)).to_bytes(2, "big")
    assert _internet_checksum(pseudo + bytes(header) + bytes(payload)) == 0


def test_build_udp_header_length_field() -> None:
    header = _build_udp_header(["10.0.0.1", "10.0.0.2", 1, 2, [0, 0, 0]])
    assert int.from_bytes(bytes(header[4:6]), "big") == 11  # 8-byte header + 3-byte payload


# ---------- build_icmp_echo() ----------


def test_build_icmp_echo_self_checksums_to_zero() -> None:
    packet = _build_icmp_echo([1, 1, [0xAA, 0xBB]])
    assert _internet_checksum(bytes(packet)) == 0


def test_build_icmp_echo_type_byte_distinguishes_request_and_reply() -> None:
    request = _build_icmp_echo([1, 1, []])
    reply = _build_icmp_echo([1, 1, [], True])
    assert request[0] == 8
    assert reply[0] == 0
