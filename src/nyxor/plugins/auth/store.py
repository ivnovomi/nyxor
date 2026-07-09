"""Local storage for a NYXOR Cloud API token.

There is no live Cloud backend yet (see the website's pricing section — the
waitlist buttons are honest about that), so ``login`` cannot validate a
token against a server. It only checks the token looks plausible and saves
it locally, exactly like a real CLI would once Cloud ships. The file
permissions are tightened to owner-only where the platform supports it,
since this is effectively a credential file.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any

from platformdirs import user_data_dir

APP_NAME = "nyxor"

MIN_TOKEN_LENGTH = 16


def default_auth_path() -> Path:
    return Path(user_data_dir(APP_NAME)) / "auth.json"


def looks_like_a_token(token: str) -> bool:
    token = token.strip()
    return len(token) >= MIN_TOKEN_LENGTH and token.isascii() and " " not in token


def mask_token(token: str) -> str:
    if len(token) <= 8:
        return "*" * len(token)
    return f"{token[:4]}{'*' * (len(token) - 8)}{token[-4:]}"


class AuthStore:
    """A single saved credential: a Cloud API token plus an optional label."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_auth_path()

    def _load(self) -> dict[str, Any] | None:
        if not self.path.is_file():
            return None
        data: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
        return data

    def save(self, token: str, email: str | None = None) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from datetime import UTC, datetime

        payload = {
            "token": token,
            "email": email,
            "saved_at": datetime.now(UTC).isoformat(),
        }
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        if os.name != "nt":
            self.path.chmod(stat.S_IRUSR | stat.S_IWUSR)

    def load(self) -> dict[str, Any] | None:
        return self._load()

    def clear(self) -> bool:
        if not self.path.is_file():
            return False
        self.path.unlink()
        return True
