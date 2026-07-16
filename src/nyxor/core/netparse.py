"""Shared host[:port] / URL parsing for CLI targets.

Several plugins accept the same flexible target syntax — a bare hostname,
``host:port``, a bracketed IPv6 literal, or a full URL — and need to pull
the host (and sometimes port) back out of it before handing it to DNS, TLS,
or a socket connection.
"""

from __future__ import annotations

from urllib.parse import urlsplit


def split_host_port(target: str, default_port: int) -> tuple[str, int]:
    """Split TARGET into ``(host, port)``.

    Accepts a full URL (``https://example.com:8443/path``), a bracketed
    IPv6 literal (``[::1]:443`` or bare ``[::1]``), ``host:port``, or a bare
    host/IP. Falls back to ``(target, default_port)`` when nothing else
    matches, including a bare IPv6 address (which has more than one colon
    and is therefore never mistaken for a ``host:port`` pair). Leading/
    trailing whitespace is stripped first, so a value copy-pasted with a
    stray space or newline (common from CLI args, config files) doesn't
    get treated as part of the hostname.
    """
    target = target.strip()

    if "://" in target:
        parsed = urlsplit(target)
        if parsed.hostname:
            return parsed.hostname, parsed.port or default_port

    if target.startswith("["):
        closing = target.find("]")
        if closing != -1:
            host = target[1:closing]
            rest = target[closing + 1 :]
            if rest.startswith(":") and rest[1:].isdigit():
                return host, int(rest[1:])
            return host, default_port

    if target.count(":") == 1:
        host, _, port_str = target.rpartition(":")
        if port_str.isdigit():
            return host, int(port_str)

    return target, default_port
