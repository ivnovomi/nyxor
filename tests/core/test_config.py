from __future__ import annotations

from pathlib import Path

import pytest

from nyxor.core.config import ConfigError, load_config


def test_default_config_loads() -> None:
    config = load_config()
    assert config.general.log_level == "INFO"
    assert config.network.max_concurrency == 100


def test_project_config_overrides_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "nyxor.toml").write_text('[general]\nlog_level = "DEBUG"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)

    config = load_config()
    assert config.general.log_level == "DEBUG"


def test_unknown_profile_raises() -> None:
    with pytest.raises(ConfigError):
        load_config(profile="does-not-exist")


def test_profile_overrides_apply(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "nyxor.toml").write_text(
        "[profiles.fast]\n[profiles.fast.network]\ntimeout_seconds = 0.5\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    config = load_config(profile="fast")
    assert config.network.timeout_seconds == 0.5
    assert config.active_profile == "fast"


def test_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NYXOR_GENERAL__LOG_LEVEL", "WARNING")
    config = load_config()
    assert config.general.log_level == "WARNING"


def test_cli_overrides_win(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NYXOR_GENERAL__LOG_LEVEL", "WARNING")
    config = load_config(cli_overrides={"general": {"log_level": "ERROR"}})
    assert config.general.log_level == "ERROR"
