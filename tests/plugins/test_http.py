from __future__ import annotations

from http.cookiejar import Cookie

import pytest

from nyxor.core.config import HttpConfig
from nyxor.plugins.http_ import plugin as http_plugin
from nyxor.plugins.http_.inspector import SECURITY_HEADERS, _describe_cookie


def _make_cookie(secure: bool, rest: dict) -> Cookie:
    return Cookie(
        version=0,
        name="session",
        value="abc",
        port=None,
        port_specified=False,
        domain="example.com",
        domain_specified=True,
        domain_initial_dot=False,
        path="/",
        path_specified=True,
        secure=secure,
        expires=None,
        discard=True,
        comment=None,
        comment_url=None,
        rest=rest,
    )


def test_describe_cookie_flags_missing_attributes() -> None:
    cookie = _make_cookie(secure=False, rest={})
    info = _describe_cookie(cookie)

    assert info == {"name": "session", "secure": False, "http_only": False, "same_site": None}


def test_describe_cookie_recognizes_set_attributes() -> None:
    cookie = _make_cookie(secure=True, rest={"HttpOnly": None, "SameSite": "Strict"})
    info = _describe_cookie(cookie)

    assert info["secure"] is True
    assert info["http_only"] is True
    assert info["same_site"] == "Strict"


def test_security_headers_cover_common_hardening_headers() -> None:
    assert "strict-transport-security" in SECURITY_HEADERS
    assert "content-security-policy" in SECURITY_HEADERS


@pytest.mark.asyncio
async def test_run_inspect_builds_a_valid_finding_for_a_redirect_chain(monkeypatch) -> None:
    async def fake_inspect(url, timeout, follow_redirects, max_redirects):
        return {
            "status_code": 200,
            "final_url": "https://www.example.com/",
            "redirect_chain": [{"url": "https://example.com/", "status_code": 301}],
            "content_encoding": None,
            "cookies": [],
            "missing_security_headers": [],
        }

    monkeypatch.setattr(http_plugin, "inspect", fake_inspect)

    result = await http_plugin.run_inspect("https://example.com", HttpConfig())

    redirect_finding = next(f for f in result.findings if f.title == "Redirect chain")
    assert redirect_finding.evidence == {
        "hops": [{"url": "https://example.com/", "status_code": 301}]
    }
