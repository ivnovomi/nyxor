"""DNS record lookups, DNSSEC detection, and mail-related DNS checks.

Built on ``dnspython``'s async resolver so it composes with the rest of the
async-first Core.
"""

from __future__ import annotations

import dns.asyncresolver
import dns.exception
import dns.resolver

DEFAULT_RECORD_TYPES: tuple[str, ...] = ("A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA")

_LOOKUP_EXCEPTIONS = (
    dns.resolver.NXDOMAIN,
    dns.resolver.NoAnswer,
    dns.resolver.NoNameservers,
    dns.exception.Timeout,
)


def _make_resolver(resolvers: list[str], timeout: float) -> dns.asyncresolver.Resolver:
    resolver = dns.asyncresolver.Resolver()
    if resolvers:
        resolver.nameservers = resolvers
    resolver.timeout = timeout
    resolver.lifetime = timeout
    return resolver


async def lookup_records(
    domain: str, record_types: tuple[str, ...], resolvers: list[str], timeout: float
) -> dict[str, list[str]]:
    """Resolve each requested record type, returning an empty list on failure."""
    resolver = _make_resolver(resolvers, timeout)
    results: dict[str, list[str]] = {}
    for rtype in record_types:
        try:
            answer = await resolver.resolve(domain, rtype)
            results[rtype] = [rdata.to_text() for rdata in answer]
        except _LOOKUP_EXCEPTIONS:
            results[rtype] = []
    return results


async def check_dnssec(domain: str, resolvers: list[str], timeout: float) -> bool:
    """Best-effort check for a published DNSKEY record."""
    resolver = _make_resolver(resolvers, timeout)
    try:
        answer = await resolver.resolve(domain, "DNSKEY")
        return len(answer) > 0
    except _LOOKUP_EXCEPTIONS:
        return False


async def check_mail_records(
    domain: str, resolvers: list[str], timeout: float
) -> dict[str, object]:
    """Look up MX, SPF, and DMARC records — the basics of mail-related posture."""
    resolver = _make_resolver(resolvers, timeout)
    info: dict[str, object] = {"mx": [], "spf": None, "dmarc": None}

    try:
        mx_answer = await resolver.resolve(domain, "MX")
        info["mx"] = sorted(str(rdata.exchange).rstrip(".") for rdata in mx_answer)
    except _LOOKUP_EXCEPTIONS:
        pass

    try:
        txt_answer = await resolver.resolve(domain, "TXT")
        for rdata in txt_answer:
            text = b"".join(rdata.strings).decode("utf-8", "ignore")
            if text.startswith("v=spf1"):
                info["spf"] = text
                break
    except _LOOKUP_EXCEPTIONS:
        pass

    try:
        dmarc_answer = await resolver.resolve(f"_dmarc.{domain}", "TXT")
        for rdata in dmarc_answer:
            text = b"".join(rdata.strings).decode("utf-8", "ignore")
            if text.startswith("v=DMARC1"):
                info["dmarc"] = text
                break
    except _LOOKUP_EXCEPTIONS:
        pass

    return info
