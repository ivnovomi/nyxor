"""Optional VirusTotal file-hash reputation lookup — off unless you ask.

Needs your own free VirusTotal API key (no NYXOR account, no NYXOR-run
service sitting in the middle). Without one, `hostcheck` runs on local
heuristics only — no network calls, no signup required, genuinely free.
This only ever looks up a hash that's already been computed locally;
nothing is uploaded anywhere.
"""

from __future__ import annotations

import hashlib

import httpx

VT_FILE_URL = "https://www.virustotal.com/api/v3/files/{sha256}"
_MAX_HASH_BYTES = 200 * 1024 * 1024


def sha256_of(path: str, *, max_bytes: int = _MAX_HASH_BYTES) -> str | None:
    """SHA-256 of a local file, or None if it can't be read (or is huge)."""
    digest = hashlib.sha256()
    size = 0
    try:
        with open(path, "rb") as handle:
            while chunk := handle.read(65536):
                size += len(chunk)
                if size > max_bytes:
                    return None
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


async def check_hash(sha256: str, api_key: str, *, timeout: float = 15.0) -> dict[str, int] | None:
    """VirusTotal's engine-vote counts for a hash it already knows, or None."""
    headers = {"x-apikey": api_key}
    url = VT_FILE_URL.format(sha256=sha256)
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(url, headers=headers)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    stats = data.get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
    return {
        "malicious": int(stats.get("malicious", 0)),
        "suspicious": int(stats.get("suspicious", 0)),
        "harmless": int(stats.get("harmless", 0)),
    }
