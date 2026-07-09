from __future__ import annotations

from nyxor.plugins.tls_.inspector import WEAK_PROTOCOLS
from nyxor.plugins.tls_.plugin import _parse_target


def test_parse_target_defaults_to_443() -> None:
    assert _parse_target("example.com") == ("example.com", 443)


def test_parse_target_honors_explicit_port() -> None:
    assert _parse_target("example.com:8443") == ("example.com", 8443)


def test_weak_protocols_include_deprecated_tls_versions() -> None:
    assert "TLSv1" in WEAK_PROTOCOLS
    assert "TLSv1.1" in WEAK_PROTOCOLS
    assert "TLSv1.3" not in WEAK_PROTOCOLS
