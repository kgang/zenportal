# Architecture Proposal: Zen Portal Production-Ready Implementation

A clean, testable architecture for the multi-session Claude Code manager.

---

## Design Goals

| Goal | Measure | Target |
|------|---------|--------|
| Testability | Coverage | >80% |
| Extensibility | New feature effort | <2 hours |
| Performance | Response time | <100ms |
| Reliability | Error recovery | Graceful always |
| Maintainability | File size | <300 LOC each |

---

## Module Structure

```
zen_portal/
├── __init__.py
├── __main__.py              # Entry point
├── app.py                   # Main Textual App
├── config.py                # Configuration management
│
├── models/
│   ├── __init__.py
│   ├── session.py           # Session dataclass
│   ├── budget.py            # AAU budget model
│   └── events.py            # Custom events
│
├── services/
│   ├── __init__.py
│   ├── tmux.py              # Tmux abstraction (low-level)
│   ├── session_manager.py   # Session lifecycle (high-level)
│   ├── output_streamer.py   # Async output streaming
│   └── validation.py        # Input validation
│
├── widgets/
│   ├── __init__.py
│   ├── session_list.py      # Session list widget
│   ├── session_detail.py    # Session detail widget
│   ├── output_view.py       # Output streaming widget
│   ├── status_bar.py        # AAU + status display
│   └── help_overlay.py      # Help screen widget
│
├── screens/
│   ├── __init__.py
│   ├── main.py              # Main screen (list + detail)
│   ├── focus.py             # Focused output screen
│   └── new_session.py       # New session modal
│
└── tests/
    ├── __init__.py
    ├── conftest.py          # Shared fixtures
    ├── test_tmux.py         # Tmux service tests
    ├── test_session_manager.py
    ├── test_widgets.py
    └── test_screens.py
```

---

## Layer Architecture

```
+--------------------------------------------------+
|                    UI Layer                       |
|  (App, Screens, Widgets)                         |
|  - Handles user input                            |
|  - Renders state                                 |
|  - Dispatches actions                            |
+--------------------------------------------------+
                        |
                        v (events/actions)
+--------------------------------------------------+
|                 Service Layer                     |
|  (SessionManager, OutputStreamer)                |
|  - Business logic                                |
|  - State management                              |
|  - Coordinates operations                        |
+--------------------------------------------------+
                        |
                        v (commands)
+--------------------------------------------------+
|               Infrastructure Layer                |
|  (TmuxService, Validation)                       |
|  - External system interaction                   |
|  - Low-level operations                          |
|  - No business logic                             |
+--------------------------------------------------+
```

---

## Core Abstractions

### Session Model

```python
# models/session.py
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid

class SessionState(Enum):
    SPROUTING = "sprouting"
    GROWING = "growing"
    BLOOMED = "bloomed"
    WILTED = "wilted"
    DORMANT = "dormant"

@dataclass
class Session:
    """A Claude Code session."""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    prompt: str = ""
    state: SessionState = SessionState.SPROUTING
    created_at: datetime = field(default_factory=datetime.now)
    ended_at: Optional[datetime] = None
    exit_code: Optional[int] = None
    output_lines: int = 0

    @property
    def age_seconds(self) -> int:
        return int((datetime.now() - self.created_at).total_seconds())

    @property
    def age_display(self) -> str:
        """Human-readable age."""
        seconds = self.age_seconds
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m"
        else:
            return f"{seconds // 3600}h"

    @property
    def status_glyph(self) -> str:
        glyphs = {
            SessionState.SPROUTING: ".",
            SessionState.GROWING: "*",
            SessionState.BLOOMED: "+",
            SessionState.WILTED: "-",
            SessionState.DORMANT: "~",
        }
        return glyphs.get(self.state, "?")

    @property
    def prompt_preview(self) -> str:
        """Truncated prompt for display."""
        if len(self.prompt) <= 30:
            return self.prompt
        return self.prompt[:27] + "..."

    def to_dict(self) -> dict:
        """Serialize for persistence."""
        return {
            "id": self.id,
            "prompt": self.prompt,
            "state": self.state.value,
            "created_at": self.created_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "exit_code": self.exit_code,
            "output_lines": self.output_lines,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Session":
        """Deserialize from persistence."""
        return cls(
            id=data["id"],
            prompt=data["prompt"],
            state=SessionState(data["state"]),
            created_at=datetime.fromisoformat(data["created_at"]),
            ended_at=datetime.fromisoformat(data["ended_at"]) if data["ended_at"] else None,
            exit_code=data.get("exit_code"),
            output_lines=data.get("output_lines", 0),
        )
```

