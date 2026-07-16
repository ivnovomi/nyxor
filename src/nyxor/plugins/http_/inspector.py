"""HTTP response inspection: headers, redirects, cookies, compression, and
common security header checks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx2 as httpx

from nyxor.plugins.http_.fingerprint import fingerprint

# Returns the IP address the caller has already validated and wants the
# connection pinned to (closing a DNS-rebinding TOCTOU — see `inspect()`),
# or None if there's nothing to pin (the target was already a literal IP,
# or the caller doesn't need pinning at all, e.g. the CLI).
ValidateUrl = Callable[[str], Awaitable[str | None]]

# Header/security-header checks and tech fingerprinting need at most a few KB
# of body (meta tags, generator strings, ...) — capping how much of the
# response we buffer keeps a target that streams an unbounded/huge response
# (deliberately or not) from being able to exhaust this process's memory.
MAX_BODY_BYTES = 2 * 1024 * 1024

SECURITY_HEADERS = (
    "strict-transport-security",
    "content-security-policy",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
)


def _describe_cookie(cookie: Any) -> dict[str, Any]:
    rest = {str(k).lower(): v for k, v in (getattr(cookie, "_rest", None) or {}).items()}
    return {
        "name": cookie.name,
        "secure": bool(cookie.secure),
        "http_only": "httponly" in rest,
        "same_site": rest.get("samesite"),
    }


async def _read_capped_body(response: httpx.Response) -> bytes:
    """Read at most MAX_BODY_BYTES of the response body, then stop.

    A malicious or misconfigured target can stream an arbitrarily large
    (even infinite) body; without a cap, buffering it all would let a single
    scanned target exhaust this process's memory.
    """
    chunks: list[bytes] = []
    total = 0
    async for chunk in response.aiter_bytes():
        remaining = MAX_BODY_BYTES - total
        if remaining <= 0:
            break
        if len(chunk) > remaining:
            chunks.append(chunk[:remaining])
            break
        chunks.append(chunk)
        total += len(chunk)
        if total >= MAX_BODY_BYTES:
            break
    return b"".join(chunks)


def _pin_url_to_ip(url: str, ip: str) -> tuple[str, str]:
    """Rewrite ``url`` to connect to ``ip`` instead of letting the HTTP

    client resolve its own hostname, returning ``(pinned_url, host_header)``.
    The caller must send ``host_header`` as both the ``Host`` header and the
    TLS SNI hostname, or the server won't recognize the request (virtual
    hosting) and/or the certificate won't validate against a bare IP.
    """
    parsed = urlsplit(url)
    host = parsed.hostname
    if not host:
        # A caller only reaches here with a pinned IP already in hand, which
        # itself only happens after validate_url successfully resolved a
        # hostname out of this same URL — an empty host at this point means
        # that invariant broke, and sending a request with a blank Host
        # header would be a confusing way to find out.
        raise ValueError(f"cannot pin {url!r}: no hostname to preserve as Host/SNI")
    host_header = host if parsed.port is None else f"{host}:{parsed.port}"
    ip_literal = f"[{ip}]" if ":" in ip else ip
    netloc = ip_literal if parsed.port is None else f"{ip_literal}:{parsed.port}"
    pinned_url = urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
    return pinned_url, host_header


async def inspect(
    url: str,
    timeout: float,
    follow_redirects: bool,
    max_redirects: int,
    *,
    validate_url: ValidateUrl | None = None,
) -> dict[str, Any]:
    """``validate_url`` (if given) is awaited on the initial URL and again on

    every redirect hop before it's fetched — redirects are followed manually
    precisely so each one can be checked, not just the URL the caller
    passed in. Callers that don't need that (the CLI, which is meant to be
    able to point at internal/private targets on purpose) simply omit it.

    When ``validate_url`` returns a pinned IP, the actual connection is made
    to that exact address instead of letting the HTTP client re-resolve the
    hostname itself — otherwise the validation above and the connection that
    follows are two independent DNS lookups, and a DNS-rebinding attacker
    (a very short TTL, a public answer for the first lookup and a private
    one for the second) can pass the check and still reach an internal
    address.
    """
    redirect_chain: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, max_redirects=max_redirects, verify=True
    ) as client:
        current_url = url
        response: httpx.Response
        body = b""
        for _ in range(max_redirects + 1):
            pinned_ip = await validate_url(current_url) if validate_url is not None else None

            request_url = current_url
            request_headers: dict[str, str] = {}
            extensions: dict[str, Any] = {}
            if pinned_ip is not None:
                request_url, host_header = _pin_url_to_ip(current_url, pinned_ip)
                request_headers["Host"] = host_header
                extensions["sni_hostname"] = urlsplit(current_url).hostname

            async with client.stream(
                "GET", request_url, headers=request_headers, extensions=extensions
            ) as response:
                if follow_redirects and response.is_redirect:
                    location = response.headers.get("location", "")
                    redirect_chain.append(
                        {
                            "url": current_url,
                            "status_code": response.status_code,
                            "location": location,
                        }
                    )
                    # Resolve against the logical (hostname-based) current_url,
                    # not the pinned request_url actually sent — otherwise a
                    # relative Location would resolve against a bare IP.
                    current_url = urljoin(current_url, location) if location else current_url
                    continue
                body = await _read_capped_body(response)
            break

    headers = dict(response.headers)
    lower_headers = {k.lower(): v for k, v in headers.items()}

    cookies = [_describe_cookie(cookie) for cookie in response.cookies.jar]

    missing_security_headers = [h for h in SECURITY_HEADERS if h not in lower_headers]

    # Only the derived tech/CDN names go into the result; the raw body itself
    # is never kept, so it can't bloat a JSON/HTML report.
    try:
        text = body.decode(response.encoding or "utf-8", errors="replace")
    except (LookupError, UnicodeDecodeError):
        text = body.decode("utf-8", errors="replace")
    fingerprint_result = fingerprint(headers, cookies, text)

    return {
        # current_url is the logical (hostname-based) URL, even when the
        # actual connection was pinned to a specific IP — reporting the raw
        # IP here would be both a behavior regression and a leak of an
        # implementation detail that means nothing to whoever reads the report.
        "final_url": current_url,
        "status_code": response.status_code,
        "headers": headers,
        "redirect_chain": redirect_chain,
        "cookies": cookies,
        "content_encoding": lower_headers.get("content-encoding"),
        "server": lower_headers.get("server"),
        "missing_security_headers": missing_security_headers,
        "technologies": fingerprint_result["technologies"],
        "cdn_waf": fingerprint_result["cdn_waf"],
    }
