from __future__ import annotations

import pytest

from nyxor.api.app import _hostname_from_target


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "example.com"),
        ("example.com:443", "example.com"),
        ("https://example.com/path", "example.com"),
        ("http://example.com:8080/x?y=1", "example.com"),
        ("8.8.8.8", "8.8.8.8"),
        ("8.8.8.8:53", "8.8.8.8"),
        ("2001:4860:4860::8888", "2001:4860:4860::8888"),
        ("[::1]:443", "::1"),
        ("[2001:4860:4860::8888]:443", "2001:4860:4860::8888"),
    ],
)
def test_hostname_from_target(raw: str, expected: str) -> None:
    assert _hostname_from_target(raw) == expected


def test_audit_endpoint_rejects_loopback_literal(nyxor_test_client) -> None:
    resp = nyxor_test_client.get("/dns/127.0.0.1")
    assert resp.status_code == 400
    assert "non-public" in resp.json()["detail"]


def test_audit_endpoint_rejects_localhost_hostname(nyxor_test_client) -> None:
    resp = nyxor_test_client.get("/tls/localhost:443")
    assert resp.status_code == 400


def test_http_endpoint_rejects_metadata_ip(nyxor_test_client) -> None:
    resp = nyxor_test_client.get(
        "/http", params={"url": "http://169.254.169.254/latest/meta-data/"}
    )
    assert resp.status_code == 400


def test_audit_endpoint_rejects_private_ip_literal(nyxor_test_client) -> None:
    resp = nyxor_test_client.get("/dns/10.0.0.5")
    assert resp.status_code == 400
