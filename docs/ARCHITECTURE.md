# Zen Portal Architecture

## Overview

Zen Portal is a contemplative TUI built with [Textual](https://textual.textualize.io/). It provides a minimal interface for managing AI assistant sessions (Claude, Codex, Gemini, OpenRouter) running in parallel via tmux.

## Core Architecture

### Services Container (`app.py`)

Dependency injection via a dataclass container:

```python
@dataclass
class Services:
    tmux: TmuxService           # Low-level tmux operations
    config: ConfigManager       # 3-tier config resolution
    sessions: SessionManager    # Session lifecycle
    state: SessionStateService  # Thread-safe persistence
    worktree: WorktreeService   # Git worktree management
    event_bus: EventBus         # Pub/sub for decoupling
```

### Reactive State Management

**The critical architectural decision**: No blocking calls on the UI thread.

```python
# OLD (blocking polling - caused freezes)
self.set_interval(1.0, self._poll_sessions)  # Blocked UI

# NEW (async reactive)
self._watcher = SessionStateWatcher(AsyncTmuxService(tmux), manager)
await self._watcher.start()  # Non-blocking via asyncio.to_thread()
```

See `docs/REACTIVE.md` for the full reactive architecture documentation.

### Event-Driven Updates

The EventBus enables decoupled communication:

```python
bus = EventBus.get()  # Singleton
bus.emit(SessionCreatedEvent(session_id="x", session_name="y"))
bus.subscribe(SessionCreatedEvent, self._on_session_created)
```

Events flow unidirectionally: Services → EventBus → UI

### tmux Integration

Sessions run in tmux for:
- True background execution (survives TUI restarts)
- Easy output capture via `capture-pane`
- Session persistence across restarts
- Multiple parallel sessions

```python
# Create session
tmux new-session -d -s zen-{id} -c {cwd} claude "{prompt}"

# Check state (now async via asyncio.to_thread)
await async_tmux.session_exists(name)
await async_tmux.is_pane_dead(name)

# Capture output
tmux capture-pane -t zen-{id} -p -S -100
```

## Module Structure

```
zen_portal/
├── app.py                    # Entry + Services container (DI)
├── models/                   # Data models
│   ├── session.py            # Session, SessionState, SessionType
│   └── template.py           # SessionTemplate
├── services/                 # Business logic (no UI)
│   ├── session_manager.py    # Lifecycle management
│   ├── events.py             # EventBus pub/sub
│   ├── tmux.py               # Low-level tmux (sync)
│   ├── tmux_async.py         # Async tmux wrapper
│   ├── reactive/             # Reactive architecture
│   │   ├── signal.py         # Signal[T], Computed[T], Effect
│   │   └── session_watcher.py # Async state monitoring
│   ├── core/                 # Extracted services
│   ├── pipelines/            # Multi-step operations
│   └── ...
├── screens/                  # Textual UI screens
├── widgets/                  # Reusable widgets
└── tests/                    # 361 unit tests
```

## Design Principles

### 1. Never Block the UI Thread

All blocking operations (subprocess, file I/O) use `asyncio.to_thread()`:

```python
async def session_exists(self, name: str) -> bool:
    return await asyncio.to_thread(self._tmux.session_exists, name)
```

### 2. Event-Driven Over Polling

Push updates when state changes, don't constantly poll:

```python
# After user action
await self._watcher.refresh_now()  # Event-triggered

# Background heartbeat is infrequent (10s) not aggressive (1s)
```

### 3. Progressive Disclosure

Keep files under 500 lines. Large modules split into `core/` subdirectories. Essential code first, details extracted.

### 4. Graceful Degradation

Operations return tuples for error handling without exceptions:

```python
def expand_file_reference(text: str) -> tuple[str, str | None]:
    """Return (result, error). Caller decides how to handle."""
```

## Configuration

3-tier resolution with overrides:

```
session > portal > config > defaults
```

Files:
- `~/.config/zen-portal/config.json` - User defaults
- `~/.config/zen-portal/portal.json` - Project state
- `~/.zen_portal/state.json` - Session persistence

## Further Reading

- `docs/REACTIVE.md` - Reactive architecture deep dive
- `docs/TEXTUAL_PATTERNS.md` - Textual framework patterns
- `HYDRATE.md` - Living documentation (AGENTESE format)