### Custom Events

```python
# models/events.py
from textual.message import Message
from .session import Session

class SessionCreated(Message):
    """Fired when a new session is created."""
    def __init__(self, session: Session) -> None:
        self.session = session
        super().__init__()

class SessionStateChanged(Message):
    """Fired when session state changes."""
    def __init__(self, session: Session, old_state: str) -> None:
        self.session = session
        self.old_state = old_state
        super().__init__()

class SessionOutput(Message):
    """Fired when new output is available."""
    def __init__(self, session_id: str, output: str) -> None:
        self.session_id = session_id
        self.output = output
        super().__init__()

class SessionPruned(Message):
    """Fired when a session is pruned."""
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__()
```

---

## Service Layer

### TmuxService (Infrastructure)

```python
# services/tmux.py
from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Optional
import shlex

@dataclass
class TmuxResult:
    """Result of a tmux operation."""
    success: bool
    output: str = ""
    error: str = ""

class TmuxService:
    """Low-level tmux operations. No business logic."""

    def __init__(self, socket_path: Optional[Path] = None):
        self._socket = socket_path
        self._timeout = 5

    def _base_cmd(self) -> list[str]:
        """Base tmux command with optional socket."""
        if self._socket:
            return ["tmux", "-S", str(self._socket)]
        return ["tmux"]

    def session_exists(self, name: str) -> bool:
        """Check if a tmux session exists."""
        cmd = self._base_cmd() + ["has-session", "-t", name]
        result = subprocess.run(cmd, capture_output=True, timeout=self._timeout)
        return result.returncode == 0

    def create_session(
        self,
        name: str,
        command: list[str],
        working_dir: Path,
    ) -> TmuxResult:
        """Create a new detached tmux session."""
        cmd = self._base_cmd() + [
            "new-session",
            "-d",
            "-s", name,
            "-c", str(working_dir),
        ] + command

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            return TmuxResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return TmuxResult(success=False, error="Timeout creating session")

    def kill_session(self, name: str) -> TmuxResult:
        """Kill a tmux session."""
        cmd = self._base_cmd() + ["kill-session", "-t", name]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            return TmuxResult(
                success=result.returncode == 0,
                error=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return TmuxResult(success=False, error="Timeout killing session")

    def capture_pane(self, name: str, lines: int = 100) -> TmuxResult:
        """Capture output from a session's pane."""
        cmd = self._base_cmd() + [
            "capture-pane",
            "-t", name,
            "-p",
            "-S", f"-{lines}",  # Last N lines
        ]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            return TmuxResult(
                success=result.returncode == 0,
                output=result.stdout,
                error=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return TmuxResult(success=False, error="Timeout capturing output")

    def send_keys(self, name: str, keys: str) -> TmuxResult:
        """Send keys to a session."""
        cmd = self._base_cmd() + ["send-keys", "-t", name, keys, "Enter"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            return TmuxResult(
                success=result.returncode == 0,
                error=result.stderr,
            )
        except subprocess.TimeoutExpired:
            return TmuxResult(success=False, error="Timeout sending keys")

    def list_sessions(self) -> list[str]:
        """List all tmux session names."""
        cmd = self._base_cmd() + ["list-sessions", "-F", "#{session_name}"]
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
            if result.returncode == 0:
                return result.stdout.strip().split("\n")
            return []
        except subprocess.TimeoutExpired:
            return []
```

