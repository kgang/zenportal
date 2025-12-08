# Zen Code Design: Architecture Philosophy

> Applying zen principles to code: simplicity, clarity, minimalism, separation, testability

Last updated: 2025-12-07

---

## Core Philosophy

**Zen Code Principles:**
1. **簡素 Kanso (Simplicity)** - Remove complexity, not features
2. **明快 Meikai (Clarity)** - Code reveals intent immediately
3. **分離 Bunri (Separation)** - Each piece knows only what it must
4. **空 Kū (Emptiness)** - No unnecessary abstraction
5. **検証 Kenshō (Verification)** - Truth through testing

---

## Critical Issues

### 1. SessionManager: The God Object (832 lines)

**Violation**: Single Responsibility Principle - does lifecycle + persistence + state refresh + worktrees + tokens

**Current Structure:**
```python
class SessionManager:
    # Lines 1-200: Lifecycle (create, pause, kill, revive)
    # Lines 201-400: Advanced ops (resume, adopt, navigate)
    # Lines 401-450: Batch operations (kill_all, cleanup)
    # Lines 451-832: State persistence (save, load, history)

    # 10 dependencies in constructor
    def __init__(self, tmux, config, worktree, working_dir, on_event, base_dir):
        self._tmux = tmux
        self._config = config
        self._worktree = worktree
        self._worktree_mgr = WorktreeManager(...)  # Creates internal manager
        self._token_mgr = TokenManager()           # Creates internal manager
        self._state_refresher = StateRefresher(...) # Creates internal manager
```

**Problem**: Cannot test lifecycle without persistence. Cannot mock state refresh independently.

**Zen Refactoring:**

```python
# NEW: Pure session lifecycle orchestration
class SessionManager:
    """Orchestrates session lifecycle only."""

    def __init__(
        self,
        tmux: TmuxService,
        state: SessionStateService,      # Extracted
        worktree: WorktreeService,       # Single service
        tokens: TokenService,            # Extracted
        commands: CommandBuilder,
        event_bus: EventBus              # Replaces callback
    ):
        # 6 dependencies, all injected, all interfaces

    def create_session(self, config: SessionConfig) -> Session:
        """Create new session. State persistence is external."""
        session = self._build_session(config)
        self._tmux.create(session)
        self._event_bus.emit(SessionCreated(session))
        return session

    def pause_session(self, session_id: str) -> bool:
        """Pause session. Caller handles persistence."""
        # No _save_state() call here - that's state service's job

# NEW: State persistence extracted
class SessionStateService:
    """Handles session persistence only."""

    def __init__(self, state_file: Path):
        self._state_file = state_file
        self._lock = threading.Lock()

    def save(self, sessions: list[Session]) -> None:
        """Atomically save session state."""
        with self._lock:
            self._atomic_write(sessions)

    def load(self) -> list[Session]:
        """Load session state."""
        with self._lock:
            return self._atomic_read()

# NEW: Token tracking extracted
class TokenService:
    """Tracks token usage for AI sessions."""

    def update_from_file(self, session: Session) -> TokenUsage | None:
        """Parse token data from Claude's JSONL."""

    def get_history(self, session: Session) -> list[TokenUsage]:
        """Get historical token usage."""

# NEW: Event bus replaces callbacks
class EventBus:
    """Publish/subscribe for session events."""

    def emit(self, event: SessionEvent) -> None:
        """Emit event to all subscribers."""

    def subscribe(self, event_type: type, handler: Callable) -> None:
        """Subscribe to event type."""
```

**Benefits:**
- SessionManager: 832 → ~300 lines
- Each service testable in isolation
- Clear boundaries between concerns
- Lock contention only in state service
- Events replace tight coupling

**Files to create:**
- `services/session_state.py` (150 lines)
- `services/token_service.py` (100 lines)
- `services/event_bus.py` (80 lines)

---

### 2. DOM Query Anti-Pattern (152 occurrences)

**Violation**: Re-querying DOM on every access

**Current Pattern:**
```python
class NewSessionModal(ModalScreen):
    def _check_conflicts(self) -> None:
        name = self.query_one("#name-input", Input).value
        type_val = self.query_one("#type-select", Select).value
        # Query again in another method...

    def _handle_type_change(self, value) -> None:
        self.query_one("#provider-label", Static).display = is_ai
        self.query_one("#provider-select", Select).display = is_ai
        self.query_one("#prompt-label", Static).display = is_ai
        # 8 more queries...
```

