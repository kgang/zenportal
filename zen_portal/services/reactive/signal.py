"""
Reactive primitives: Signal, Computed, Effect.

Ported from kgents reactive substrate for zen_portal.

Signal[T] is the observable state primitive - equivalent to:
- Textual: reactive() attribute
- React: useState()
- Solid: createSignal()

Computed[T] is derived state - equivalent to:
- Textual: @computed property
- React: useMemo()
- Solid: createMemo()

Effect is a side-effect container - equivalent to:
- Textual: watch() decorator
- React: useEffect()
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Generic, TypeVar

if TYPE_CHECKING:
    from typing import Any

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True)
class Snapshot(Generic[T]):
    """
    Immutable point-in-time capture of Signal state.

    Used for time-travel debugging and branching explorations.

    Attributes:
        value: The captured value at snapshot time
        timestamp: When the snapshot was taken (monotonic time)
        generation: How many times the Signal had been set when captured
    """

    value: T
    timestamp: float
    generation: int


@dataclass
class Signal(Generic[T]):
    """
    Observable state primitive with time-travel support.

    A Signal holds a value and notifies subscribers when it changes.

    Example:
        count = Signal.of(0)
        count.subscribe(lambda v: print(f"Count: {v}"))
        count.set(1)  # prints "Count: 1"
        count.update(lambda v: v + 1)  # prints "Count: 2"

        # Time travel
        snap = count.snapshot()
        count.set(100)
        count.restore(snap)
        assert count.value == 2
    """

    _value: T
    _subscribers: list[Callable[[T], None]] = field(default_factory=list)
    _generation: int = field(default=0)

    @classmethod
    def of(cls, value: T) -> Signal[T]:
        """Create a signal with initial value."""
        return cls(_value=value)

    @property
    def value(self) -> T:
        """Get current value (read-only)."""
        return self._value

    def set(self, new_value: T) -> None:
        """Set new value and notify subscribers if changed."""
        if new_value != self._value:
            self._value = new_value
            self._generation += 1
            for sub in self._subscribers:
                sub(new_value)

    def update(self, fn: Callable[[T], T]) -> None:
        """Update value via function."""
        self.set(fn(self._value))

    def subscribe(self, callback: Callable[[T], None]) -> Callable[[], None]:
        """
        Subscribe to changes. Returns unsubscribe function.

        Example:
            unsub = signal.subscribe(handle_change)
            unsub()  # Stop receiving updates
        """
        self._subscribers.append(callback)
        return lambda: self._subscribers.remove(callback)

    def map(self, fn: Callable[[T], U]) -> Computed[U]:
        """Create derived signal (functor map)."""
        return Computed.of(compute=lambda: fn(self._value), sources=[self])

    def snapshot(self) -> Snapshot[T]:
        """Capture current state as an immutable snapshot."""
        return Snapshot(
            value=self._value,
            timestamp=time.monotonic(),
            generation=self._generation,
        )

    def restore(self, snapshot: Snapshot[T]) -> None:
        """Restore signal to a previously captured snapshot."""
        self.set(snapshot.value)

    @property
    def generation(self) -> int:
        """Current generation (mutation count) of this signal."""
        return self._generation


@dataclass
class Computed(Generic[T]):
    """
    Derived state that auto-updates when dependencies change.

    Computed values are lazy: they only recompute when accessed
    after a dependency has changed.

    Example:
        first = Signal.of("Ada")
        last = Signal.of("Lovelace")
        full = Computed.of(
            compute=lambda: f"{first.value} {last.value}",
            sources=[first, last]
        )
        assert full.value == "Ada Lovelace"
        first.set("Grace")
        assert full.value == "Grace Lovelace"
    """

    _compute: Callable[[], T]
    _sources: list[Signal[Any]] = field(default_factory=list)
    _cached: T | None = field(default=None)
    _dirty: bool = field(default=True)
    _subscriptions: list[Callable[[], None]] = field(default_factory=list)

    def __post_init__(self) -> None:
        """Subscribe to all sources to invalidate on change."""
        for source in self._sources:
            unsub = source.subscribe(lambda _: self._invalidate())
            self._subscriptions.append(unsub)

    @classmethod
    def of(
        cls,
        compute: Callable[[], T],
        sources: list[Signal[Any]] | None = None,
    ) -> Computed[T]:
        """Create a computed value with its computation and dependencies."""
        return cls(_compute=compute, _sources=sources or [])

    @property
    def value(self) -> T:
        """Get current value, recomputing if dirty."""
        if self._dirty:
            self._cached = self._compute()
            self._dirty = False
        return self._cached  # type: ignore[return-value]

    def _invalidate(self) -> None:
        """Mark as dirty so next access recomputes."""
        self._dirty = True

    def dispose(self) -> None:
        """Unsubscribe from all sources."""
        for unsub in self._subscriptions:
            unsub()
        self._subscriptions.clear()

    def map(self, fn: Callable[[T], U]) -> Computed[U]:
        """Chain computed values (functor map)."""
        return Computed.of(compute=lambda: fn(self.value), sources=self._sources)


@dataclass
class Effect:
    """
    Side effect that runs when triggered.

    Effects are the bridge between pure reactive state and the impure
    outside world (logging, network calls, DOM updates, etc.).

    Unlike Computed which is lazy, Effects are eager and run immediately
    when triggered.

    Example:
        count = Signal.of(0)

        def log_count():
            print(f"Count is now: {count.value}")
            return None  # No cleanup needed

        effect = Effect.of(fn=log_count, sources=[count])
        effect.run()  # prints "Count is now: 0"
        count.set(5)  # Effect is invalidated, call run() to execute again
    """

    _fn: Callable[[], Callable[[], None] | None]
    _sources: list[Signal[Any]] = field(default_factory=list)
    _cleanup: Callable[[], None] | None = field(default=None)
    _subscriptions: list[Callable[[], None]] = field(default_factory=list)
    _dirty: bool = field(default=True)

    def __post_init__(self) -> None:
        """Subscribe to sources to mark dirty on change."""
        for source in self._sources:
            unsub = source.subscribe(lambda _: self._mark_dirty())
            self._subscriptions.append(unsub)

    @classmethod
    def of(
        cls,
        fn: Callable[[], Callable[[], None] | None],
        sources: list[Signal[Any]] | None = None,
    ) -> Effect:
        """Create an effect with its function and dependencies."""
        return cls(_fn=fn, _sources=sources or [])

    def _mark_dirty(self) -> None:
        """Mark effect as needing to run."""
        self._dirty = True

    @property
    def dirty(self) -> bool:
        """Check if effect needs to run."""
        return self._dirty

    def run(self) -> None:
        """
        Execute the effect.

        If a previous run returned a cleanup function, it's called first.
        If this run returns a cleanup function, it's stored for next time.
        """
        if self._cleanup:
            self._cleanup()
            self._cleanup = None
        result = self._fn()
        if callable(result):
            self._cleanup = result
        self._dirty = False

    def run_if_dirty(self) -> None:
        """Run the effect only if dependencies have changed."""
        if self._dirty:
            self.run()

    def dispose(self) -> None:
        """Clean up and unsubscribe from all sources."""
        if self._cleanup:
            self._cleanup()
            self._cleanup = None
        for unsub in self._subscriptions:
            unsub()
        self._subscriptions.clear()
