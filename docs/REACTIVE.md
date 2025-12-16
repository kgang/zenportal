# Reactive Architecture in Zen Portal

> *"The UI thread is sacred. Never block it."*

This document captures the learnings from eliminating polling-induced UI freezes in zen_portal through reactive patterns ported from the kgents reactive substrate.

## The Problem: Blocking Polls

### Symptoms
- UI freezing for 1-5 seconds during session state checks
- Unresponsive keyboard input while tmux commands execute
- Jank during rapid session creation (333ms polling × 9 ticks)

### Root Cause Analysis

```
MainScreen.on_mount()
  → set_interval(1.0, _poll_sessions)      # Every 1 second
    → SessionManager.refresh_states()
      → StateRefresher.refresh()
        → [For each session]
          → tmux.session_exists()          # subprocess.run() BLOCKS
          → tmux.is_pane_dead()            # subprocess.run() BLOCKS
          → tmux.get_pane_exit_status()    # subprocess.run() BLOCKS
```

**The critical insight**: Each `subprocess.run()` call has a 5-second timeout. With N sessions, worst case is `3N × 5 seconds` of blocking time. Even under normal conditions, tmux calls take 50-200ms each, creating perceptible jank.

### Why Polling Was Wrong

| Aspect | Polling | Impact |
|--------|---------|--------|
| **Model** | Pull-based | UI must ask "what changed?" |
| **Thread** | Main event loop | Blocks all input/rendering |
| **Frequency** | 1s interval | 1000ms latency floor |
| **Burst** | 333ms × 9 | 3s of aggressive blocking |
| **Scaling** | O(N) per poll | More sessions = more blocking |

---

## The Solution: Reactive + Async

### Architecture Overview

```
MainScreen.on_mount()
  → SessionStateWatcher.start()
    → asyncio.create_task(_watch_loop)      # Background task
      → [Every 10s OR on-demand]
        → detect_session_state_async()
          → AsyncTmuxService.session_exists()  # asyncio.to_thread()
          → AsyncTmuxService.is_pane_dead()    # Non-blocking!
          → AsyncTmuxService.get_pane_exit_status()
        → on_state_change callback → UI update
```

### Key Components

#### 1. AsyncTmuxService (`services/tmux_async.py`)

Wraps blocking subprocess calls with `asyncio.to_thread()`:

```python
class AsyncTmuxService:
    """Async wrapper for TmuxService - non-blocking tmux operations."""

    def __init__(self, tmux: TmuxService) -> None:
        self._tmux = tmux

    async def session_exists(self, name: str) -> bool:
        """Check if a tmux session exists (non-blocking)."""
        return await asyncio.to_thread(self._tmux.session_exists, name)

    async def is_pane_dead(self, name: str) -> bool:
        """Check if a session's pane is dead (non-blocking)."""
        return await asyncio.to_thread(self._tmux.is_pane_dead, name)
```

**Why `asyncio.to_thread()`?**
- Runs blocking code in a thread pool executor
- Returns control to event loop immediately
- Other async tasks (UI rendering, input handling) continue unblocked
- Available in Python 3.9+, simple API

#### 2. SessionStateWatcher (`services/reactive/session_watcher.py`)

Replaces polling with event-driven async monitoring:

```python
class SessionStateWatcher:
    HEARTBEAT_INTERVAL = 10.0  # Much longer than 1s polling

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())

    async def refresh_now(self) -> list[Session]:
        """Trigger immediate async refresh (for user actions)."""
        return await self._refresh_all_async()

    async def _watch_loop(self) -> None:
        """Background heartbeat - 10s interval."""
        while self._running:
            await self._refresh_all_async()
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
```

**Design decisions**:
- **10s heartbeat**: Background safety net, not primary update mechanism
- **Event-triggered refresh**: `refresh_now()` called after user actions
- **Non-blocking loop**: Uses `await asyncio.sleep()` not `time.sleep()`

#### 3. Reactive Primitives (`services/reactive/signal.py`)

Ported from kgents for future reactive UI patterns:

```python
@dataclass
class Signal(Generic[T]):
    """Observable state primitive with subscribers."""

    _value: T
    _subscribers: list[Callable[[T], None]]

    def set(self, new_value: T) -> None:
        """Set new value and notify subscribers if changed."""
        if new_value != self._value:
            self._value = new_value
            for sub in self._subscribers:
                sub(new_value)

    def subscribe(self, callback: Callable[[T], None]) -> Callable[[], None]:
        """Subscribe to changes. Returns unsubscribe function."""
        self._subscribers.append(callback)
        return lambda: self._subscribers.remove(callback)


@dataclass
class Computed(Generic[T]):
    """Derived state that auto-updates when dependencies change."""

    _compute: Callable[[], T]
    _sources: list[Signal[Any]]
    _dirty: bool = True

    @property
    def value(self) -> T:
        """Get current value, recomputing if dirty."""
        if self._dirty:
            self._cached = self._compute()
            self._dirty = False
        return self._cached
```

