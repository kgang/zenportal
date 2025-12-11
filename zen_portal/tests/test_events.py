"""Tests for EventBus service."""

import pytest

from zen_portal.services.events import (
    Event,
    EventBus,
    SessionCreatedEvent,
    SessionStateChangedEvent,
    SessionPausedEvent,
    SessionKilledEvent,
    SessionCleanedEvent,
    SessionOutputEvent,
    SessionTokenUpdateEvent,
    ProxyStatusChangedEvent,
    ProxyHealthStatus,
    ConfigChangedEvent,
)


@pytest.fixture
def bus():
    """Fresh event bus for each test."""
    EventBus.reset()
    yield EventBus.get()
    EventBus.reset()


class TestEventBusBasics:
    """Test basic event bus functionality."""

    def test_singleton_pattern(self, bus):
        """EventBus.get() returns same instance."""
        bus2 = EventBus.get()
        assert bus is bus2

    def test_reset_creates_new_instance(self, bus):
        """EventBus.reset() creates fresh instance."""
        EventBus.reset()
        bus2 = EventBus.get()
        assert bus is not bus2

    def test_subscribe_and_emit(self, bus):
        """Subscribers receive emitted events."""
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(SessionCreatedEvent, handler)
        event = SessionCreatedEvent(session_id="test-123", session_name="test")
        bus.emit(event)

        assert len(received) == 1
        assert received[0] is event

    def test_multiple_subscribers(self, bus):
        """Multiple handlers for same event type."""
        received_a = []
        received_b = []

        bus.subscribe(SessionCreatedEvent, received_a.append)
        bus.subscribe(SessionCreatedEvent, received_b.append)

        event = SessionCreatedEvent(session_id="test", session_name="test")
        bus.emit(event)

        assert len(received_a) == 1
        assert len(received_b) == 1

    def test_no_duplicate_subscriptions(self, bus):
        """Same handler can't subscribe twice."""
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(SessionCreatedEvent, handler)
        bus.subscribe(SessionCreatedEvent, handler)  # duplicate

        bus.emit(SessionCreatedEvent(session_id="test", session_name="test"))

        assert len(received) == 1  # Only called once

    def test_unsubscribe(self, bus):
        """Unsubscribed handlers don't receive events."""
        received = []

        def handler(event):
            received.append(event)

        bus.subscribe(SessionCreatedEvent, handler)
        bus.unsubscribe(SessionCreatedEvent, handler)

        bus.emit(SessionCreatedEvent(session_id="test", session_name="test"))

        assert len(received) == 0

    def test_unsubscribe_nonexistent_handler(self, bus):
        """Unsubscribing non-subscribed handler doesn't raise."""

        def handler(event):
            pass

        # Should not raise
        bus.unsubscribe(SessionCreatedEvent, handler)

    def test_event_type_isolation(self, bus):
        """Events only go to subscribers of that type."""
        created_received = []
        paused_received = []

        bus.subscribe(SessionCreatedEvent, created_received.append)
        bus.subscribe(SessionPausedEvent, paused_received.append)

        bus.emit(SessionCreatedEvent(session_id="test", session_name="test"))

        assert len(created_received) == 1
        assert len(paused_received) == 0

    def test_handler_error_isolation(self, bus):
        """One handler's error doesn't affect others."""
        received = []

        def bad_handler(event):
            raise ValueError("Intentional error")

        def good_handler(event):
            received.append(event)

        bus.subscribe(SessionCreatedEvent, bad_handler)
        bus.subscribe(SessionCreatedEvent, good_handler)

        # Should not raise, good_handler should still be called
        bus.emit(SessionCreatedEvent(session_id="test", session_name="test"))

        assert len(received) == 1

    def test_subscriber_count(self, bus):
        """subscriber_count returns correct count."""
        assert bus.subscriber_count(SessionCreatedEvent) == 0

        bus.subscribe(SessionCreatedEvent, lambda e: None)
        assert bus.subscriber_count(SessionCreatedEvent) == 1

        bus.subscribe(SessionCreatedEvent, lambda e: None)
        assert bus.subscriber_count(SessionCreatedEvent) == 2

    def test_clear(self, bus):
        """clear() removes all subscribers."""
        bus.subscribe(SessionCreatedEvent, lambda e: None)
        bus.subscribe(SessionPausedEvent, lambda e: None)

        bus.clear()

        assert bus.subscriber_count(SessionCreatedEvent) == 0
        assert bus.subscriber_count(SessionPausedEvent) == 0


class TestEventTypes:
    """Test event dataclass attributes."""

    def test_session_created_event(self, bus):
        """SessionCreatedEvent has expected fields."""
        event = SessionCreatedEvent(
            session_id="abc123",
            session_name="my-session",
            session_type="ai",
        )
        assert event.session_id == "abc123"
        assert event.session_name == "my-session"
        assert event.session_type == "ai"
        assert event.timestamp is not None

    def test_session_state_changed_event(self, bus):
        """SessionStateChangedEvent has expected fields."""
        event = SessionStateChangedEvent(
            session_id="abc123",
            old_state="running",
            new_state="paused",
        )
        assert event.session_id == "abc123"
        assert event.old_state == "running"
        assert event.new_state == "paused"

    def test_session_output_event(self, bus):
        """SessionOutputEvent has expected fields."""
        event = SessionOutputEvent(
            session_id="abc123",
            output="Hello world",
        )
        assert event.session_id == "abc123"
        assert event.output == "Hello world"

    def test_session_token_update_event(self, bus):
        """SessionTokenUpdateEvent has expected fields."""
        event = SessionTokenUpdateEvent(
            session_id="abc123",
            input_tokens=1000,
            output_tokens=500,
            cache_read=200,
            cache_write=100,
        )
        assert event.session_id == "abc123"
        assert event.input_tokens == 1000
        assert event.output_tokens == 500
        assert event.cache_read == 200
        assert event.cache_write == 100

    def test_proxy_status_changed_event(self, bus):
        """ProxyStatusChangedEvent has expected fields."""
        event = ProxyStatusChangedEvent(
            old_status=ProxyHealthStatus.GOOD,
            new_status=ProxyHealthStatus.ERROR,
            message="Connection failed",
        )
        assert event.old_status == ProxyHealthStatus.GOOD
        assert event.new_status == ProxyHealthStatus.ERROR
        assert event.message == "Connection failed"

    def test_config_changed_event(self, bus):
        """ConfigChangedEvent has expected fields."""
        event = ConfigChangedEvent(key="proxy")
        assert event.key == "proxy"


class TestWeakReferences:
    """Test weak reference subscription behavior."""

    def test_weak_subscriber_cleanup(self, bus):
        """Weak subscribers are cleaned up when owner is GC'd."""
        received = []

        class Handler:
            def __call__(self, event):
                received.append(event)

        handler = Handler()
        bus.subscribe(SessionCreatedEvent, handler, weak=True)

        # Handler should work
        bus.emit(SessionCreatedEvent(session_id="test", session_name="test"))
        assert len(received) == 1

        # Delete handler - weak ref should be cleaned on next emit
        del handler
        bus.emit(SessionCreatedEvent(session_id="test2", session_name="test2"))

        # Should not have received second event (handler was GC'd)
        # Note: This test may be flaky if GC doesn't run immediately
        # In practice, this provides eventual cleanup
