from __future__ import annotations

from nyxor.plugins.http_.fingerprint import fingerprint


def test_detects_cloudflare_from_headers() -> None:
    result = fingerprint({"CF-RAY": "abc123-DFW"}, [], "")
    assert "Cloudflare" in result["cdn_waf"]


def test_detects_cloudflare_from_server_header() -> None:
    result = fingerprint({"Server": "cloudflare"}, [], "")
    assert "Cloudflare" in result["cdn_waf"]


def test_detects_php_from_x_powered_by() -> None:
    result = fingerprint({"X-Powered-By": "PHP/8.2.1"}, [], "")
    assert "PHP" in result["technologies"]


def test_detects_nginx_from_server_header() -> None:
    result = fingerprint({"Server": "nginx/1.25.0"}, [], "")
    assert "nginx" in result["technologies"]


def test_detects_wordpress_from_cookie_name() -> None:
    cookies = [{"name": "wordpress_logged_in_abc123"}]
    result = fingerprint({}, cookies, "")
    assert "WordPress" in result["technologies"]


def test_unrelated_cookie_name_does_not_false_positive_as_wordpress() -> None:
    cookies = [{"name": "not_a_real_wordpress_cookie"}]
    result = fingerprint({}, cookies, "")
    assert "WordPress" not in result["technologies"]


def test_detects_wordpress_from_body_markers() -> None:
    body = '<html><head><link rel="stylesheet" href="/wp-content/themes/x/style.css"></head></html>'
    result = fingerprint({}, [], body)
    assert "WordPress" in result["technologies"]


def test_detects_generator_meta_tag() -> None:
    body = '<html><head><meta name="generator" content="Hugo 0.120.0"></head></html>'
    result = fingerprint({}, [], body)
    assert "Hugo 0.120.0" in result["technologies"]


def test_no_signatures_means_empty_results() -> None:
    result = fingerprint({"Content-Type": "text/html"}, [], "<html></html>")
    assert result == {"technologies": [], "cdn_waf": []}


def test_multiple_signatures_all_detected() -> None:
    headers = {"Server": "cloudflare", "X-Powered-By": "Express"}
    result = fingerprint(headers, [], "")
    assert set(result["cdn_waf"]) == {"Cloudflare"}
    assert set(result["technologies"]) == {"Express.js"}
