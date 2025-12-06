"""SessionList widget for displaying sessions with selection."""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

from ..models.session import Session, SessionState, SessionType
from ..models.events import SessionSelected


class SessionListItem(Static):
    """A single session row in the list."""

    DEFAULT_CSS = """
    SessionListItem {
        width: 100%;
        height: 1;
        padding: 0 1;
    }

    SessionListItem.selected {
        background: $surface-lighten-1;
    }

    SessionListItem.running {
        color: $success;
    }

    SessionListItem.completed {
        color: $text-muted;
    }

    SessionListItem.paused {
        color: $text;
    }

    SessionListItem.failed, SessionListItem.killed {
        color: $text-disabled;
    }
    """

    def __init__(self, session: Session, selected: bool = False) -> None:
        super().__init__()
        self.session = session
        if selected:
            self.add_class("selected")
        self.add_class(session.state.value)

    def render(self) -> str:
        s = self.session
        # Minimal format: glyph + name + age
        # Type prefix only for non-Claude sessions
        type_prefixes = {
            SessionType.SHELL: "sh:",
            SessionType.CODEX: "cx:",
            SessionType.GEMINI: "gm:",
            SessionType.OPENROUTER: "or:",
        }
        prefix = type_prefixes.get(s.session_type, "")
        name = f"{prefix}{s.display_name}" if prefix else s.display_name

        return f"{s.status_glyph}  {name:<32} {s.age_display:>5}"


class SessionList(Static):
    """List of all sessions with keyboard navigation."""

    sessions: reactive[list[Session]] = reactive(list, recompose=True)
    selected_index: reactive[int] = reactive(0)

    DEFAULT_CSS = """
    SessionList {
        width: 100%;
        height: 100%;
        border: none;
        padding: 0;
    }

    SessionList .empty-message {
        content-align: center middle;
        color: $text-disabled;
        height: 100%;
    }

    SessionList .title {
        height: 1;
        color: $text-disabled;
        text-align: left;
        padding: 0 1;
        margin-bottom: 1;
    }
    """

    def compose(self) -> ComposeResult:
        if not self.sessions:
            yield Static("\n\n\n\n      ○\n\n    empty\n\n    n  new session", classes="empty-message")
            return

        yield Static("sessions", classes="title")
        for i, session in enumerate(self.sessions):
            yield SessionListItem(session, selected=i == self.selected_index)

    def watch_selected_index(self, index: int) -> None:
        """Emit selection event when index changes."""
        if self.sessions and 0 <= index < len(self.sessions):
            self.post_message(SessionSelected(self.sessions[index]))

    def move_down(self) -> None:
        """Select next session (wraps to top)."""
        if self.sessions:
            self.selected_index = (self.selected_index + 1) % len(self.sessions)
            self.refresh(recompose=True)

    def move_up(self) -> None:
        """Select previous session (wraps to bottom)."""
        if self.sessions:
            self.selected_index = (self.selected_index - 1) % len(self.sessions)
            self.refresh(recompose=True)

    def get_selected(self) -> Session | None:
        """Get the currently selected session."""
        if self.sessions and 0 <= self.selected_index < len(self.sessions):
            return self.sessions[self.selected_index]
        return None

    def update_sessions(self, sessions: list[Session]) -> None:
        """Update the session list."""
        self.sessions = sessions
        # Clamp selection index
        if self.selected_index >= len(sessions):
            self.selected_index = max(0, len(sessions) - 1)
        # Force recompose to ensure UI reflects current session states
        # (reactive may not detect changes when list contents mutate in-place)
        self.refresh(recompose=True)
