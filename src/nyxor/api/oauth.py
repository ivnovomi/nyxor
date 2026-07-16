"""OAuth 2.0 Device Authorization Grant (RFC 8628) for the CLI.

Real, working OAuth2 — not a placeholder pointing at a Cloud that doesn't
exist yet. `nyx auth login` runs this flow against any `nyx serve` instance
(defaulting to your own, on localhost): it gets a short user code, you
approve it (via a browser page or `nyx auth approve`), and the CLI polls
until it receives a bearer token. When NYXOR Cloud ships, the same flow
works against Cloud's API — only `--host` changes.

State is in-memory and per-process, matching every other piece of local
state NYXOR keeps (inventory, trends, auth token) — restarting `nyx serve`
clears pending/approved devices, which is expected for a self-hosted
single-operator instance.
"""

from __future__ import annotations

import hashlib
import secrets
import string
import time
from dataclasses import dataclass, field

DEVICE_CODE_TTL_SECONDS = 600
TOKEN_TTL_SECONDS = 30 * 24 * 3600  # bearer tokens are good for 30 days, then must be re-issued
POLL_INTERVAL_SECONDS = 3
_USER_CODE_ALPHABET = "".join(sorted(set(string.ascii_uppercase) - set("ILOU")))  # unambiguous


def _new_user_code() -> str:
    chars = [secrets.choice(_USER_CODE_ALPHABET) for _ in range(8)]
    return f"{''.join(chars[:4])}-{''.join(chars[4:])}"


def _hash_token(token: str) -> str:
    """SHA-256 of a bearer token, used as the storage/lookup key.

    Storing (and comparing) the hash instead of the raw token keeps
    ``is_valid_token`` an O(1) dict lookup — comparing the presented token
    against every stored one with ``hmac.compare_digest`` in a loop is O(N)
    in the number of live tokens, letting an attacker force an ever-growing
    linear scan on every request as tokens accumulate over their 30-day TTL.
    A hash-table lookup on a fixed-length digest doesn't have that
    scaling problem, and the token itself (32 random bytes) is far too
    high-entropy for a timing side channel on the hash comparison to be a
    practical concern.
    """
    return hashlib.sha256(token.encode()).hexdigest()


@dataclass
class DeviceAuth:
    device_code: str
    user_code: str
    created_at: float = field(default_factory=time.monotonic)
    status: str = "pending"  # pending | approved | denied
    access_token: str | None = None
    last_poll_at: float = 0.0

    @property
    def expired(self) -> bool:
        return time.monotonic() - self.created_at > DEVICE_CODE_TTL_SECONDS


class OAuthError(Exception):
    """Carries an RFC 8628 `error` code (e.g. authorization_pending, expired_token)."""

    def __init__(self, code: str, description: str) -> None:
        super().__init__(description)
        self.code = code
        self.description = description


class DeviceAuthStore:
    """In-memory device-code + issued-token registry for one running API process."""

    def __init__(self) -> None:
        self._by_device_code: dict[str, DeviceAuth] = {}
        self._by_user_code: dict[str, str] = {}
        self._valid_tokens: dict[str, float] = {}  # token -> issued_at (monotonic)

    def _sweep_expired(self) -> None:
        expired = [dc for dc, auth in self._by_device_code.items() if auth.expired]
        for dc in expired:
            auth = self._by_device_code.pop(dc)
            self._by_user_code.pop(auth.user_code, None)

        now = time.monotonic()
        expired_tokens = [
            token
            for token, issued_at in self._valid_tokens.items()
            if now - issued_at > TOKEN_TTL_SECONDS
        ]
        for token in expired_tokens:
            del self._valid_tokens[token]

    def create(self) -> DeviceAuth:
        self._sweep_expired()
        device_code = secrets.token_urlsafe(24)
        user_code = _new_user_code()
        auth = DeviceAuth(device_code=device_code, user_code=user_code)
        self._by_device_code[device_code] = auth
        self._by_user_code[user_code] = device_code
        return auth

    def approve(self, user_code: str) -> DeviceAuth:
        device_code = self._by_user_code.get(user_code.strip().upper())
        if device_code is None:
            raise OAuthError("invalid_grant", "unknown or expired code")
        auth = self._by_device_code[device_code]
        if auth.expired:
            raise OAuthError("expired_token", "this code has expired")
        auth.status = "approved"
        auth.access_token = secrets.token_urlsafe(32)
        self._valid_tokens[_hash_token(auth.access_token)] = time.monotonic()
        return auth

    def poll(self, device_code: str) -> str:
        """Return an access token if approved, else raise an RFC 8628 error."""
        auth = self._by_device_code.get(device_code)
        if auth is None:
            raise OAuthError("invalid_grant", "unknown device_code")
        if auth.expired:
            raise OAuthError("expired_token", "this device code has expired")

        now = time.monotonic()
        if now - auth.last_poll_at < POLL_INTERVAL_SECONDS - 0.5:
            raise OAuthError("slow_down", "polling too fast")
        auth.last_poll_at = now

        if auth.status == "denied":
            raise OAuthError("access_denied", "the request was denied")
        if auth.status != "approved" or auth.access_token is None:
            raise OAuthError("authorization_pending", "waiting for user approval")
        return auth.access_token

    def is_valid_token(self, token: str) -> bool:
        self._sweep_expired()
        return _hash_token(token) in self._valid_tokens


# One store per API process — created once in create_app() and closed over
# by the route handlers, exactly like the rest of the app's config.
