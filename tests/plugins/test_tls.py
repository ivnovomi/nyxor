from __future__ import annotations

import socket
import ssl
from datetime import UTC, datetime, timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from nyxor.plugins.tls_.inspector import WEAK_PROTOCOLS, inspect
from nyxor.plugins.tls_.plugin import _parse_target, run_inspect


def test_parse_target_defaults_to_443() -> None:
    assert _parse_target("example.com") == ("example.com", 443)


def test_parse_target_honors_explicit_port() -> None:
    assert _parse_target("example.com:8443") == ("example.com", 8443)


def test_parse_target_handles_a_full_url() -> None:
    # Regression: rpartition(":") used to read "https" as the host and
    # "//example.com/" as the port for a bare `nyx audit https://...` call.
    assert _parse_target("https://example.com/") == ("example.com", 443)


def test_parse_target_handles_a_full_url_with_explicit_port() -> None:
    assert _parse_target("https://example.com:8443/path") == ("example.com", 8443)


def test_parse_target_falls_back_to_the_whole_string_on_garbage_port() -> None:
    assert _parse_target("not:a:real:port") == ("not:a:real:port", 443)


def test_parse_target_handles_a_bracketed_ipv6_literal_with_port() -> None:
    # Regression: this used to return ("[::1]:443", 443) — the whole bracket
    # notation plus the port suffix, verbatim, as the "host".
    assert _parse_target("[::1]:443") == ("::1", 443)


def test_parse_target_handles_a_bracketed_ipv6_literal_without_a_port() -> None:
    assert _parse_target("[::1]") == ("::1", 443)


def test_parse_target_handles_a_bare_ipv6_address() -> None:
    assert _parse_target("2606:4700:10::6814:179a") == ("2606:4700:10::6814:179a", 443)


def test_parse_target_handles_a_url_with_a_bracketed_ipv6_host() -> None:
    assert _parse_target("https://[::1]:8443/") == ("::1", 8443)


def test_weak_protocols_include_deprecated_tls_versions() -> None:
    assert "TLSv1" in WEAK_PROTOCOLS
    assert "TLSv1.1" in WEAK_PROTOCOLS
    assert "TLSv1.3" not in WEAK_PROTOCOLS


def _make_der_cert() -> bytes:
    """A throwaway self-signed cert — only used here to give `inspect()`

    something real to parse; TLS trust/hostname verification is bypassed
    by faking `ssl.create_default_context()` entirely, so this doesn't
    need to be trusted by anything.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "example.com")])
    now = datetime.now(UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.DER)


def test_pinned_ip_is_used_for_the_socket_connection_not_the_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Without pinning, socket.create_connection(("example.com", 443)) does
    # its own independent DNS resolution — a second, exploitable lookup a
    # DNS-rebinding attacker (public answer first, private one with a very
    # short TTL second) can use to slip past whatever validated "example.com"
    # a moment earlier. Pinning forces the connection onto that exact,
    # already-validated address instead.
    der_cert = _make_der_cert()
    seen_connect_addrs: list[tuple[str, int]] = []
    seen_sni: list[str | None] = []

    class _FakeSocket:
        def __enter__(self) -> _FakeSocket:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

    class _FakeTLSSocket:
        def __enter__(self) -> _FakeTLSSocket:
            return self

        def __exit__(self, *exc_info: object) -> None:
            return None

        def getpeercert(self, binary_form: bool = True) -> bytes:
            return der_cert

        def version(self) -> str:
            return "TLSv1.3"

        def cipher(self) -> tuple[str, str, int]:
            return ("TLS_AES_128_GCM_SHA256", "TLSv1.3", 128)

    class _FakeContext:
        def wrap_socket(self, sock: object, server_hostname: str | None = None) -> _FakeTLSSocket:
            seen_sni.append(server_hostname)
            return _FakeTLSSocket()

    def fake_create_connection(addr: tuple[str, int], timeout: float | None = None) -> _FakeSocket:
        seen_connect_addrs.append(addr)
        return _FakeSocket()

    monkeypatch.setattr(socket, "create_connection", fake_create_connection)
    monkeypatch.setattr(ssl, "create_default_context", lambda: _FakeContext())

    inspect("example.com", 443, 5.0, pinned_ip="93.184.216.34")

    assert seen_connect_addrs == [("93.184.216.34", 443)]
    # The TLS handshake's SNI/certificate-hostname check must still use the
    # real hostname, not the IP -- a cert for "example.com" won't validate
    # against a bare address.
    assert seen_sni == ["example.com"]


async def test_run_inspect_pins_the_connection_to_validate_urls_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_calls: list[dict[str, object]] = []
    seen_hosts: list[str] = []

    def fake_inspect(host: str, port: int, timeout: float, *, pinned_ip: str | None = None):
        seen_calls.append({"host": host, "port": port, "pinned_ip": pinned_ip})
        return {
            "subject": "CN=example.com",
            "issuer": "CN=example.com",
            "not_before": "2026-01-01T00:00:00+00:00",
            "not_after": "2026-12-31T00:00:00+00:00",
            "days_remaining": 300,
            "san": [],
            "protocol": "TLSv1.3",
            "cipher_name": "TLS_AES_128_GCM_SHA256",
            "cipher_bits": 128,
            "serial_number": "1",
        }

    monkeypatch.setattr("nyxor.plugins.tls_.plugin.inspect", fake_inspect)

    async def validate_url(host: str) -> str | None:
        seen_hosts.append(host)
        return "93.184.216.34"

    await run_inspect("example.com:443", 5.0, validate_url=validate_url)

    assert seen_hosts == ["example.com"]
    assert seen_calls == [{"host": "example.com", "port": 443, "pinned_ip": "93.184.216.34"}]
