"""EventBus: Decoupled service-to-UI communication.

Replaces scattered callbacks with centralized pub/sub pattern.
Services emit domain events, UI subscribes to what it needs.

Usage:
    # In services (emit events)
    bus = EventBus.get()
    bus.emit(SessionCreatedEvent(session))

    # In screens (subscribe to events)
    bus = EventBus.get()
    bus.subscribe(SessionCreatedEvent, self._on_session_created)

    # Cleanup on unmount
    bus.unsubscribe(SessionCreatedEvent, self._on_session_created)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Generic, TypeVar
import logging
import weakref

logger = logging.getLogger(__name__)

# Event type variable for generic typing
E = TypeVar("E", bound="Event")


@dataclass
class Event:
    """Base class for all domain events."""

    timestamp: datetime = field(default_factory=datetime.now)


# Session Events


@dataclass
class SessionCreatedEvent(Event):
    """Emitted when a session is created."""

    session_id: str = ""
    session_name: str = ""
    session_type: str = ""  # "ai" or "shell"


@dataclass
class SessionStateChangedEvent(Event):
    """Emitted when session state changes (running/paused/killed)."""

    session_id: str = ""
    old_state: str = ""
    new_state: str = ""


@dataclass
class SessionPausedEvent(Event):
    """Emitted when a session is paused (tmux ended, worktree preserved)."""

    session_id: str = ""


@dataclass
class SessionKilledEvent(Event):
    """Emitted when a session is killed (tmux ended, worktree removed)."""

    session_id: str = ""


@dataclass
class SessionCleanedEvent(Event):
    """Emitted when a paused session's worktree is cleaned."""

    session_id: str = ""


@dataclass
class SessionOutputEvent(Event):
    """Emitted when new session output is available."""

    session_id: str = ""
    output: str = ""


@dataclass
class SessionTokenUpdateEvent(Event):
    """Emitted when token counts are updated for a session."""

    session_id: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read: int = 0
    cache_write: int = 0


# Proxy Events


class ProxyHealthStatus(Enum):
    """Proxy health levels."""

    EXCELLENT = "excellent"
    GOOD = "good"
    DEGRADED = "degraded"
    WARNING = "warning"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class ProxyStatusChangedEvent(Event):
    """Emitted when proxy status changes."""

    old_status: ProxyHealthStatus = ProxyHealthStatus.UNKNOWN
    new_status: ProxyHealthStatus = ProxyHealthStatus.UNKNOWN
    message: str = ""


# Config Events


@dataclass
class ConfigChangedEvent(Event):
    """Emitted when configuration is updated."""

    key: str = ""  # Which config section changed


# Type alias for event handlers
EventHandler = Callable[[Event], None]


class EventBus:
    """Central event bus for service-to-UI communication.

    Singleton pattern ensures one bus per application.
    Uses weak references for automatic cleanup when subscribers are garbage collected.
    """

    _instance: "EventBus | None" = None

    def __init__(self) -> None:
        self._subscribers: dict[type[Event], list[EventHandler]] = {}
        self._weak_subscribers: dict[type[Event], list[weakref.ref]] = {}

    @classmethod
    def get(cls) -> "EventBus":
        """Get the singleton event bus instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        cls._instance = None

    def subscribe(
        self,
        event_type: type[E],
        handler: Callable[[E], None],
        weak: bool = False,
    ) -> None:
        """Subscribe to an event type.

        Args:
            event_type: The event class to subscribe to
            handler: Callback function to invoke when event is emitted
            weak: Use weak reference (auto-cleanup when handler owner is GC'd)
        """
        if weak:
            if event_type not in self._weak_subscribers:
                self._weak_subscribers[event_type] = []
            self._weak_subscribers[event_type].append(weakref.ref(handler))
        else:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            if handler not in self._subscribers[event_type]:
                self._subscribers[event_type].append(handler)

    def unsubscribe(
        self,
        event_type: type[E],
        handler: Callable[[E], None],
    ) -> None:
        """Unsubscribe from an event type."""
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(handler)
            except ValueError:
                pass  # Handler not in list

    def emit(self, event: Event) -> None:
        """Emit an event to all subscribers.

        Logs errors but doesn't let one subscriber's failure affect others.
        """
        event_type = type(event)

        # Call strong reference handlers
        handlers = self._subscribers.get(event_type, [])
        for handler in handlers:
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler error for {event_type.__name__}: {e}")

        # Call weak reference handlers (cleanup dead refs)
        weak_handlers = self._weak_subscribers.get(event_type, [])
        live_refs = []
        for ref in weak_handlers:
            handler = ref()
            if handler is not None:
                live_refs.append(ref)
                try:
                    handler(event)
                except Exception as e:
                    logger.error(f"Event handler error for {event_type.__name__}: {e}")
        self._weak_subscribers[event_type] = live_refs

    def subscriber_count(self, event_type: type[Event]) -> int:
        """Get number of subscribers for an event type (for debugging)."""
        strong = len(self._subscribers.get(event_type, []))
        weak = len([r for r in self._weak_subscribers.get(event_type, []) if r() is not None])
        return strong + weak

    def clear(self) -> None:
        """Clear all subscribers (for testing)."""
        self._subscribers.clear()
        self._weak_subscribers.clear()
