"""DNS record lookups, DNSSEC detection, and mail-related DNS checks.

Built on ``dnspython``'s async resolver so it composes with the rest of the
async-first Core.
"""

from __future__ import annotations

import asyncio

import dns.asyncresolver
import dns.exception

DEFAULT_RECORD_TYPES: tuple[str, ...] = ("A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA")

# dns.exception.DNSException is the common base for every dnspython error —
# NXDOMAIN/NoAnswer/NoNameservers/Timeout, but also malformed-name errors
# like dns.name.EmptyLabel/LabelTooLong raised for a bad input domain before
# any query is even sent. Catching only the first four left those escaping
# uncaught, crashing the whole audit/watch/trends run over one bad hostname.
_LOOKUP_EXCEPTIONS = (dns.exception.DNSException,)


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
    """Resolve each requested record type concurrently, returning an empty list on failure."""
    resolver = _make_resolver(resolvers, timeout)

    async def _resolve_one(rtype: str) -> list[str]:
        try:
            answer = await resolver.resolve(domain, rtype)
            return [rdata.to_text() for rdata in answer]
        except _LOOKUP_EXCEPTIONS:
            return []

    # Issued in parallel — sequentially, one slow/unresponsive resolver
    # response per record type could take up to len(record_types) * timeout
    # instead of ~timeout.
    values = await asyncio.gather(*(_resolve_one(rtype) for rtype in record_types))
    return dict(zip(record_types, values, strict=True))


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

    async def _mx() -> list[str]:
        try:
            answer = await resolver.resolve(domain, "MX")
            return sorted(str(rdata.exchange).rstrip(".") for rdata in answer)
        except _LOOKUP_EXCEPTIONS:
            return []

    async def _spf() -> str | None:
        try:
            answer = await resolver.resolve(domain, "TXT")
            for rdata in answer:
                text = b"".join(rdata.strings).decode("utf-8", "ignore")
                if text.startswith("v=spf1"):
                    return text
        except _LOOKUP_EXCEPTIONS:
            pass
        return None

    async def _dmarc() -> str | None:
        try:
            answer = await resolver.resolve(f"_dmarc.{domain}", "TXT")
            for rdata in answer:
                text = b"".join(rdata.strings).decode("utf-8", "ignore")
                if text.startswith("v=DMARC1"):
                    return text
        except _LOOKUP_EXCEPTIONS:
            pass
        return None

    # Three independent lookups, run concurrently instead of one after another.
    mx, spf, dmarc = await asyncio.gather(_mx(), _spf(), _dmarc())
    return {"mx": mx, "spf": spf, "dmarc": dmarc}