### SessionManager (Business Logic)

```python
# services/session_manager.py
from pathlib import Path
from typing import Callable, Optional
from datetime import datetime

from ..models.session import Session, SessionState
from ..models.events import SessionCreated, SessionStateChanged, SessionPruned
from .tmux import TmuxService
from .validation import validate_prompt

class SessionLimitError(Exception):
    """Raised when session limits are exceeded."""
    pass

class ValidationError(Exception):
    """Raised when input validation fails."""
    pass

class SessionManager:
    """Manages session lifecycle. Business logic lives here."""

    MAX_SESSIONS = 10
    MAX_ACTIVE_SESSIONS = 5
    SESSION_PREFIX = "zen"

    def __init__(
        self,
        tmux: TmuxService,
        working_dir: Path,
        on_event: Optional[Callable] = None,
    ):
        self._tmux = tmux
        self._working_dir = working_dir
        self._on_event = on_event
        self._sessions: dict[str, Session] = {}

    @property
    def sessions(self) -> list[Session]:
        """All sessions sorted by creation time (newest first)."""
        return sorted(
            self._sessions.values(),
            key=lambda s: s.created_at,
            reverse=True,
        )

    @property
    def active_count(self) -> int:
        """Count of currently active sessions."""
        return len([
            s for s in self._sessions.values()
            if s.state in (SessionState.SPROUTING, SessionState.GROWING)
        ])

    def _emit(self, event) -> None:
        """Emit an event if handler registered."""
        if self._on_event:
            self._on_event(event)

    def _session_name(self, session_id: str) -> str:
        """Generate tmux session name from session ID."""
        return f"{self.SESSION_PREFIX}-{session_id[:8]}"

    def create_session(self, prompt: str) -> Session:
        """Create a new Claude session."""
        # Validate limits
        if len(self._sessions) >= self.MAX_SESSIONS:
            raise SessionLimitError(
                f"Maximum sessions ({self.MAX_SESSIONS}) reached"
            )

        if self.active_count >= self.MAX_ACTIVE_SESSIONS:
            raise SessionLimitError(
                f"Maximum active sessions ({self.MAX_ACTIVE_SESSIONS}) reached"
            )

        # Validate prompt
        valid, error = validate_prompt(prompt)
        if not valid:
            raise ValidationError(error)

        # Create session model
        session = Session(prompt=prompt)
        self._sessions[session.id] = session

        # Build Claude command
        full_prompt = f"In {self._working_dir.name}:\n\n{prompt}"
        command = ["claude", "--print", full_prompt]

        # Create tmux session
        tmux_name = self._session_name(session.id)
        result = self._tmux.create_session(
            name=tmux_name,
            command=command,
            working_dir=self._working_dir,
        )

        if result.success:
            session.state = SessionState.GROWING
        else:
            session.state = SessionState.WILTED

        self._emit(SessionCreated(session))
        return session

    def prune_session(self, session_id: str) -> bool:
        """Kill and remove a session."""
        session = self._sessions.get(session_id)
        if not session:
            return False

        tmux_name = self._session_name(session_id)
        self._tmux.kill_session(tmux_name)

        session.state = SessionState.WILTED
        session.ended_at = datetime.now()

        self._emit(SessionPruned(session_id))
        return True

    def get_output(self, session_id: str, lines: int = 100) -> str:
        """Get recent output from a session."""
        session = self._sessions.get(session_id)
        if not session:
            return ""

        tmux_name = self._session_name(session_id)
        result = self._tmux.capture_pane(tmux_name, lines=lines)

        if result.success:
            session.output_lines = len(result.output.strip().split("\n"))
            return result.output

        return ""

    def send_input(self, session_id: str, input_text: str) -> bool:
        """Send input to a session (water the plant)."""
        session = self._sessions.get(session_id)
        if not session or session.state != SessionState.GROWING:
            return False

        # Validate input
        valid, error = validate_prompt(input_text)
        if not valid:
            return False

        tmux_name = self._session_name(session_id)
        result = self._tmux.send_keys(tmux_name, input_text)
        return result.success

    def refresh_states(self) -> None:
        """Check and update all session states."""
        for session in self._sessions.values():
            if session.state not in (SessionState.GROWING, SessionState.SPROUTING):
                continue

            tmux_name = self._session_name(session.id)
            old_state = session.state

            if self._tmux.session_exists(tmux_name):
                session.state = SessionState.GROWING
            else:
                session.state = SessionState.BLOOMED
                session.ended_at = datetime.now()

            if session.state != old_state:
                self._emit(SessionStateChanged(session, old_state.value))

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID."""
        return self._sessions.get(session_id)

    def cleanup_old_sessions(self, max_age_hours: int = 24) -> int:
        """Remove sessions older than max_age_hours."""
        now = datetime.now()
        removed = 0

        for session_id in list(self._sessions.keys()):
            session = self._sessions[session_id]
            age_hours = (now - session.created_at).total_seconds() / 3600

            if age_hours > max_age_hours:
                # Kill if still running
                if session.state in (SessionState.GROWING, SessionState.SPROUTING):
                    self.prune_session(session_id)

                del self._sessions[session_id]
                removed += 1

        return removed
```