**Problem**: O(n) search through widget tree on every access. Unclear what widgets exist.

**Zen Pattern: Cache Widget References**

```python
class NewSessionModal(ModalScreen):
    """Session creation modal with cached widget references."""

    def compose(self) -> ComposeResult:
        # Composition defines structure
        with Vertical(id="new-tab"):
            yield Static("name", id="name-label")
            yield Input(id="name-input")
            yield Static("type", id="type-label")
            yield Select(id="type-select")
            # ...

    def on_mount(self) -> None:
        """Cache all widget references once."""
        self._refs = WidgetRefs(
            name_input=self.query_one("#name-input", Input),
            type_select=self.query_one("#type-select", Select),
            provider_label=self.query_one("#provider-label", Static),
            provider_select=self.query_one("#provider-select", Select),
            # ... all widgets cached
        )

    def _check_conflicts(self) -> None:
        """Direct access to cached widgets."""
        name = self._refs.name_input.value
        type_val = self._refs.type_select.value
        # O(1) access

    def _handle_type_change(self, value) -> None:
        """Single coherent update."""
        refs = self._refs
        is_ai = value == NewSessionType.AI

        # Batch update visibility
        for widget in [refs.provider_label, refs.provider_select,
                       refs.prompt_label, refs.prompt_input]:
            widget.display = is_ai
```

**Zen Alternative: Typed Widget Container**

```python
from dataclasses import dataclass

@dataclass
class NewSessionWidgets:
    """Typed widget references for new session form."""
    name_input: Input
    type_select: Select
    provider_label: Static
    provider_select: Select
    model_input: Input
    directory_browser: DirectoryBrowser
    prompt_input: TextArea
    worktree_checkbox: Checkbox

    @classmethod
    def from_screen(cls, screen: ModalScreen) -> "NewSessionWidgets":
        """Query once, cache all."""
        return cls(
            name_input=screen.query_one("#name-input", Input),
            type_select=screen.query_one("#type-select", Select),
            # ... type-safe, autocomplete-friendly
        )

class NewSessionModal(ModalScreen):
    def on_mount(self) -> None:
        self.widgets = NewSessionWidgets.from_screen(self)

    def _check_conflicts(self) -> None:
        # IDE autocomplete works!
        name = self.widgets.name_input.value
```

**Benefits:**
- 152 DOM queries → ~15 (one-time cache)
- O(n) → O(1) access pattern
- Type safety and autocomplete
- Clear widget inventory
- Easier testing (mock WidgetRefs)

---

### 3. Dual Worktree Implementations

**Violation**: Two separate services do overlapping work

**Current:**
```
/services/worktree.py (287 lines)
├── WorktreeService
│   ├── create_worktree(repo, branch, path)
│   ├── remove_worktree(path)
│   ├── list_worktrees(repo)
│   └── Git operations focus

/services/core/worktree_manager.py (138 lines)
├── WorktreeManager
│   ├── setup_for_session(session, features, settings)
│   ├── cleanup_session_worktree(session)
│   ├── navigate_to_worktree(session)
│   └── Session integration focus
```

**Problem:** Unclear which to use. Both imported in different files. Duplication of logic.

**Zen Consolidation:**

```python
# KEEP: services/worktree.py (enhanced)
class WorktreeService:
    """Git worktree operations for session isolation."""

    def __init__(self, git: GitService):
        self._git = git

    # Low-level git operations
    def create(self, repo: Path, branch: str, path: Path) -> Worktree:
        """Create git worktree."""

    def remove(self, worktree: Worktree) -> bool:
        """Remove git worktree."""

    def list_all(self, repo: Path) -> list[Worktree]:
        """List all worktrees for repository."""

    # High-level session operations (merged from manager)
    def setup_for_session(
        self,
        session: Session,
        features: WorktreeFeatures,
        settings: WorktreeSettings
    ) -> Path:
        """Create worktree for session with env linking."""
        worktree = self.create(
            repo=session.working_dir,
            branch=features.branch or settings.default_branch,
            path=self._worktree_path(session)
        )

        if settings.symlink_env_files:
            self._link_env_files(worktree, session.working_dir)

        return worktree.path

    def cleanup_session(self, session: Session) -> bool:
        """Remove session's worktree."""
        path = self._worktree_path(session)
        return self.remove(Worktree(path=path, branch=""))

    def _worktree_path(self, session: Session) -> Path:
        """Compute worktree path for session."""
        return session.working_dir / ".worktrees" / session.id[:8]

    def _link_env_files(self, worktree: Worktree, repo: Path) -> None:
        """Symlink env files from repo to worktree."""
        for env_file in [".env", ".env.local"]:
            src = repo / env_file
            if src.exists():
                (worktree.path / env_file).symlink_to(src)

# DELETE: services/core/worktree_manager.py
```

