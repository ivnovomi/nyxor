"""HTTP response inspection: headers, redirects, cookies, compression, and
common security header checks."""

from __future__ import annotations

from typing import Any

import httpx

from nyxor.plugins.http_.fingerprint import fingerprint

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


async def inspect(
    url: str, timeout: float, follow_redirects: bool, max_redirects: int
) -> dict[str, Any]:
    """
    Inspect a URL and collect response metadata, redirect information, cookies, security header gaps, and fingerprints.
    
    Parameters:
    	url (str): URL to request.
    	timeout (float): Maximum time allowed for the HTTP request.
    	follow_redirects (bool): Whether to follow redirects.
    	max_redirects (int): Maximum number of redirects to follow.
    
    Returns:
    	dict[str, Any]: Response details including the final URL, status code, headers, redirect chain, cookies, missing security headers, detected technologies, and CDN/WAF fingerprints.
    """
    redirect_chain: list[dict[str, Any]] = []

    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False, max_redirects=max_redirects, verify=True
    ) as client:
        current_url = url
        response: httpx.Response | None = None
        for _ in range(max_redirects + 1):
            response = await client.get(current_url)
            if follow_redirects and response.is_redirect:
                location = response.headers.get("location", "")
                redirect_chain.append(
                    {"url": current_url, "status_code": response.status_code, "location": location}
                )
                current_url = str(response.next_request.url) if response.next_request else location
                continue
            break

        assert response is not None

    headers = dict(response.headers)
    lower_headers = {k.lower(): v for k, v in headers.items()}

    cookies = [_describe_cookie(cookie) for cookie in response.cookies.jar]

    missing_security_headers = [h for h in SECURITY_HEADERS if h not in lower_headers]

    # `response.text` is already fully buffered in memory (a plain client.get(),
    # not a stream) — reading it here for signature matching costs no extra
    # request. Only the derived tech/CDN names go into the result; the raw
    # body itself is never kept, so it can't bloat a JSON/HTML report.
    try:
        body = response.text
    except Exception:  # undecodable body (binary response, bad charset, ...)
        body = ""
    fingerprint_result = fingerprint(headers, cookies, body)

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
