"""HTTP response inspection: headers, redirects, cookies, compression, and
common security header checks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

import httpx

from nyxor.plugins.http_.fingerprint import fingerprint

ValidateUrl = Callable[[str], Awaitable[None]]

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
    """
    redirect_chain: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, max_redirects=max_redirects, verify=True
    ) as client:
        current_url = url
        response: httpx.Response
        body = b""
        for _ in range(max_redirects + 1):
            if validate_url is not None:
                await validate_url(current_url)
            async with client.stream("GET", current_url) as response:
                if follow_redirects and response.is_redirect:
                    location = response.headers.get("location", "")
                    redirect_chain.append(
                        {
                            "url": current_url,
                            "status_code": response.status_code,
                            "location": location,
                        }
                    )
                    current_url = (
                        str(response.next_request.url) if response.next_request else location
                    )
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
        "final_url": str(response.url),
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