**Benefits:**
- 425 lines → 300 lines (net reduction)
- Single import: `from services.worktree import WorktreeService`
- Clear API: low-level (create/remove) + high-level (setup_for_session)
- Easier testing: mock GitService only
- No confusion about which service to use

---

### 4. Leaky Abstractions: Private Details Exposed

**Violation**: Internal implementation leaked as public API

**Current:**
```python
# services/session_manager.py
class SessionManager:
    def __init__(self, ...):
        self._worktree_mgr = WorktreeManager(...)  # Private
        self._token_mgr = TokenManager()           # Private

        # BUT: exposed as public!
        self.worktree = self._worktree_mgr  # Why public?
        self.tokens = self._token_mgr       # Breaks encapsulation

# screens/main.py uses this leak:
def action_show_worktrees(self):
    worktrees = self._manager.worktree.list_worktrees()  # Direct access!
```

**Problem:** Screens bypass SessionManager API. Tight coupling to internal structure.

**Zen Encapsulation:**

```python
class SessionManager:
    """Session lifecycle orchestration."""

    def __init__(
        self,
        tmux: TmuxService,
        worktree: WorktreeService,  # Injected, not internal
        tokens: TokenService,        # Injected, not internal
    ):
        self._tmux = tmux
        self._worktree = worktree
        self._tokens = tokens
        # NO public exposure

    # Public API only
    def list_worktrees(self, repo: Path) -> list[Worktree]:
        """Delegate to worktree service."""
        return self._worktree.list_all(repo)

    def get_token_usage(self, session: Session) -> TokenUsage | None:
        """Delegate to token service."""
        return self._tokens.update_from_file(session)

# Screens use SessionManager API only
def action_show_worktrees(self):
    worktrees = self._manager.list_worktrees(repo=current_dir)
```

**Benefits:**
- Clear interface: only public methods callable
- SessionManager can change internals without breaking screens
- Easier to test (mock fewer dependencies)
- Enforces single point of access

---

### 5. Error Handling: Silent Failures

**Violation**: Exceptions caught with `pass`, no logging

**Current Pattern:**
```python
# services/session_manager.py:619
try:
    with open(history_file, "a") as f:
        f.write(json.dumps(record) + "\n")
except OSError:
    pass  # History is optional, don't fail on errors

# services/config.py:47
try:
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
except OSError:
    pass  # Best effort on systems that don't support chmod

# 6 more instances...
```

**Problem:** No way to debug failures. User doesn't know something failed. Development is harder.

**Zen Error Handling:**

```python
import logging

logger = logging.getLogger(__name__)

# 1. Log before swallowing
try:
    with open(history_file, "a") as f:
        f.write(json.dumps(record) + "\n")
except OSError as e:
    logger.warning(f"Failed to append session history: {e}")
    # Continue - history is optional

# 2. Define expected vs unexpected
try:
    path.chmod(stat.S_IRUSR | stat.S_IWUSR)
except OSError as e:
    if e.errno == errno.ENOTSUP:
        logger.debug("chmod not supported on this filesystem")
    else:
        logger.error(f"Unexpected chmod error: {e}")
        raise  # Re-raise unexpected errors

# 3. Create proper exception hierarchy
class ZenError(Exception):
    """Base exception for Zenportal."""

class SessionError(ZenError):
    """Session operation failed."""

class SessionLimitError(SessionError):
    """Session limit exceeded."""

class StateError(ZenError):
    """State persistence failed."""

class WorktreeError(ZenError):
    """Worktree operation failed."""

# Use specific exceptions
def create_session(self, config: SessionConfig) -> Session:
    if len(self._sessions) >= MAX_SESSIONS:
        raise SessionLimitError(
            f"Cannot create session: limit of {MAX_SESSIONS} reached"
        )
```

