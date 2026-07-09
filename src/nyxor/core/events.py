"""A minimal synchronous event bus decoupling the Core from plugins.

Plugins publish lifecycle events (``module.started``, ``finding.reported``,
...) without knowing who, if anyone, is listening — the dashboard, a future
telemetry module, or nothing at all in a plain CLI run.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

EventHandler = Callable[..., None]


class EventBus:
    """In-process publish/subscribe bus. Not persisted, not distributed."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)

    def subscribe(self, event: str, handler: EventHandler) -> None:
        self._handlers[event].append(handler)

    def unsubscribe(self, event: str, handler: EventHandler) -> None:
        handlers = self._handlers.get(event)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def publish(self, event: str, **payload: Any) -> None:
        for handler in list(self._handlers.get(event, ())):
            handler(**payload)


# Well-known event names. Plugins are free to publish custom events too —
# this is a convenience list, not an enforced enum.
EVENT_SCAN_STARTED = "scan.started"
EVENT_SCAN_COMPLETED = "scan.completed"
EVENT_MODULE_STARTED = "module.started"
EVENT_MODULE_COMPLETED = "module.completed"
EVENT_FINDING_REPORTED = "finding.reported"
EVENT_PLUGIN_LOADED = "plugin.loaded"
EVENT_PLUGIN_LOAD_FAILED = "plugin.load_failed"
