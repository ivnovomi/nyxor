from __future__ import annotations

import dns.name
import dns.resolver
import pytest

from nyxor.plugins.dns_.lookups import (
    DEFAULT_RECORD_TYPES,
    check_dnssec,
    check_mail_records,
    lookup_records,
)


class _FakeRdata:
    def __init__(self, text: str) -> None:
        self._text = text

    def to_text(self) -> str:
        return self._text


class _FakeAnswer(list):
    pass


@pytest.mark.asyncio
async def test_lookup_records_returns_values(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(self, domain: str, rtype: str):
        if rtype == "A":
            return _FakeAnswer([_FakeRdata("93.184.216.34")])
        raise dns.resolver.NoAnswer()

    monkeypatch.setattr("dns.asyncresolver.Resolver.resolve", fake_resolve)

    results = await lookup_records("example.com", ("A", "AAAA"), [], 1.0)

    assert results["A"] == ["93.184.216.34"]
    assert results["AAAA"] == []


@pytest.mark.asyncio
async def test_check_dnssec_false_when_no_dnskey(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(self, domain: str, rtype: str):
        raise dns.resolver.NXDOMAIN()

    monkeypatch.setattr("dns.asyncresolver.Resolver.resolve", fake_resolve)

    assert await check_dnssec("example.com", [], 1.0) is False


@pytest.mark.asyncio
async def test_check_mail_records_handles_missing_records(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_resolve(self, domain: str, rtype: str):
        raise dns.resolver.NoAnswer()

    monkeypatch.setattr("dns.asyncresolver.Resolver.resolve", fake_resolve)

    info = await check_mail_records("example.com", [], 1.0)

    assert info == {"mx": [], "spf": None, "dmarc": None}


@pytest.mark.asyncio
async def test_lookup_records_does_not_crash_on_a_malformed_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A malformed hostname (empty label, label too long, ...) makes dnspython
    # raise a dns.name.* error, not one of the NXDOMAIN/NoAnswer/NoNameservers
    # /Timeout family — this must be swallowed the same way, not propagate
    # and take the whole audit/watch/trends run down with it.
    async def fake_resolve(self, domain: str, rtype: str):
        raise dns.name.EmptyLabel()

    monkeypatch.setattr("dns.asyncresolver.Resolver.resolve", fake_resolve)

    results = await lookup_records("exa..mple.com", DEFAULT_RECORD_TYPES, [], 1.0)

    assert all(values == [] for values in results.values())


@pytest.mark.asyncio
async def test_check_mail_records_does_not_crash_on_a_malformed_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_resolve(self, domain: str, rtype: str):
        raise dns.name.LabelTooLong()

    monkeypatch.setattr("dns.asyncresolver.Resolver.resolve", fake_resolve)

    info = await check_mail_records("exa..mple.com", [], 1.0)

    assert info == {"mx": [], "spf": None, "dmarc": None}