**Benefits:**
- Failures are visible in logs
- Can debug production issues
- Proper exception types are self-documenting
- Can catch specific exceptions vs broad catch-all

---

### 6. Testing: Business Logic Trapped in Widgets

**Violation**: Complex validation logic inside Textual screens, untestable

**Current:**
```python
# screens/new_session_modal.py (666 lines)
class NewSessionModal(ModalScreen):
    def _check_conflicts(self) -> None:
        """Complex validation logic mixed with UI."""
        name = self.query_one("#name-input", Input).value.strip()

        # Business logic here!
        if not name:
            return

        conflicts = detect_conflicts(
            name=name,
            session_type=session_type_map.get(session_type),
            existing=self._existing_sessions,
            max_sessions=self._max_sessions,
        )

        # UI updates mixed with logic
        conflict_container = self.query_one("#conflict-warnings")
        conflict_container.remove_children()

        for conflict in conflicts:
            # Create warning widgets...
```

**Problem:** Cannot test validation without Textual app. UI and logic tightly coupled.

**Zen Separation: Extract Validators**

```python
# NEW: services/validation/session_validator.py
from dataclasses import dataclass

@dataclass
class ValidationResult:
    """Result of validation with errors/warnings."""
    is_valid: bool
    errors: list[str]
    warnings: list[str]

    @property
    def has_issues(self) -> bool:
        return bool(self.errors or self.warnings)

class NewSessionValidator:
    """Validates new session configuration."""

    def __init__(self, max_sessions: int = 10):
        self._max_sessions = max_sessions

    def validate_name(
        self,
        name: str,
        existing_names: set[str]
    ) -> ValidationResult:
        """Validate session name."""
        errors = []
        warnings = []

        if not name or not name.strip():
            errors.append("Session name cannot be empty")

        if name in existing_names:
            warnings.append(f"Session '{name}' already exists")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )

    def validate_directory(self, path: str) -> ValidationResult:
        """Validate working directory."""
        errors = []

        try:
            resolved = Path(path).expanduser().resolve()
            if not resolved.exists():
                errors.append(f"Directory does not exist: {path}")
            elif not resolved.is_dir():
                errors.append(f"Path is not a directory: {path}")
        except Exception as e:
            errors.append(f"Invalid path: {e}")

        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=[]
        )

    def validate_session_limit(
        self,
        current_count: int
    ) -> ValidationResult:
        """Check if session limit allows creation."""
        if current_count >= self._max_sessions:
            return ValidationResult(
                is_valid=False,
                errors=[f"Session limit reached ({self._max_sessions})"],
                warnings=[]
            )

        return ValidationResult(is_valid=True, errors=[], warnings=[])

# SCREEN: Pure presentation
class NewSessionModal(ModalScreen):
    def __init__(self, validator: NewSessionValidator, ...):
        self._validator = validator

    def _check_name(self) -> None:
        """Validate and display results."""
        name = self.widgets.name_input.value

        result = self._validator.validate_name(
            name=name,
            existing_names={s.name for s in self._sessions}
        )

        self._display_validation(result)

    def _display_validation(self, result: ValidationResult) -> None:
        """Update UI based on validation result."""
        container = self.widgets.warnings_container
        container.remove_children()

        for error in result.errors:
            container.mount(ErrorWidget(error))

        for warning in result.warnings:
            container.mount(WarningWidget(warning))
```

**Testing:**
```python
# NEW: tests/services/test_session_validator.py
def test_validate_name_empty():
    validator = NewSessionValidator()
    result = validator.validate_name("", set())

    assert not result.is_valid
    assert "cannot be empty" in result.errors[0]

def test_validate_name_duplicate():
    validator = NewSessionValidator()
    result = validator.validate_name("foo", {"foo", "bar"})

    assert result.is_valid  # Warning, not error
    assert "already exists" in result.warnings[0]

def test_validate_directory_not_exists():
    validator = NewSessionValidator()
    result = validator.validate_directory("/nonexistent/path")

    assert not result.is_valid
    assert "does not exist" in result.errors[0]
```

**Benefits:**
- Business logic fully testable
- Screen reduced from 666 → ~400 lines
- Clear separation: validator = logic, screen = presentation
- Can reuse validator in CLI, API, etc.
- Type-safe ValidationResult vs ad-hoc dictionaries

---

