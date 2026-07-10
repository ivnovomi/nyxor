"""Passive tech-stack, CDN, and WAF fingerprinting.

100% passive: everything here reads data the HTTP inspector already
fetched for `nyx http inspect` (response headers, cookies, and the body
it downloaded anyway) — no extra requests, no active probing, no
`wafw00f`-style payload injection. Signature matching only, so false
negatives are expected (a site can always hide what it runs); false
positives are kept low by matching on headers/cookie names/markup that
are genuinely distinctive rather than generic substrings.
"""

from __future__ import annotations

import re
from typing import Any

# (header name (lowercase), optional value substring to require, tech name).
# `None` for the value substring means "present at all is enough".
_CDN_WAF_HEADER_SIGNATURES: tuple[tuple[str, str | None, str], ...] = (
    ("cf-ray", None, "Cloudflare"),
    ("cf-cache-status", None, "Cloudflare"),
    ("server", "cloudflare", "Cloudflare"),
    ("x-amz-cf-id", None, "Amazon CloudFront"),
    ("x-amz-cf-pop", None, "Amazon CloudFront"),
    ("server", "cloudfront", "Amazon CloudFront"),
    ("x-akamai-transformed", None, "Akamai"),
    ("server", "akamaighost", "Akamai"),
    ("x-sucuri-id", None, "Sucuri (WAF)"),
    ("x-sucuri-cache", None, "Sucuri (WAF)"),
    ("x-iinfo", None, "Imperva Incapsula (WAF)"),
    ("x-cdn", "incapsula", "Imperva Incapsula (WAF)"),
    ("x-served-by", None, "Fastly"),
    ("x-fastly-request-id", None, "Fastly"),
    ("via", "varnish", "Varnish"),
    ("x-azure-ref", None, "Azure Front Door"),
    ("server", "openresty", "OpenResty (nginx-based)"),
)

_TECH_HEADER_SIGNATURES: tuple[tuple[str, str | None, str], ...] = (
    ("x-powered-by", "php", "PHP"),
    ("x-powered-by", "asp.net", "ASP.NET"),
    ("x-powered-by", "express", "Express.js"),
    ("x-powered-by", "next.js", "Next.js"),
    ("server", "nginx", "nginx"),
    ("server", "apache", "Apache"),
    ("server", "microsoft-iis", "IIS"),
    ("server", "gunicorn", "Gunicorn (Python)"),
    ("server", "werkzeug", "Flask (Python)"),
    ("server", "caddy", "Caddy"),
)

# cookie name (lowercase) -> tech name.
_TECH_COOKIE_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("phpsessid", "PHP"),
    ("jsessionid", "Java (JSP/Servlet)"),
    ("asp.net_sessionid", "ASP.NET"),
    ("laravel_session", "Laravel (PHP)"),
    ("wordpress_logged_in", "WordPress"),
    ("csrftoken", "Django (Python)"),
    ("_shopify_s", "Shopify"),
)

# body substring -> tech name.
_TECH_BODY_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("wp-content", "WordPress"),
    ("wp-includes", "WordPress"),
    ("drupal.settings", "Drupal"),
    ("/sites/default/files", "Drupal"),
    ("joomla!", "Joomla"),
    ("__next_data__", "Next.js"),
    ("data-reactroot", "React"),
    ("ng-version", "Angular"),
    ("cdn.shopify.com", "Shopify"),
    ("wix.com", "Wix"),
    ("squarespace.com", "Squarespace"),
)

_META_GENERATOR_RE = re.compile(
    r'<meta[^>]+name=["\']generator["\'][^>]+content=["\']([^"\']+)["\']', re.IGNORECASE
)


def _header_matches(
    lower_headers: dict[str, str], signatures: tuple[tuple[str, str | None, str], ...]
) -> list[str]:
    """
    Identify names associated with matching HTTP header signatures.
    
    Parameters:
        lower_headers (dict[str, str]): Header names mapped to their values.
        signatures (tuple[tuple[str, str | None, str], ...]): Header signatures containing a header name, an optional value substring, and the associated name.
    
    Returns:
        list[str]: Names whose header signatures match the provided headers.
    """
    found: list[str] = []
    for header, needle, name in signatures:
        value = lower_headers.get(header)
        if value is None:
            continue
        if needle is None or needle in value.lower():
            found.append(name)
    return found


def fingerprint(
    headers: dict[str, str], cookies: list[dict[str, Any]], body: str
) -> dict[str, list[str]]:
    """
    Passively identify technologies and CDN/WAF providers from HTTP response data.
    
    Parameters:
        headers (dict[str, str]): Raw response headers.
        cookies (list[dict[str, Any]]): Response cookie dictionaries.
        body (str): Response body text.
    
    Returns:
        dict[str, list[str]]: Sorted detected technology names under `"technologies"` and CDN/WAF provider names under `"cdn_waf"`.
    """
    lower_headers = {k.lower(): v for k, v in headers.items()}
    lower_body = body.lower()

    technologies: set[str] = set(_header_matches(lower_headers, _TECH_HEADER_SIGNATURES))
    cdn_waf: set[str] = set(_header_matches(lower_headers, _CDN_WAF_HEADER_SIGNATURES))

    for cookie in cookies:
        name = str(cookie.get("name", "")).lower()
        for cookie_signature, tech in _TECH_COOKIE_SIGNATURES:
            # startswith, not ==: several of these (notably WordPress's
            # "wordpress_logged_in_<hash>") append a per-site suffix to the
            # base cookie name in real deployments.
            if name.startswith(cookie_signature):
                technologies.add(tech)

    for needle, tech in _TECH_BODY_SIGNATURES:
        if needle in lower_body:
            technologies.add(tech)

    generator_match = _META_GENERATOR_RE.search(body)
    if generator_match:
        technologies.add(generator_match.group(1).strip())

    return {
        "technologies": sorted(technologies),
        "cdn_waf": sorted(cdn_waf),
    }
