from __future__ import annotations

import time

import pytest

from nyxor.api.oauth import DeviceAuthStore, OAuthError


def test_create_issues_distinct_device_and_user_codes() -> None:
    store = DeviceAuthStore()
    a = store.create()
    b = store.create()
    assert a.device_code != b.device_code
    assert a.user_code != b.user_code
    assert a.status == "pending"


def test_poll_before_approval_raises_authorization_pending() -> None:
    store = DeviceAuthStore()
    auth = store.create()
    with pytest.raises(OAuthError) as exc_info:
        store.poll(auth.device_code)
    assert exc_info.value.code == "authorization_pending"


def test_approve_then_poll_returns_a_token() -> None:
    store = DeviceAuthStore()
    auth = store.create()
    store.approve(auth.user_code)

    # poll() rate-limits itself; step past the interval by backdating.
    store._by_device_code[auth.device_code].last_poll_at = 0.0
    token = store.poll(auth.device_code)

    assert isinstance(token, str) and token
    assert store.is_valid_token(token)


def test_approve_unknown_user_code_raises_invalid_grant() -> None:
    store = DeviceAuthStore()
    with pytest.raises(OAuthError) as exc_info:
        store.approve("NOPE-NOPE")
    assert exc_info.value.code == "invalid_grant"


def test_approve_is_case_insensitive_and_trims_whitespace() -> None:
    store = DeviceAuthStore()
    auth = store.create()
    store.approve(f"  {auth.user_code.lower()}  ")
    store._by_device_code[auth.device_code].last_poll_at = 0.0
    token = store.poll(auth.device_code)
    assert store.is_valid_token(token)


def test_poll_unknown_device_code_raises_invalid_grant() -> None:
    store = DeviceAuthStore()
    with pytest.raises(OAuthError) as exc_info:
        store.poll("does-not-exist")
    assert exc_info.value.code == "invalid_grant"


def test_poll_expired_device_raises_expired_token() -> None:
    store = DeviceAuthStore()
    auth = store.create()
    store._by_device_code[auth.device_code].created_at = time.monotonic() - 10_000
    with pytest.raises(OAuthError) as exc_info:
        store.poll(auth.device_code)
    assert exc_info.value.code == "expired_token"


def test_poll_too_soon_after_a_previous_poll_raises_slow_down() -> None:
    store = DeviceAuthStore()
    auth = store.create()
    store._by_device_code[auth.device_code].last_poll_at = time.monotonic()
    with pytest.raises(OAuthError) as exc_info:
        store.poll(auth.device_code)
    assert exc_info.value.code == "slow_down"


def test_is_valid_token_rejects_unknown_tokens() -> None:
    store = DeviceAuthStore()
    assert store.is_valid_token("garbage") is False


def test_tokens_expire_after_their_ttl() -> None:
    from nyxor.api import oauth as oauth_module

    store = DeviceAuthStore()
    auth = store.create()
    store.approve(auth.user_code)
    store._by_device_code[auth.device_code].last_poll_at = 0.0
    token = store.poll(auth.device_code)
    assert store.is_valid_token(token)

    token_hash = oauth_module._hash_token(token)
    store._valid_tokens[token_hash] = time.monotonic() - oauth_module.TOKEN_TTL_SECONDS - 1

    assert store.is_valid_token(token) is False