### Validation Service

```python
# services/validation.py
import re
from typing import Tuple, Optional

# Patterns that suggest command injection attempts
SUSPICIOUS_PATTERNS = [
    r'`[^`]+`',           # Backticks
    r'\$\([^)]+\)',       # Command substitution
    r'&&\s*\w+',          # Command chaining with &&
    r'\|\|\s*\w+',        # Command chaining with ||
    r';\s*\w+',           # Semicolon command separation
    r'>\s*/[a-z]',        # Redirect to absolute path
    r'rm\s+-[rf]+',       # Dangerous rm variations
    r'chmod\s+[0-7]+',    # Permission changes
    r'curl\s+.+\|\s*sh',  # Pipe curl to shell
]

MAX_PROMPT_LENGTH = 2000

def validate_prompt(prompt: str) -> Tuple[bool, Optional[str]]:
    """
    Validate user prompt for security issues.

    Returns (is_valid, error_message).
    """
    if not prompt or not prompt.strip():
        return False, "Prompt cannot be empty"

    if len(prompt) > MAX_PROMPT_LENGTH:
        return False, f"Prompt too long (max {MAX_PROMPT_LENGTH} chars)"

    for pattern in SUSPICIOUS_PATTERNS:
        if re.search(pattern, prompt, re.IGNORECASE):
            return False, "Prompt contains suspicious patterns"

    return True, None
```

---

## Widget Layer

### Session List Widget

```python
# widgets/session_list.py
from textual.reactive import reactive
from textual.widgets import Static, ListView, ListItem
from textual.message import Message

from ..models.session import Session

class SessionSelected(Message):
    """Fired when a session is selected."""
    def __init__(self, session: Session) -> None:
        self.session = session
        super().__init__()

class SessionListItem(ListItem):
    """A single session in the list."""

    def __init__(self, session: Session) -> None:
        super().__init__()
        self.session = session

    def compose(self):
        yield Static(self._render())

    def _render(self) -> str:
        s = self.session
        return f"[{s.status_glyph}] {s.prompt_preview:<30} {s.age_display:>5}"


class SessionList(Static):
    """List of all sessions with selection."""

    sessions = reactive(list, recompose=True)
    selected_index = reactive(0)

    DEFAULT_CSS = """
    SessionList {
        width: 100%;
        height: 100%;
    }

    SessionList .selected {
        background: $primary 20%;
    }

    SessionList .growing {
        color: $success;
    }

    SessionList .wilted {
        color: $error;
    }
    """

    def compose(self):
        if not self.sessions:
            yield Static("No sessions. Press [n] to create one.")
            return

        for i, session in enumerate(self.sessions):
            item = SessionListItem(session)
            if i == self.selected_index:
                item.add_class("selected")
            item.add_class(session.state.value)
            yield item

    def watch_selected_index(self, index: int) -> None:
        """Emit selection event when index changes."""
        if self.sessions and 0 <= index < len(self.sessions):
            self.post_message(SessionSelected(self.sessions[index]))

    def action_move_down(self) -> None:
        if self.sessions:
            self.selected_index = min(
                self.selected_index + 1,
                len(self.sessions) - 1
            )

    def action_move_up(self) -> None:
        self.selected_index = max(self.selected_index - 1, 0)

    def get_selected(self) -> Session | None:
        if self.sessions and 0 <= self.selected_index < len(self.sessions):
            return self.sessions[self.selected_index]
        return None