### 7. State Management: No Locking

**Violation**: Concurrent access to session state without synchronization

**Current:**
```python
class SessionManager:
    def _save_state(self) -> bool:
        """Atomic file write, but no lock."""
        temp = self._state_file.with_suffix(".tmp")
        temp.write_text(json.dumps(data))
        temp.rename(self._state_file)  # Atomic on POSIX

    def _load_state(self) -> list[SessionRecord]:
        """No lock acquired."""
        return json.loads(self._state_file.read_text())

    def revive_session(self, session_id: str) -> bool:
        """Modifies session state during discovery."""
        session = self._sessions.get(session_id)

        # Async I/O here!
        if not session.claude_session_id:
            discovery = DiscoveryService(...)
            sessions = discovery.list_claude_sessions()  # Network call!
            session.claude_session_id = sessions[0].session_id  # Mutation

        # Could be out of sync with disk state now
```

**Problem:** If app calls `revive_session()` while another thread calls `_save_state()`, session could be in inconsistent state.

**Zen Synchronization:**

```python
import threading
from contextlib import contextmanager

class SessionStateService:
    """Thread-safe session state persistence."""

    def __init__(self, state_file: Path):
        self._state_file = state_file
        self._lock = threading.RLock()  # Reentrant lock
        self._sessions: dict[str, Session] = {}

    @contextmanager
    def _transaction(self):
        """Context manager for state transactions."""
        self._lock.acquire()
        try:
            yield
        finally:
            self._lock.release()

    def save(self, sessions: list[Session]) -> None:
        """Atomically save with lock."""
        with self._transaction():
            self._atomic_write(sessions)

    def load(self) -> list[Session]:
        """Load with lock."""
        with self._transaction():
            return self._atomic_read()

    def update_session(
        self,
        session_id: str,
        updater: Callable[[Session], None]
    ) -> None:
        """Atomically update single session."""
        with self._transaction():
            session = self._sessions.get(session_id)
            if session:
                updater(session)  # Modify in locked context
                self.save(list(self._sessions.values()))

# Usage
def revive_session(self, session_id: str) -> bool:
    """Safe concurrent access."""

    # Do I/O outside lock
    discovery = DiscoveryService(...)
    claude_sessions = discovery.list_claude_sessions()

    # Update state in lock
    def update(session: Session):
        if claude_sessions and not session.claude_session_id:
            session.claude_session_id = claude_sessions[0].session_id

    self._state.update_session(session_id, update)
```

**Benefits:**
- Thread-safe concurrent access
- Clear transaction boundaries
- No race conditions on state mutations
- I/O outside lock (performance)
- Testable with threading tests

---

### 8. Dependency Injection: Screens Create Services

**Violation**: Presentation layer responsible for service lifecycle

**Current:**
```python
# screens/new_session_modal.py
class NewSessionModal(ModalScreen):
    def __init__(
        self,
        config_manager,
        discovery_service=None,  # Optional!
        tmux_service=None,       # Optional!
        models_service=None,     # Optional!
    ):
        # Screen creates services if not provided
        self._discovery = discovery_service or DiscoveryService()
        self._tmux = tmux_service or TmuxService()
        self._models = models_service or OpenRouterModelsService()
```

**Problem:**
- Hard to test (need to mock at construction)
- Unclear lifetime of services
- Violates dependency inversion (screen depends on concrete classes)

**Zen Injection:**