**When to use**:
- `Signal[T]`: Observable state that triggers UI updates
- `Computed[T]`: Derived values that cache until dependencies change
- `Effect`: Side effects with cleanup (logging, network calls)

---

## Integration Patterns

### MainScreen Integration

```python
async def on_mount(self) -> None:
    # Start async state watcher (replaces polling)
    self._watcher = SessionStateWatcher(
        AsyncTmuxService(self._manager._tmux),
        self._manager,
        on_state_change=lambda _: self._on_watcher_state_change(),
    )
    await self._watcher.start()

async def on_unmount(self) -> None:
    # Clean up watcher
    if self._watcher:
        await self._watcher.stop()
```

### Event-Triggered Refreshes

Instead of constant polling, refresh on user actions:

```python
# After session creation:
self._start_rapid_refresh()  # Now async, non-blocking

async def _rapid_refresh_async(self) -> None:
    """Async rapid refresh - non-blocking."""
    for _ in range(6):  # 6 checks over 3 seconds
        changed = await self._watcher.refresh_now()
        if changed:
            self._refresh_sessions()
        await asyncio.sleep(0.5)
```

### Manual Refresh Action

```python
async def action_refresh_output(self) -> None:
    """Manual refresh - triggers async state check."""
    self._refresh_selected_output()
    if self._watcher:
        await self._watcher.refresh_now()
    self._refresh_sessions()
```

---

## Results

### Before vs After

| Metric | Before (Polling) | After (Reactive) |
|--------|------------------|------------------|
| Poll interval | 1 second | 10 seconds |
| Rapid refresh | 333ms × 9 (blocking) | 500ms × 6 (async) |
| tmux call model | `subprocess.run()` | `asyncio.to_thread()` |
| UI freeze risk | 5s timeout per call | Never blocks |
| CPU when idle | Constant polling | Zero overhead |
| Latency floor | 1000ms | Event-driven |

### Why It Works

1. **Thread pool isolation**: `asyncio.to_thread()` runs blocking code in executor threads, keeping the event loop free

2. **Reduced frequency**: 10s heartbeat vs 1s polling = 10× fewer background operations

3. **Event-driven**: User actions trigger immediate refresh, not polling interval

4. **Graceful degradation**: Even if tmux calls slow down, UI remains responsive

---

## Learnings

### The asyncio.to_thread() Pattern

This is the key insight for any Python async app with blocking dependencies:

```python
# WRONG: Blocks the event loop
def poll_something():
    result = subprocess.run(...)  # Blocks everything
    return result

# RIGHT: Non-blocking via thread pool
async def poll_something_async():
    result = await asyncio.to_thread(subprocess.run, ...)
    return result
```

**When to use**:
- File I/O operations
- Subprocess calls (like tmux)
- Network calls in sync libraries
- Any blocking operation in an async context

### Push vs Pull Architecture

```
PULL (Polling):
  UI → "Has anything changed?" → Backend → Response
  UI → "Has anything changed?" → Backend → Response
  UI → "Has anything changed?" → Backend → Response
  (Constant overhead, latency floor = poll interval)

PUSH (Reactive):
  Backend → "Something changed!" → UI
  (Zero overhead when idle, immediate on change)
```

### The Signal Pattern

Reactive signals provide a clean abstraction for observable state:

```python
# Create observable state
sessions = Signal.of([])

# Subscribe to changes
unsub = sessions.subscribe(lambda s: update_ui(s))

# Changes automatically propagate
sessions.set(new_sessions)  # UI updates automatically

# Cleanup
unsub()
```

This pattern:
- Decouples state management from UI
- Makes data flow explicit
- Enables time-travel debugging (via snapshots)
- Provides automatic cleanup

---

## Future Enhancements

### tmux Socket Watching (Optional)

For even more reactive behavior, consider watching the tmux socket:

```python
# Location: /private/tmp/tmux-{uid}/default
# Watch for modification time changes as event trigger
```

However, tmux sockets don't change frequently enough to be a reliable event source. The current 10s heartbeat + event-triggered refresh is sufficient.

### Full Reactive UI

The Signal/Computed primitives enable more sophisticated patterns:

```python
# Derived state example
selected_session = Signal.of(None)
output_content = Computed.of(
    compute=lambda: manager.get_output(selected_session.value.id),
    sources=[selected_session]
)

# UI automatically updates when selection changes
output_content.subscribe(lambda c: output_view.update(c))
```

---

## References

- **kgents reactive substrate**: `/Users/kentgang/git/kgents/impl/claude/agents/i/reactive/signal.py`
- **Python asyncio.to_thread**: https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread
- **Textual async patterns**: https://textual.textualize.io/guide/workers/
