from __future__ import annotations

from nyxor.core.plugins import discover_plugins


def test_builtin_plugins_are_discovered() -> None:
    discovered = discover_plugins()
    names = {d.plugin.metadata.name for d in discovered}

    assert {
        "system",
        "network",
        "dns",
        "tls",
        "http",
        "inventory",
        "report",
        "config",
        "plugin",
        "update",
    } <= names


def test_disabled_plugins_are_skipped() -> None:
    discovered = discover_plugins(disabled=["network"])
    names = {d.plugin.metadata.name for d in discovered}

    assert "network" not in names
    assert "system" in names


def test_every_plugin_exposes_valid_metadata() -> None:
    for discovered in discover_plugins():
        meta = discovered.plugin.metadata
        assert meta.name
        assert meta.version
        assert callable(discovered.plugin.register)