```python
# NEW: app.py - Service container
from dataclasses import dataclass

@dataclass
class Services:
    """Application service container."""
    tmux: TmuxService
    config: ConfigManager
    sessions: SessionManager
    worktree: WorktreeService
    tokens: TokenService
    discovery: DiscoveryService
    models: OpenRouterModelsService
    state: SessionStateService
    events: EventBus

    @classmethod
    def create(cls, config_path: Path) -> "Services":
        """Wire up all services."""
        config = ConfigManager(config_path)
        tmux = TmuxService()
        git = GitService()
        worktree = WorktreeService(git)
        state = SessionStateService(config.state_file)
        tokens = TokenService()
        events = EventBus()

        sessions = SessionManager(
            tmux=tmux,
            state=state,
            worktree=worktree,
            tokens=tokens,
            events=events,
        )

        return cls(
            tmux=tmux,
            config=config,
            sessions=sessions,
            worktree=worktree,
            tokens=tokens,
            discovery=DiscoveryService(),
            models=OpenRouterModelsService(),
            state=state,
            events=events,
        )

class ZenApp(App):
    def __init__(self):
        super().__init__()
        self.services = Services.create(
            config_path=Path.home() / ".config" / "zen-portal"
        )

    def push_new_session_modal(self):
        """Inject dependencies into screen."""
        modal = NewSessionModal(
            config=self.services.config,
            discovery=self.services.discovery,
            tmux=self.services.tmux,
            models=self.services.models,
            sessions=self.services.sessions,
        )
        self.push_screen(modal)

# SCREEN: Pure presentation, all deps injected
class NewSessionModal(ModalScreen):
    def __init__(
        self,
        config: ConfigManager,
        discovery: DiscoveryService,
        tmux: TmuxService,
        models: OpenRouterModelsService,
        sessions: SessionManager,
    ):
        # All required, no defaults
        self._config = config
        self._discovery = discovery
        self._tmux = tmux
        self._models = models
        self._sessions = sessions
```

**Testing:**
```python
# tests/screens/test_new_session_modal.py
def test_new_session_modal_validation():
    # Mock all services
    config = Mock(spec=ConfigManager)
    discovery = Mock(spec=DiscoveryService)
    tmux = Mock(spec=TmuxService)
    models = Mock(spec=OpenRouterModelsService)
    sessions = Mock(spec=SessionManager)

    modal = NewSessionModal(
        config=config,
        discovery=discovery,
        tmux=tmux,
        models=models,
        sessions=sessions,
    )

    # Test screen behavior with mocked services
```

**Benefits:**
- Clear service lifetime (app controls creation)
- Easy to test (inject mocks)
- Dependency graph visible in one place (Services.create)
- Screens are pure presentation
- Can swap implementations (e.g., MockTmuxService)

---

### 9. Configuration: Three Sources, No Schema

**Violation**: Config merged from 3 sources without validation

**Current:**
```python
# services/config.py
class ConfigManager:
    def __init__(self, config_dir: Path):
        # Layer 1: Defaults (hardcoded)
        self._defaults = {...}

        # Layer 2: User config (JSON file)
        self._user_config = self._load_config()

        # Layer 3: Profile (theme override)
        self._profile = self._load_profile()

    def get(self, key: str, default=None):
        """3-way merge, no validation."""
        return (
            self._profile.get(key) or
            self._user_config.get(key) or
            self._defaults.get(key) or
            default
        )
```

**Problems:**
- No schema validation (user can set any key)
- Typos silently ignored (`"worktre_enable": true`)
- Type errors at runtime (`max_sessions: "10"` is string)
- Hard to discover what config options exist

**Zen Schema:**

