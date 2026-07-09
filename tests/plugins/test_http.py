from __future__ import annotations

from http.cookiejar import Cookie

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
