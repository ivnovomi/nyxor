from __future__ import annotations

from pathlib import Path

from nyxor.plugins.auth.store import AuthStore, looks_like_a_token, mask_token


def test_looks_like_a_token_requires_length_and_no_spaces() -> None:
    assert looks_like_a_token("a" * 16) is True
    assert looks_like_a_token("short") is False
    assert looks_like_a_token("has a space" * 2) is False


def test_mask_token_keeps_only_the_ends_visible() -> None:
    masked = mask_token("sk_live_1234567890abcdef")
    assert masked.startswith("sk_l")
    assert masked.endswith("cdef")
    assert "1234567890" not in masked


def test_mask_token_fully_masks_very_short_tokens() -> None:
    assert mask_token("short") == "*****"


def test_save_then_load_round_trips(tmp_path: Path) -> None:
    store = AuthStore(path=tmp_path / "auth.json")
    store.save("a" * 20, email="dev@example.com")

    record = store.load()
    assert record is not None
    assert record["token"] == "a" * 20
    assert record["email"] == "dev@example.com"
    assert "saved_at" in record


def test_load_with_no_saved_token_returns_none(tmp_path: Path) -> None:
    store = AuthStore(path=tmp_path / "does-not-exist.json")
    assert store.load() is None


def test_clear_removes_the_file_and_reports_whether_it_existed(tmp_path: Path) -> None:
    store = AuthStore(path=tmp_path / "auth.json")
    assert store.clear() is False

    store.save("a" * 20)
    assert store.clear() is True
    assert store.load() is None