```

### Output View Widget

```python
# widgets/output_view.py
from textual.reactive import reactive
from textual.widgets import Static, RichLog
from textual.app import ComposeResult

class OutputView(Static):
    """Scrolling output display for a session."""

    output = reactive("")
    session_name = reactive("")

    DEFAULT_CSS = """
    OutputView {
        width: 100%;
        height: 100%;
        border: solid $primary;
        padding: 0 1;
    }

    OutputView #header {
        height: 1;
        background: $surface;
        color: $text-muted;
    }

    OutputView #content {
        height: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        yield Static(f" {self.session_name}", id="header")
        yield RichLog(id="content", highlight=True, markup=True)

    def watch_output(self, new_output: str) -> None:
        """Update the log when output changes."""
        log = self.query_one("#content", RichLog)
        log.clear()
        log.write(new_output)

    def watch_session_name(self, name: str) -> None:
        """Update header when session changes."""
        header = self.query_one("#header", Static)
        header.update(f" {name}")
```

---

## Screen Layer

### Main Screen

```python
# screens/main.py
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Static, Footer

from ..widgets.session_list import SessionList, SessionSelected
from ..widgets.output_view import OutputView
from ..widgets.status_bar import StatusBar
from ..services.session_manager import SessionManager

class MainScreen(Screen):
    """Main application screen with session list and output preview."""

    BINDINGS = [
        ("j", "move_down", "Down"),
        ("k", "move_up", "Up"),
        ("n", "new_session", "New"),
        ("p", "prune", "Prune"),
        ("enter", "focus_session", "Focus"),
        ("a", "attach", "Attach"),
        ("question_mark", "show_help", "Help"),
        ("q", "quit", "Quit"),
    ]

    DEFAULT_CSS = """
    MainScreen {
        layout: grid;
        grid-size: 2 2;
        grid-columns: 1fr 1fr;
        grid-rows: 1fr auto;
    }

    #session-list {
        column-span: 1;
        row-span: 1;
    }

    #output-view {
        column-span: 1;
        row-span: 1;
    }

    #status-bar {
        column-span: 2;
        row-span: 1;
        height: 1;
    }
    """

    def __init__(self, session_manager: SessionManager):
        super().__init__()
        self._manager = session_manager

    def compose(self) -> ComposeResult:
        yield SessionList(id="session-list")
        yield OutputView(id="output-view")
        yield StatusBar(id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        """Initialize session list."""
        self._refresh_sessions()
        self.set_interval(1.0, self._poll_sessions)

    def _refresh_sessions(self) -> None:
        """Update session list widget."""
        session_list = self.query_one("#session-list", SessionList)
        session_list.sessions = self._manager.sessions

    def _poll_sessions(self) -> None:
        """Periodic refresh of session states."""
        self._manager.refresh_states()
        self._refresh_sessions()

        # Update output for selected session
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if selected:
            output = self._manager.get_output(selected.id)
            output_view = self.query_one("#output-view", OutputView)
            output_view.session_name = selected.prompt_preview
            output_view.output = output

    def on_session_selected(self, event: SessionSelected) -> None:
        """Handle session selection changes."""
        output = self._manager.get_output(event.session.id)
        output_view = self.query_one("#output-view", OutputView)
        output_view.session_name = event.session.prompt_preview
        output_view.output = output

    def action_move_down(self) -> None:
        self.query_one("#session-list", SessionList).action_move_down()

    def action_move_up(self) -> None:
        self.query_one("#session-list", SessionList).action_move_up()

    def action_new_session(self) -> None:
        from .new_session import NewSessionModal
        self.app.push_screen(NewSessionModal(self._manager))

    def action_prune(self) -> None:
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if selected:
            self._manager.prune_session(selected.id)
            self._refresh_sessions()
            self.notify(f"Pruned: {selected.prompt_preview}")

    def action_focus_session(self) -> None:
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if selected:
            from .focus import FocusScreen
            self.app.push_screen(FocusScreen(self._manager, selected.id))

    def action_attach(self) -> None:
        """Attach to tmux session (leaves TUI)."""
        session_list = self.query_one("#session-list", SessionList)
        selected = session_list.get_selected()
        if selected:
            self.app.exit(message=f"attach:{selected.id}")

    def action_show_help(self) -> None:
        from ..widgets.help_overlay import HelpOverlay
        self.app.push_screen(HelpOverlay())
```

---

## Testing Strategy

### Unit Tests (Services)

```python
# tests/test_tmux.py
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from zen_portal.services.tmux import TmuxService, TmuxResult

class TestTmuxService:

    @pytest.fixture
    def tmux(self):
        return TmuxService()

    def test_session_exists_true(self, tmux):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            assert tmux.session_exists("test-session") is True

    def test_session_exists_false(self, tmux):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=1)
            assert tmux.session_exists("test-session") is False

    def test_create_session_success(self, tmux):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="",
                stderr="",
            )
            result = tmux.create_session(
                name="test",
                command=["echo", "hello"],
                working_dir=Path("/tmp"),
            )
            assert result.success is True

    def test_create_session_failure(self, tmux):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="duplicate session",
            )
            result = tmux.create_session(
                name="test",
                command=["echo", "hello"],
                working_dir=Path("/tmp"),
            )
            assert result.success is False
            assert "duplicate" in result.error


# tests/test_session_manager.py
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from zen_portal.services.session_manager import (
    SessionManager,
    SessionLimitError,
    ValidationError,
)
from zen_portal.services.tmux import TmuxService, TmuxResult
from zen_portal.models.session import SessionState

class TestSessionManager:

    @pytest.fixture
    def mock_tmux(self):
        tmux = MagicMock(spec=TmuxService)
        tmux.create_session.return_value = TmuxResult(success=True)
        tmux.session_exists.return_value = True
        return tmux

    @pytest.fixture
    def manager(self, mock_tmux):
        return SessionManager(
            tmux=mock_tmux,
            working_dir=Path("/tmp/test"),
        )

    def test_create_session_success(self, manager):
        session = manager.create_session("test prompt")
        assert session.prompt == "test prompt"
        assert session.state == SessionState.GROWING

    def test_create_session_empty_prompt(self, manager):
        with pytest.raises(ValidationError):
            manager.create_session("")

    def test_create_session_suspicious_prompt(self, manager):
        with pytest.raises(ValidationError):
            manager.create_session("test `rm -rf /`")

    def test_session_limit_total(self, manager):
        for i in range(SessionManager.MAX_SESSIONS):
            manager.create_session(f"prompt {i}")

        with pytest.raises(SessionLimitError):
            manager.create_session("one too many")

    def test_prune_session(self, manager, mock_tmux):
        session = manager.create_session("test")
        result = manager.prune_session(session.id)
        assert result is True
        assert session.state == SessionState.WILTED
        mock_tmux.kill_session.assert_called_once()
```

### Integration Tests (Widgets/Screens)

```python
# tests/test_screens.py
import pytest
from unittest.mock import MagicMock
from pathlib import Path

from zen_portal.app import ZenPortalApp
from zen_portal.services.session_manager import SessionManager
from zen_portal.services.tmux import TmuxService, TmuxResult

@pytest.fixture
def mock_manager():
    tmux = MagicMock(spec=TmuxService)
    tmux.create_session.return_value = TmuxResult(success=True)
    tmux.session_exists.return_value = True
    tmux.capture_pane.return_value = TmuxResult(
        success=True,
        output="Test output\n"
    )

    return SessionManager(
        tmux=tmux,
        working_dir=Path("/tmp/test"),
    )

@pytest.mark.asyncio
async def test_main_screen_navigation(mock_manager):
    app = ZenPortalApp(session_manager=mock_manager)

    # Create some sessions
    mock_manager.create_session("first")
    mock_manager.create_session("second")

    async with app.run_test() as pilot:
        # Navigate down
        await pilot.press("j")
        # Check selection moved (would need to query widget state)

        # Navigate up
        await pilot.press("k")

@pytest.mark.asyncio
async def test_new_session_modal(mock_manager):
    app = ZenPortalApp(session_manager=mock_manager)

    async with app.run_test() as pilot:
        # Open new session modal
        await pilot.press("n")

        # Type prompt
        await pilot.press(*"test prompt")

        # Submit
        await pilot.press("enter")

        # Verify session created
        assert len(mock_manager.sessions) == 1
```

---

## Configuration

```python
# config.py
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import json

@dataclass
class ZenConfig:
    """Application configuration."""

    # Session limits
    max_sessions: int = 10
    max_active_sessions: int = 5
    session_timeout_minutes: int = 60

    # AAU budget
    daily_aau_budget: float = 1.0

    # Paths
    working_dir: Optional[Path] = None
    socket_path: Optional[Path] = None

    # UI preferences
    show_output_preview: bool = True
    auto_refresh_seconds: float = 1.0

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "ZenConfig":
        """Load config from file or defaults."""
        if path is None:
            path = Path.home() / ".zen-portal" / "config.json"

        if path.exists():
            with open(path) as f:
                data = json.load(f)
                return cls(**data)

        return cls()

    def save(self, path: Optional[Path] = None) -> None:
        """Save config to file."""
        if path is None:
            path = Path.home() / ".zen-portal" / "config.json"

        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, "w") as f:
            json.dump(self.__dict__, f, indent=2, default=str)
```

---

## Deployment Notes

### Entry Point

```python
# __main__.py
import sys
from pathlib import Path

from .app import ZenPortalApp
from .config import ZenConfig
from .services.tmux import TmuxService
from .services.session_manager import SessionManager

def main():
    config = ZenConfig.load()

    tmux = TmuxService(socket_path=config.socket_path)
    working_dir = config.working_dir or Path.cwd()

    manager = SessionManager(tmux=tmux, working_dir=working_dir)

    app = ZenPortalApp(session_manager=manager)
    result = app.run()

    # Handle exit codes for attach
    if result and result.startswith("attach:"):
        session_id = result.split(":")[1]
        # Re-exec into tmux attach
        import os
        session_name = f"zen-{session_id[:8]}"
        os.execlp("tmux", "tmux", "attach", "-t", session_name)

if __name__ == "__main__":
    main()
```

### pyproject.toml

```toml
[project]
name = "zen-portal"
version = "0.1.0"
description = "Contemplative multi-session Claude Code manager"
requires-python = ">=3.11"
dependencies = [
    "textual>=0.89.0,<1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=4.0",
]

[project.scripts]
zen = "zen_portal.__main__:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["zen_portal/tests"]
```

---

## Summary

| Component | Responsibility | Dependencies |
|-----------|----------------|--------------|
| `TmuxService` | Low-level tmux ops | subprocess |
| `SessionManager` | Business logic | TmuxService |
| `ValidationService` | Input sanitization | None |
| `SessionList` | List display | Session model |
| `OutputView` | Output streaming | None |
| `MainScreen` | Layout + navigation | All widgets |

### Key Design Decisions

1. **Dependency injection**: Services accept dependencies, enabling testing
2. **Event-driven**: Custom messages for loose coupling
3. **Reactive state**: Textual's reactive system for UI updates
4. **Clean separation**: UI knows nothing about tmux
5. **Comprehensive validation**: Security at the input layer
