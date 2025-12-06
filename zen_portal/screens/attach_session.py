"""AttachSessionModal: Modal for attaching to external tmux sessions."""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Static

from ..services.discovery import DiscoveryService, ExternalTmuxSession
from ..services.tmux import TmuxService


class AttachMode(Enum):
    """Mode of attachment."""

    TMUX_SESSION = "tmux_session"  # Attach to external tmux


@dataclass
class AttachSessionResult:
    """Result from attach session modal."""

    tmux_name: str  # External tmux session name
    has_claude: bool  # Whether Claude is detected
    claude_session_id: str | None = None  # Detected Claude session ID
    cwd: Path | None = None  # Working directory of the tmux session


class AttachSessionModal(ModalScreen[AttachSessionResult | None]):
    """Modal for attaching to external tmux sessions.

    Displays available tmux sessions (not managed by zen-portal) and allows
    attaching to them. If Claude is detected running, syncs the session back.
    """

    DEFAULT_CSS = """
    AttachSessionModal {
        align: center middle;
    }

    AttachSessionModal #dialog {
        width: 70;
        height: auto;
        max-height: 90%;
        padding: 1 2;
        background: $surface;
        border: round $surface-lighten-1;
        overflow-y: auto;
    }

    AttachSessionModal .title {
        text-align: center;
        color: $text-muted;
        margin-bottom: 1;
    }

    AttachSessionModal #session-list {
        height: auto;
        padding: 0;
    }

    AttachSessionModal .session-row {
        height: 1;
        padding: 0 1;
    }

    AttachSessionModal .session-row:hover {
        background: $surface-lighten-1;
    }

    AttachSessionModal .session-row.selected {
        background: $primary-darken-2;
    }

    AttachSessionModal .empty {
        color: $text-disabled;
        text-style: italic;
        padding: 1;
        text-align: center;
    }

    AttachSessionModal .hint {
        text-align: center;
        color: $text-muted;
        margin-top: 1;
    }

    AttachSessionModal .claude-indicator {
        color: $success;
    }

    AttachSessionModal .dead-indicator {
        color: $error;
    }
    """

    BINDINGS = [
        ("j", "move_down", "down"),
        ("k", "move_up", "up"),
        ("down", "move_down", "down"),
        ("up", "move_up", "up"),
        ("enter", "select", "select"),
        ("escape", "cancel", "cancel"),
    ]

    def __init__(
        self,
        discovery_service: DiscoveryService | None = None,
        tmux_service: TmuxService | None = None,
        session_prefix: str = "zen-",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._discovery = discovery_service or DiscoveryService()
        self._tmux = tmux_service or TmuxService()
        self._prefix = session_prefix
        self._sessions: list[ExternalTmuxSession] = []
        self._selected_index = 0

    def compose(self) -> ComposeResult:
        with Vertical(id="dialog"):
            yield Static("attach to tmux", classes="title")
            yield Vertical(id="session-list")
            yield Static("j/k navigate · enter attach · esc cancel", classes="hint")

    def on_mount(self) -> None:
        self._load_sessions()

    def _load_sessions(self) -> None:
        """Load all tmux sessions (only alive ones)."""
        external_names = self._tmux.list_sessions()

        self._sessions = []
        for name in external_names:
            info = self._tmux.get_session_info(name)
            session = self._discovery.analyze_tmux_session(info)
            # Only show sessions that are alive (can actually attach)
            if not session.is_dead:
                self._sessions.append(session)

        self._refresh_list()

    def _refresh_list(self) -> None:
        """Refresh the session list display."""
        session_list = self.query_one("#session-list", Vertical)
        session_list.remove_children()

        if not self._sessions:
            session_list.mount(Static("no external tmux sessions", classes="empty"))
            return

        for i, session in enumerate(self._sessions):
            # Build display line: glyph name command cwd
            glyph = "[green]●[/green]" if session.has_claude else "○"
            cmd = session.command or "?"
            cwd_name = session.cwd.name if session.cwd else ""
            claude_mark = " [green]claude[/green]" if session.has_claude else ""

            label = f"{glyph} {session.name:<20} {cmd:<10} {cwd_name}{claude_mark}"

            classes = "session-row"
            if i == self._selected_index:
                classes += " selected"

            session_list.mount(Static(label, classes=classes, id=f"session-{i}", markup=True))

    def _update_selection(self) -> None:
        """Update visual selection."""
        for i in range(len(self._sessions)):
            try:
                item = self.query_one(f"#session-{i}", Static)
                if i == self._selected_index:
                    item.add_class("selected")
                else:
                    item.remove_class("selected")
            except Exception:
                pass

    def action_move_down(self) -> None:
        if self._sessions and self._selected_index < len(self._sessions) - 1:
            self._selected_index += 1
            self._update_selection()

    def action_move_up(self) -> None:
        if self._sessions and self._selected_index > 0:
            self._selected_index -= 1
            self._update_selection()

    def action_select(self) -> None:
        if not self._sessions:
            self.app.notify("no session to attach", severity="warning")
            return

        if self._selected_index >= len(self._sessions):
            return

        session = self._sessions[self._selected_index]
        self.dismiss(AttachSessionResult(
            tmux_name=session.name,
            has_claude=session.has_claude,
            claude_session_id=session.claude_session_id,
            cwd=session.cwd,
        ))

    def action_cancel(self) -> None:
        self.dismiss(None)
