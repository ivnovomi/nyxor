from __future__ import annotations

from nyxor.plugins.tls_.inspector import WEAK_PROTOCOLS
from nyxor.plugins.tls_.plugin import _parse_target


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
