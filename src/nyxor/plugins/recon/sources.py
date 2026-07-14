"""Passive subdomain discovery — certificate transparency logs.

Nothing here ever sends a packet to the target: `crt.sh` is a public,
third-party archive of certificates already issued for a domain (anyone
running a CT-logged CA has to publish them, by design — that's the whole
point of Certificate Transparency). Reading that log is exactly as passive
as looking up a domain's WHOIS record.
"""

from __future__ import annotations

import httpx

CRTSH_URL = "https://crt.sh/"


async def crtsh_subdomains(domain: str, timeout: float = 15.0) -> set[str]:
    """Every hostname crt.sh has ever seen a certificate for under `domain`.

    Returns an empty set (never raises) on any network/parse failure —
    crt.sh is a free public service with no uptime guarantee, and a recon
    scan shouldn't die just because it's having a bad day.
    """
    params = {"q": f"%.{domain}", "output": "json"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(CRTSH_URL, params=params)
            response.raise_for_status()
            entries = response.json()
    except (httpx.HTTPError, ValueError):
        return set()

    # crt.sh (or a proxy/CDN in front of it) can return well-formed JSON
    # that isn't the expected list of certificate entries — e.g. a rate-limit
    # or maintenance response like {"error": "..."}. That's still a "having
    # a bad day" case this function promises never to raise for.
    if not isinstance(entries, list):
        return set()

    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        raw = entry.get("name_value", "")
        for name in raw.splitlines():
            name = name.strip().lower()
            if not name or name.startswith("*."):
                name = name.removeprefix("*.")
            if name and (name == domain or name.endswith(f".{domain}")):
                names.add(name)
    return names
