"""TLS certificate and connection inspection.

Uses the stdlib ``ssl`` module to perform the handshake (so it respects the
platform's trust store and works identically on Windows/Linux/macOS) and
``cryptography`` to parse the certificate for details ``ssl`` doesn't expose.
"""

from __future__ import annotations

import socket
import ssl
from datetime import UTC, datetime
from typing import Any

from cryptography import x509

WEAK_PROTOCOLS = {"TLSv1", "TLSv1.1", "SSLv3", "SSLv2"}


def inspect(
    host: str, port: int = 443, timeout: float = 5.0, *, pinned_ip: str | None = None
) -> dict[str, Any]:
    """Connect to ``host:port``, complete a TLS handshake, and describe the certificate.

    ``pinned_ip``, if given, is what the TCP connection actually dials —
    ``host`` is still used for the TLS handshake's SNI and certificate
    hostname verification. A caller that already resolved and validated
    ``host`` (the REST API's SSRF guard) passes the specific address it
    checked here so this connection can't re-resolve to something else; a
    plain ``socket.create_connection((host, port))`` does its own DNS
    lookup, which is a second, independent resolution a DNS-rebinding
    attacker (a very short TTL, a public answer for the first lookup and a
    private one for the second) can exploit to slip past the check.
    """
    context = ssl.create_default_context()
    with (
        socket.create_connection((pinned_ip or host, port), timeout=timeout) as sock,
        context.wrap_socket(sock, server_hostname=host) as tls_sock,
    ):
        der_cert = tls_sock.getpeercert(binary_form=True)
        protocol = tls_sock.version()
        cipher = tls_sock.cipher()

    if der_cert is None:
        raise ssl.SSLError("Server did not present a certificate.")

    cert = x509.load_der_x509_certificate(der_cert)
    not_after = cert.not_valid_after_utc
    not_before = cert.not_valid_before_utc
    days_remaining = (not_after - datetime.now(UTC)).days

    try:
        san = cert.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value.get_values_for_type(x509.DNSName)
    except x509.ExtensionNotFound:
        san = []

    return {
        "subject": cert.subject.rfc4514_string(),
        "issuer": cert.issuer.rfc4514_string(),
        "not_before": not_before.isoformat(),
        "not_after": not_after.isoformat(),
        "days_remaining": days_remaining,
        "san": san,
        "protocol": protocol,
        "cipher_name": cipher[0] if cipher else None,
        "cipher_bits": cipher[2] if cipher else None,
        "serial_number": format(cert.serial_number, "x"),
    }
