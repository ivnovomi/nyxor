from __future__ import annotations


def test_scan_endpoint_rate_limits_after_twenty_requests_per_minute(nyxor_test_client) -> None:
    statuses = [nyxor_test_client.get("/dns/example.com").status_code for _ in range(25)]
    assert statuses[:20] == [200] * 20
    assert all(status == 429 for status in statuses[20:])


def test_health_endpoint_is_not_scan_rate_limited(nyxor_test_client) -> None:
    # /health has no @limiter.limit override, so only the generous default
    # (60/min) applies — 25 requests should sail through.
    statuses = [nyxor_test_client.get("/health").status_code for _ in range(25)]
    assert all(status == 200 for status in statuses)
