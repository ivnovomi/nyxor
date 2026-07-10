from __future__ import annotations

from nyxor.core.explain import explain
from nyxor.core.models import Finding, Severity


def _finding(title: str, description: str, severity: Severity = Severity.INFO) -> Finding:
    return Finding(title=title, description=description, severity=severity)


def test_dnssec_present_and_absent_get_different_explanations() -> None:
    present = explain(_finding("DNSSEC", "DNSKEY record published."))
    absent = explain(_finding("DNSSEC", "No DNSKEY record found — DNSSEC likely not enabled."))

    assert "signed" in present
    assert "someone sitting on the network path" in absent
    assert present != absent


def test_spf_absent_explains_the_risk() -> None:
    text = explain(_finding("SPF record", "No SPF record found."))
    assert "forge" in text.lower()


def test_missing_security_headers_gets_a_plain_explanation() -> None:
    text = explain(_finding("Missing security headers", "x-frame-options, ..."))
    assert "clickjacking" in text


def test_cookie_finding_distinguishes_secure_from_insecure() -> None:
    secure = explain(_finding("Cookie: session", "Secure, HttpOnly, and SameSite are all set."))
    insecure = explain(
        _finding("Cookie: session", "missing Secure, missing HttpOnly", severity=Severity.MEDIUM)
    )
    assert "locked down properly" in secure
    assert "steal" in insecure


def test_unknown_finding_falls_back_to_a_severity_flavored_generic_line() -> None:
    text = explain(
        _finding("Some brand-new check nobody templated yet", "raw detail", Severity.HIGH)
    )
    assert "raw detail" in text
    assert "crack in the armor" in text


def test_every_severity_has_a_fallback_take() -> None:
    for severity in Severity:
        text = explain(_finding("Untemplated thing", "detail", severity))
        assert text