```python
# NEW: models/config.py
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class WorktreeConfig:
    """Worktree-specific configuration."""
    enabled: bool = False
    default_branch: str = "main"
    symlink_env_files: bool = True

@dataclass
class ZenAIConfig:
    """Zen AI configuration."""
    provider: str = "claude"
    model: str = "claude-sonnet-4.5"

@dataclass
class ProxyConfig:
    """OpenRouter proxy configuration."""
    enabled: bool = False
    api_key: str = ""
    api_url: str = "https://openrouter.ai/api/v1"

@dataclass
class AppConfig:
    """Complete application configuration with defaults."""

    # Session limits
    max_sessions: int = 10
    enabled_session_types: list[str] = field(default_factory=lambda: ["ai", "shell"])

    # Directories
    default_working_dir: Path = field(default_factory=Path.cwd)

    # Worktrees
    worktree: WorktreeConfig = field(default_factory=WorktreeConfig)

    # AI
    zen_ai: ZenAIConfig = field(default_factory=ZenAIConfig)

    # Proxy
    proxy: ProxyConfig = field(default_factory=ProxyConfig)

    # UI
    theme: str = "textual-dark"
    exit_behavior: str = "ask"  # ask | kill_all | keep_all

    @classmethod
    def from_dict(cls, data: dict) -> "AppConfig":
        """Parse config from dict with validation."""
        return cls(
            max_sessions=int(data.get("max_sessions", 10)),
            enabled_session_types=data.get("enabled_session_types", ["ai", "shell"]),
            default_working_dir=Path(data.get("default_working_dir", ".")),
            worktree=WorktreeConfig(**data.get("worktree", {})),
            zen_ai=ZenAIConfig(**data.get("zen_ai", {})),
            proxy=ProxyConfig(**data.get("proxy", {})),
            theme=data.get("theme", "textual-dark"),
            exit_behavior=data.get("exit_behavior", "ask"),
        )

    def to_dict(self) -> dict:
        """Serialize for JSON storage."""
        return {
            "max_sessions": self.max_sessions,
            "enabled_session_types": self.enabled_session_types,
            "default_working_dir": str(self.default_working_dir),
            "worktree": {
                "enabled": self.worktree.enabled,
                "default_branch": self.worktree.default_branch,
                "symlink_env_files": self.worktree.symlink_env_files,
            },
            "zen_ai": {
                "provider": self.zen_ai.provider,
                "model": self.zen_ai.model,
            },
            "proxy": {
                "enabled": self.proxy.enabled,
                "api_key": self.proxy.api_key,
                "api_url": self.proxy.api_url,
            },
            "theme": self.theme,
            "exit_behavior": self.exit_behavior,
        }

# SIMPLIFIED: services/config.py
class ConfigManager:
    """Manages application configuration."""

    def __init__(self, config_dir: Path):
        self._config_file = config_dir / "config.json"
        self._config = self._load()

    def _load(self) -> AppConfig:
        """Load config from file or use defaults."""
        if self._config_file.exists():
            try:
                data = json.loads(self._config_file.read_text())
                return AppConfig.from_dict(data)
            except Exception as e:
                logger.error(f"Failed to load config: {e}, using defaults")

        return AppConfig()  # Defaults

    def save(self, config: AppConfig) -> None:
        """Save config to file."""
        self._config_file.write_text(
            json.dumps(config.to_dict(), indent=2)
        )
        self._config = config

    @property
    def config(self) -> AppConfig:
        """Current configuration."""
        return self._config
```

**Benefits:**
- Type-safe config access: `config.worktree.enabled` (not `config.get("worktree_enable")`)
- IDE autocomplete works
- Invalid keys caught at load time
- Clear documentation (dataclass fields)
- Easy to test (construct AppConfig directly)
- Serialization centralized

---

### 10. Naming: Unclear Intent

**Violation**: Names don't reveal purpose

**Current Examples:**

```python
# What does this do?
def _path_to_claude_project_name(self, path: Path) -> str:
    """Convert a path to Claude's project directory name format."""
    return str(path).replace("/", "-").replace("_", "-")

# What's the difference?
WorktreeService       # Git operations
WorktreeManager       # Session integration

# What type is this?
provider: str = "claude"  # String, but acts like enum

# What's in here?
NewSessionType    # Enum for session types
SessionType       # Also enum for session types? Same thing?
```

**Zen Naming:**

```python
# Clear purpose
class ClaudePathEncoder:
    """Encodes filesystem paths for Claude's directory naming convention."""

    @staticmethod
    def encode(path: Path) -> str:
        """Convert /a/b_c to -a-b-c"""
        return str(path).replace("/", "-").replace("_", "-")

    @staticmethod
    def decode(encoded: str, base: Path) -> Path:
        """Convert -a-b-c back to /a/b_c"""
        # Greedy reconstruction...

# Single worktree service (merged)
WorktreeService  # All worktree operations

# Proper enum
class AIProvider(Enum):
    CLAUDE = "claude"
    CODEX = "codex"
    GEMINI = "gemini"
    OPENROUTER = "openrouter"

# Single session type enum
class SessionType(Enum):
    """Type of session: AI assistant or shell."""
    AI = "ai"
    SHELL = "shell"
```

**Naming Principles:**
- Class names are nouns: `PathEncoder`, `SessionValidator`
- Method names are verbs: `encode()`, `validate()`, `create()`
- Booleans are questions: `is_valid`, `has_errors`, `should_retry`
- No abbreviations: `manager` not `mgr`, `service` not `svc`
- Specific not generic: `ClaudePathEncoder` not `PathConverter`

---

## Implementation Roadmap

### Phase 1: Foundation (High Impact, Low Risk)
**Goal**: Improve testability and reduce coupling

1. **Extract SessionStateService** (1 day)
   - Move persistence logic from SessionManager
   - Add threading locks
   - Create tests for state service
   - Result: SessionManager 832 → 500 lines

