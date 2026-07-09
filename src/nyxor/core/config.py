"""Configuration loading with a well-defined override hierarchy.

Precedence, lowest to highest:

1. Packaged defaults (:data:`DEFAULT_CONFIG`)
2. User configuration (``platformdirs.user_config_dir("nyxor")/config.toml``)
3. Project configuration (``./nyxor.toml`` in the current working directory)
4. The selected profile's overrides (``[profiles.<name>]`` in either file)
5. Environment variables (``NYXOR_*``, ``__`` for nesting)
6. Explicit CLI overrides (``--output``, ``--verbose``, ...)

Each layer is a partial dict that is deep-merged onto the previous one, and
the merged result is validated once, at the end, as a :class:`NyxorConfig`.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from platformdirs import user_config_dir
from pydantic import BaseModel, Field

from nyxor.core.errors import ConfigError

APP_NAME = "nyxor"
PROJECT_CONFIG_FILENAMES = ("nyxor.toml", ".nyxor.toml")

DEFAULT_CONFIG: dict[str, Any] = {
    "general": {
        "log_level": "INFO",
        "log_format": "console",  # "console" | "json"
        "output_format": "json",  # "json" | "yaml" | "table"
        "output_dir": "./nyxor-output",
    },
    "network": {"timeout_seconds": 2.0, "max_concurrency": 100},
    "dns": {"resolvers": [], "timeout_seconds": 5.0},
    "tls": {"timeout_seconds": 5.0},
    "http": {"timeout_seconds": 10.0, "follow_redirects": True, "max_redirects": 10},
    "ai": {
        "ollama_host": "http://localhost:11434",
        "model": "llama3.2",
        "timeout_seconds": 30.0,
    },
    "plugins": {"disabled": []},
    "profiles": {},
}


class GeneralConfig(BaseModel):
    log_level: str = "INFO"
    log_format: str = "console"
    output_format: str = "json"
    output_dir: str = "./nyxor-output"


class NetworkConfig(BaseModel):
    timeout_seconds: float = 2.0
    max_concurrency: int = 100


class DnsConfig(BaseModel):
    resolvers: list[str] = Field(default_factory=list)
    timeout_seconds: float = 5.0


class TlsConfig(BaseModel):
    timeout_seconds: float = 5.0


class HttpConfig(BaseModel):
    timeout_seconds: float = 10.0
    follow_redirects: bool = True
    max_redirects: int = 10


class AiConfig(BaseModel):
    """Where to find a local LLM for `nyx analyze`.

    Points at Ollama's default local address by default — no API key, no
    network call to anyone but the model running on this machine. NYXOR
    Cloud offers the same command against a hosted model for machines that
    don't want to run one themselves.
    """

    ollama_host: str = "http://localhost:11434"
    model: str = "llama3.2"
    timeout_seconds: float = 30.0


class PluginsConfig(BaseModel):
    disabled: list[str] = Field(default_factory=list)


class NyxorConfig(BaseModel):
    """The fully merged, validated configuration for a single CLI run."""

    general: GeneralConfig = Field(default_factory=GeneralConfig)
    network: NetworkConfig = Field(default_factory=NetworkConfig)
    dns: DnsConfig = Field(default_factory=DnsConfig)
    tls: TlsConfig = Field(default_factory=TlsConfig)
    http: HttpConfig = Field(default_factory=HttpConfig)
    ai: AiConfig = Field(default_factory=AiConfig)
    plugins: PluginsConfig = Field(default_factory=PluginsConfig)
    profiles: dict[str, dict[str, Any]] = Field(default_factory=dict)
    active_profile: str | None = None


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(
            f"Invalid TOML in {path}: {exc}", hint="Check for syntax errors."
        ) from exc
    except OSError as exc:
        raise ConfigError(f"Could not read config file {path}: {exc}") from exc


def user_config_path() -> Path:
    return Path(user_config_dir(APP_NAME)) / "config.toml"


def find_project_config(start: Path | None = None) -> Path | None:
    """Look in the current working directory for a project config file."""
    directory = start or Path.cwd()
    for filename in PROJECT_CONFIG_FILENAMES:
        candidate = directory / filename
        if candidate.is_file():
            return candidate
    return None


def _env_overrides(prefix: str = "NYXOR_") -> dict[str, Any]:
    """Turn ``NYXOR_SECTION__KEY=value`` environment variables into a nested dict."""
    overrides: dict[str, Any] = {}
    for env_key, raw_value in os.environ.items():
        if not env_key.startswith(prefix):
            continue
        path = env_key[len(prefix) :].lower().split("__")
        node = overrides
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = raw_value
    return overrides


def load_config(
    *,
    profile: str | None = None,
    project_dir: Path | None = None,
    cli_overrides: dict[str, Any] | None = None,
) -> NyxorConfig:
    """Build the effective configuration for this invocation."""
    merged = dict(DEFAULT_CONFIG)

    user_path = user_config_path()
    if user_path.is_file():
        merged = _deep_merge(merged, _read_toml(user_path))

    project_path = find_project_config(project_dir)
    if project_path is not None:
        merged = _deep_merge(merged, _read_toml(project_path))

    if profile:
        profile_overrides = merged.get("profiles", {}).get(profile)
        if profile_overrides is None:
            raise ConfigError(
                f"Unknown profile: {profile!r}",
                hint="Define it under [profiles.<name>] in your config file.",
            )
        merged = _deep_merge(merged, profile_overrides)

    merged = _deep_merge(merged, _env_overrides())

    if cli_overrides:
        merged = _deep_merge(merged, cli_overrides)

    try:
        config = NyxorConfig.model_validate(merged)
    except Exception as exc:  # pydantic.ValidationError
        raise ConfigError(f"Invalid configuration: {exc}") from exc
    config.active_profile = profile
    return config
