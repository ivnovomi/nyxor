"""``--dumber``: plain-language, no-jargon explanations for findings.

Purely templated — no LLM call, no network access beyond what the scan
itself already made. A keyword on the finding's title picks a hand-written
explainer; anything that doesn't match falls back to a generic,
severity-flavored one-liner. Deliberately a little irreverent — this is
the "explain it to me like I'm five, and also make it fun" mode, not the
report you hand to an auditor.
"""

from __future__ import annotations

from collections.abc import Callable

from nyxor.core.models import Finding, Severity

ExplainFn = Callable[[Finding], str]

_SEVERITY_TAKE: dict[Severity, str] = {
    Severity.CRITICAL: "Drop everything — this is the kind of thing that ends up on the news.",
    Severity.HIGH: "Worth fixing soon. This is a real crack in the armor, not a nitpick.",
    Severity.MEDIUM: "Not on fire, but put it on the to-do list.",
    Severity.LOW: "Minor. Nice to fix, nobody's losing sleep over it.",
    Severity.INFO: "Just FYI — no action needed, it's context, not a complaint.",
}


def _dnssec(f: Finding) -> str:
    if "dnskey" not in f.description.lower() or "not enabled" in f.description.lower():
        return (
            "DNSSEC is a cryptographic signature proving DNS answers weren't tampered "
            "with on the way to you. This domain doesn't have one, so — in theory — "
            "someone sitting on the network path could feed a visitor a fake address "
            "for it. Rare in practice, but it's the seatbelt nobody's wearing."
        )
    return (
        "DNSSEC is switched on: DNS answers for this domain are cryptographically "
        "signed, so they can't be quietly swapped out in transit. Nice."
    )


def _spf(f: Finding) -> str:
    if "no spf" in f.description.lower():
        return (
            "SPF is a list of which mail servers are allowed to send email pretending "
            "to be from this domain. There isn't one, so anybody could try to forge "
            "email 'from' this address — and a lot of it would sail right through."
        )
    return (
        "SPF record found: it lists which mail servers may legitimately send email as "
        "this domain, which makes forging convincing spoofed email harder."
    )


def _dmarc(f: Finding) -> str:
    if "no dmarc" in f.description.lower():
        return (
            "DMARC tells mailbox providers what to do with email that fails "
            "authentication — reject it, quarantine it, or shrug and deliver it "
            "anyway. Without one, spoofed email impersonating this domain has a "
            "better shot at landing in someone's inbox looking legit."
        )
    return (
        "DMARC record found: it tells mailbox providers what to do with email that "
        "fails authentication, which cuts down on convincing spoofed mail."
    )


def _cert_expiration(f: Finding) -> str:
    return (
        f"{f.description} Certificates are how your browser knows it's actually "
        "talking to the real site and not an impostor — once one expires, browsers "
        "throw up a big scary red warning page."
    )


def _cert_subject(f: Finding) -> str:
    return (
        f"{f.description} — this is 'who is this certificate actually for, and who "
        "vouched for them,' the info your browser checks before it trusts the "
        "padlock icon."
    )


def _tls_protocol(f: Finding) -> str:
    return (
        f"{f.description} — newer TLS versions are faster and close old cryptographic "
        "holes. This is the 'how' behind the padlock icon in the address bar."
    )


def _tls_cipher(f: Finding) -> str:
    return (
        f"{f.description} — the actual lock-and-key algorithm scrambling traffic "
        "between you and the site. Bigger numbers (256 > 128) roughly mean "
        "'harder to brute-force,' though the algorithm choice matters more than size."
    )


def _security_headers(f: Finding) -> str:
    return (
        "These are optional instructions a site can send telling browsers to lock "
        "things down harder — block clickjacking, stop weird cross-site scripts, "
        "force HTTPS, and so on. Missing ones aren't an open door by themselves, but "
        "they're free seatbelts this site isn't wearing."
    )


def _cookie(f: Finding) -> str:
    if f.severity == Severity.INFO:
        return (
            "This cookie is locked down properly: JavaScript can't read it, and it "
            "only ever travels over an encrypted connection."
        )
    return (
        f"{f.description}. In practice, a cookie missing these flags is easier to "
        "steal via an injected script, or by snooping unencrypted traffic on a "
        "shared network (coffee shop wifi, etc)."
    )


def _redirect(f: Finding) -> str:
    return f"The site bounces visitors through a chain before landing: {f.description}"


def _response_status(f: Finding) -> str:
    return (
        f"{f.description} — this is just 'the site answered, here's the HTTP status "
        "code it gave back.'"
    )


def _compression(f: Finding) -> str:
    return (
        f"{f.description} — the server is shrinking the page before sending it, so it "
        "loads faster. Purely a performance thing."
    )


def _dns_record(f: Finding) -> str:
    return f"{f.description} — routine DNS bookkeeping, not a security finding by itself."


def _detected_technology(f: Finding) -> str:
    return (
        f"Passive fingerprinting picked up: {f.description}. Read from response headers, "
        "cookie names, and page markup — nothing was probed or guessed at, so treat it as "
        "a hint, not a certainty (sites can and do hide what they run)."
    )


def _cdn_waf(f: Finding) -> str:
    return (
        f"Traffic to this site passes through: {f.description}. That's the service sitting "
        "in front of the real server, caching content and often filtering out obviously "
        "malicious requests before they ever reach it."
    )


_EXPLAINERS: list[tuple[str, ExplainFn]] = [
    ("dnssec", _dnssec),
    ("spf record", _spf),
    ("dmarc record", _dmarc),
    ("certificate expiration", _cert_expiration),
    ("certificate subject", _cert_subject),
    ("negotiated tls protocol", _tls_protocol),
    ("negotiated cipher", _tls_cipher),
    ("missing security headers", _security_headers),
    ("cookie:", _cookie),
    ("redirect chain", _redirect),
    ("response status", _response_status),
    ("compression", _compression),
    ("detected technology", _detected_technology),
    ("cdn / waf", _cdn_waf),
    ("record(s)", _dns_record),
]


def explain(finding: Finding) -> str:
    """A plain-language, no-jargon take on a single finding — templated, not AI."""
    title_lower = finding.title.lower()
    for keyword, fn in _EXPLAINERS:
        if keyword in title_lower:
            return fn(finding)
    description = finding.description or "No further detail attached to this one."
    return f"{description} {_SEVERITY_TAKE[finding.severity]}"