2. **Create Service Container** (1 day)
   - Centralize service creation in app.py
   - Inject dependencies into screens
   - Remove default service creation in screens
   - Result: Clear dependency graph, testable screens

3. **Add Logging Infrastructure** (0.5 days)
   - Replace `pass` with logged warnings
   - Add logger to all services
   - Result: Debuggable production issues

### Phase 2: Simplification (Medium Impact, Medium Risk)
**Goal**: Reduce complexity and duplication

4. **Consolidate Worktree Services** (1 day)
   - Merge WorktreeManager into WorktreeService
   - Update all imports
   - Create comprehensive tests
   - Result: 425 → 300 lines, single API

5. **Cache Widget References** (1 day)
   - Create WidgetRefs dataclass for NewSessionModal
   - Replace 152 query_one calls with cached refs
   - Measure performance improvement
   - Result: O(n) → O(1) widget access

6. **Define Config Schema** (1 day)
   - Create AppConfig dataclass
   - Add from_dict/to_dict serialization
   - Validate on load
   - Result: Type-safe config, catch errors early

### Phase 3: Architecture (High Impact, Higher Risk)
**Goal**: Clean boundaries and testability

7. **Extract Business Logic from Screens** (2 days)
   - Create NewSessionValidator
   - Create TemplateValidator
   - Move validation out of modals
   - Write comprehensive tests
   - Result: 666 → 400 lines in NewSessionModal, 90% test coverage

8. **Create Exception Hierarchy** (0.5 days)
   - Define ZenError base class
   - Create specific exceptions (SessionError, StateError, etc.)
   - Replace string errors with typed exceptions
   - Result: Better error handling, clearer failures

9. **Add Event Bus** (1 day)
   - Replace callback pattern with pub/sub
   - Decouple SessionManager from UI
   - Result: Services can evolve independently

### Phase 4: Quality (Ongoing)
**Goal**: Comprehensive testing and documentation

10. **Increase Test Coverage** (3 days)
    - Write tests for all services
    - Add integration tests
    - Target 80% coverage
    - Result: Confidence in refactoring

11. **Add Docstrings** (2 days)
    - Document all public APIs
    - Add module-level docs
    - Explain complex algorithms (path reconstruction)
    - Result: Self-documenting codebase

---

## Metrics

**Current State:**
- Files > 500 lines: 8
- DOM queries: 152
- Test files: 15 / 83 source files (18%)
- Service implementations: 2 (worktree duplication)
- Exception types: 1 (SessionLimitError)
- Logging: Minimal

**Target State:**
- Files > 500 lines: 0
- DOM queries: <20 (cached)
- Test files: 50+ / 90+ source files (>50%)
- Service implementations: 1 per concern
- Exception types: 8+ (proper hierarchy)
- Logging: Comprehensive

**Complexity Reduction:**
- SessionManager: 832 → 300 lines (-64%)
- NewSessionModal: 666 → 400 lines (-40%)
- Total codebase: 15,299 → ~13,000 lines (-15%)

---

## Zen Code Checklist

Before merging code, ask:

- [ ] **Simplicity**: Can this be simpler? Remove complexity, not features
- [ ] **Clarity**: Does the name reveal intent? Can a new developer understand?
- [ ] **Minimalism**: Is this abstraction necessary? Solve real problems only
- [ ] **Separation**: Does this module know only what it needs?
- [ ] **Testability**: Can I test this easily? Is business logic pure?
- [ ] **Documentation**: Does the code explain itself? Are complex parts documented?
- [ ] **Error Handling**: Are failures logged? Do exceptions have types?
- [ ] **Performance**: Are there obvious inefficiencies? (N+1 queries, etc.)

---

## Conclusion

The Zenportal codebase is well-structured overall but has accumulated complexity. Applying zen principles to the *code itself*:

- **Extract services** (SessionStateService, TokenService, EventBus)
- **Consolidate implementations** (single WorktreeService)
- **Separate concerns** (validators out of screens)
- **Cache references** (widget lookup once, not 152 times)
- **Inject dependencies** (container pattern)
- **Schema validation** (typed config)
- **Proper errors** (exception hierarchy + logging)
- **Test everything** (80% coverage target)

**Core philosophy**: Code should be easy to understand, easy to change, and easy to verify.

Like a zen garden, the codebase should reveal its structure at a glance, with no unnecessary elements obscuring the essential design.
