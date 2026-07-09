"""Plugin discovery and registration.

Plugins — built-in or third-party — are found exclusively through the
``nyxor.plugins`` entry-point group declared in a package's ``pyproject.toml``:

    [project.entry-points."nyxor.plugins"]
    myplugin = "my_package.plugin:PLUGIN"

There is no central registry file to edit. Installing a package that
declares this entry point is enough for ``nyx`` to pick it up.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import EntryPoint, entry_points

from nyxor.core.errors import PluginError
from nyxor.core.interfaces import Plugin
from nyxor.core.logging import get_logger

PLUGIN_GROUP = "nyxor.plugins"

logger = get_logger(__name__)


@dataclass
class DiscoveredPlugin:
    entry_point: EntryPoint
    plugin: Plugin


def _load_entry_point(entry_point: EntryPoint) -> Plugin:
    try:
        obj = entry_point.load()
    except Exception as exc:
        raise PluginError(
            f"Failed to load plugin {entry_point.name!r}: {exc}",
            hint="Run `nyx plugin list --verbose` to see the full traceback.",
        ) from exc

    if not isinstance(obj, Plugin):
        raise PluginError(
            f"Plugin {entry_point.name!r} does not satisfy the Plugin interface "
            f"(missing `metadata` or `register`)."
        )
    return obj


def discover_plugins(*, disabled: tuple[str, ...] | list[str] = ()) -> list[DiscoveredPlugin]:
    """Discover all installed plugins, skipping disabled ones.

    Failures loading an individual plugin are logged and skipped rather than
    aborting the whole CLI — one broken plugin should never take down NYXOR.
    """
    discovered: list[DiscoveredPlugin] = []
    disabled_set = set(disabled)

    for entry_point in entry_points(group=PLUGIN_GROUP):
        if entry_point.name in disabled_set:
            logger.debug("plugin.skipped_disabled", plugin=entry_point.name)
            continue
        try:
            plugin = _load_entry_point(entry_point)
        except PluginError as exc:
            logger.warning("plugin.load_failed", plugin=entry_point.name, error=str(exc))
            continue
        discovered.append(DiscoveredPlugin(entry_point=entry_point, plugin=plugin))
        logger.debug("plugin.loaded", plugin=entry_point.name, version=plugin.metadata.version)

    return discovered
