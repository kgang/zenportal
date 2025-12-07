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

    SessionListItem.grabbed {
        background: $primary-darken-3;
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

    def __init__(self, session: Session, selected: bool = False, grabbed: bool = False) -> None:
        super().__init__()
        self.session = session
        if selected:
            self.add_class("selected")
        if grabbed:
            self.add_class("grabbed")
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
    """List of all sessions with keyboard navigation and grab mode for reordering."""

    sessions: reactive[list[Session]] = reactive(list, recompose=True)
    selected_index: reactive[int] = reactive(0)
    grab_mode: reactive[bool] = reactive(False)

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

    SessionList .title.grab-mode {
        color: $primary;
    }
    """

    def compose(self) -> ComposeResult:
        if not self.sessions:
            yield Static("\n\n\n\n      ○\n\n    empty\n\n    n  new session", classes="empty-message")
            return

        title_classes = "title grab-mode" if self.grab_mode else "title"
        title_text = "≡ reorder" if self.grab_mode else "sessions"
        yield Static(title_text, classes=title_classes)
        for i, session in enumerate(self.sessions):
            is_selected = i == self.selected_index
            is_grabbed = is_selected and self.grab_mode
            yield SessionListItem(session, selected=is_selected, grabbed=is_grabbed)

    def watch_selected_index(self, index: int) -> None:
        """Emit selection event when index changes."""
        if self.sessions and 0 <= index < len(self.sessions):
            self.post_message(SessionSelected(self.sessions[index]))

    def move_down(self) -> None:
        """Move selection down, or move session down if in grab mode."""
        if not self.sessions:
            return
        if self.grab_mode:
            self._move_session_down()
        else:
            self.selected_index = (self.selected_index + 1) % len(self.sessions)
        self.refresh(recompose=True)

    def move_up(self) -> None:
        """Move selection up, or move session up if in grab mode."""
        if not self.sessions:
            return
        if self.grab_mode:
            self._move_session_up()
        else:
            self.selected_index = (self.selected_index - 1) % len(self.sessions)
        self.refresh(recompose=True)

    def _move_session_down(self) -> None:
        """Move selected session down in the list."""
        if self.selected_index >= len(self.sessions) - 1:
            return  # Already at bottom
        sessions = list(self.sessions)
        i = self.selected_index
        sessions[i], sessions[i + 1] = sessions[i + 1], sessions[i]
        self.sessions = sessions
        self.selected_index = i + 1

    def _move_session_up(self) -> None:
        """Move selected session up in the list."""
        if self.selected_index <= 0:
            return  # Already at top
        sessions = list(self.sessions)
        i = self.selected_index
        sessions[i], sessions[i - 1] = sessions[i - 1], sessions[i]
        self.sessions = sessions
        self.selected_index = i - 1

    def toggle_grab_mode(self) -> bool:
        """Toggle grab mode for reordering. Returns new grab state."""
        self.grab_mode = not self.grab_mode
        self.refresh(recompose=True)
        return self.grab_mode

    def exit_grab_mode(self) -> None:
        """Exit grab mode without toggling."""
        if self.grab_mode:
            self.grab_mode = False
            self.refresh(recompose=True)

    def get_selected(self) -> Session | None:
        """Get the currently selected session."""
        if self.sessions and 0 <= self.selected_index < len(self.sessions):
            return self.sessions[self.selected_index]
        return None

    def get_session_order(self) -> list[str]:
        """Get session IDs in current display order."""
        return [s.id for s in self.sessions]

    def update_sessions(self, sessions: list[Session]) -> None:
        """Update the session list."""
        self.sessions = sessions
        # Clamp selection index
        if self.selected_index >= len(sessions):
            self.selected_index = max(0, len(sessions) - 1)
        # Force recompose to ensure UI reflects current session states
        # (reactive may not detect changes when list contents mutate in-place)
        self.refresh(recompose=True)

    def update_sessions_preserve_order(self, sessions: list[Session], order: list[str]) -> None:
        """Update sessions while preserving custom order."""
        if not order:
            self.update_sessions(sessions)
            return

        # Build lookup
        by_id = {s.id: s for s in sessions}
        ordered = []

        # Add sessions in saved order
        for sid in order:
            if sid in by_id:
                ordered.append(by_id.pop(sid))

        # Append any new sessions not in order (at the top)
        new_sessions = [s for s in sessions if s.id in by_id]
        # Sort new by creation time (newest first)
        new_sessions.sort(key=lambda s: s.created_at, reverse=True)
        ordered = new_sessions + ordered

        self.update_sessions(ordered)
