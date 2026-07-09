from __future__ import annotations

from nyxor.core.events import EventBus


def test_publish_calls_subscribed_handlers() -> None:
    bus = EventBus()
    received: list[dict] = []
    bus.subscribe("scan.started", lambda **payload: received.append(payload))

    bus.publish("scan.started", target="example.com")

    assert received == [{"target": "example.com"}]


def test_publish_with_no_subscribers_is_a_noop() -> None:
    bus = EventBus()
    bus.publish("nothing.listening")  # should not raise


def test_unsubscribe_stops_delivery() -> None:
    bus = EventBus()
    received: list[str] = []

    def handler(**_: object) -> None:
        received.append("called")

    bus.subscribe("event", handler)
    bus.unsubscribe("event", handler)
    bus.publish("event")

    assert received == []
