from __future__ import annotations

import asyncio
import datetime
import ssl
from collections.abc import AsyncIterator

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from nyxor.core.config import load_config
from nyxor.core.scripting import run_script
from nyxor.core.scripting.errors import RuntimeScriptError


def _make_self_signed_cert() -> tuple[bytes, bytes]:
    """A throwaway self-signed cert/key pair for a local TLS test server —

    deliberately untrusted by any real CA, so it's a good stand-in for
    "a host with an invalid cert" when testing socket.connect_tls's
    verify=true/false behavior without touching the real network.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.datetime.now(datetime.UTC)
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - datetime.timedelta(minutes=5))
        .not_valid_after(now + datetime.timedelta(minutes=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    cert_pem = cert.public_bytes(serialization.Encoding.PEM)
    key_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return cert_pem, key_pem


async def _tls_echo(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    data = await reader.read(4096)
    writer.write(b"TLS-ECHO:" + data)
    await writer.drain()
    writer.close()


@pytest.fixture
async def tls_echo_server(tmp_path) -> AsyncIterator[int]:
    cert_pem, key_pem = _make_self_signed_cert()
    cert_path = tmp_path / "cert.pem"
    key_path = tmp_path / "key.pem"
    cert_path.write_bytes(cert_pem)
    key_path.write_bytes(key_pem)

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert_path), str(key_path))

    server = await asyncio.start_server(_tls_echo, "127.0.0.1", 0, ssl=context)
    port = server.sockets[0].getsockname()[1]
    async with server:
        task = asyncio.ensure_future(server.serve_forever())
        try:
            yield port
        finally:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task


async def _run(source: str) -> list[str]:
    lines: list[str] = []
    await run_script(source, load_config(), output=lines.append, unsafe=True)
    return lines


async def test_connect_tls_with_verify_false_succeeds_against_a_self_signed_cert(
    tls_echo_server: int,
) -> None:
    lines = await _run(
        f"""
set h = socket.connect_tls("127.0.0.1", {tls_echo_server}, 5.0, false)
socket.send(h, "hello")
print socket.recv_text(h, 4096, 5.0)
socket.close(h)
"""
    )
    assert lines == ["TLS-ECHO:hello"]


async def test_connect_tls_with_verify_true_rejects_a_self_signed_cert(
    tls_echo_server: int,
) -> None:
    with pytest.raises(RuntimeScriptError, match="handshake"):
        await _run(f'socket.connect_tls("127.0.0.1", {tls_echo_server}, 5.0)\n')


async def test_connect_tls_is_refused_without_unsafe(tls_echo_server: int) -> None:
    lines: list[str] = []
    with pytest.raises(RuntimeScriptError, match="'socket' is disabled by default"):
        await run_script(
            f'socket.connect_tls("127.0.0.1", {tls_echo_server})\n',
            load_config(),
            output=lines.append,
            unsafe=False,
        )
