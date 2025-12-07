"""SessionInfoView widget for displaying session metadata."""

from textual.app import ComposeResult
from textual.reactive import reactive
from textual.widgets import Static

from ..models.session import Session, SessionState
from ..services.proxy_monitor import ProxyMonitor


class SessionInfoView(Static, can_focus=False):
    """Minimalist zen panel showing session metadata.

    Displayed when information mode is active instead of output view.
    This widget is intentionally non-focusable - all interactions
    are handled by MainScreen keybindings.
    """

    session: reactive[Session | None] = reactive(None)

    def __init__(self, proxy_monitor: ProxyMonitor | None = None, **kwargs):
        super().__init__(**kwargs)
        self._proxy_monitor = proxy_monitor

    DEFAULT_CSS = """
    SessionInfoView {
        width: 100%;
        height: 100%;
        border: none;
        padding: 0 1;
    }

    SessionInfoView .title {
        height: 1;
        color: $text-disabled;
        text-align: left;
        margin-bottom: 1;
    }

    SessionInfoView .content {
        height: 1fr;
        padding: 0;
    }

    SessionInfoView .empty-message {
        content-align: center middle;
        color: $text-disabled;
        height: 1fr;
    }

    """

    def compose(self) -> ComposeResult:
        if not self.session:
            yield Static("\n\n\n\n      ·\n\n    select a session", classes="empty-message")
            return

        yield Static("info", classes="title")
        yield Static(self._render_info(), classes="content")

    def _render_info(self) -> str:
        """Render session metadata as minimal formatted text."""
        s = self.session
        if not s:
            return ""

        lines = []

        # Single line: name, state, time
        state_display = self._format_state(s.state)
        lines.append(f"{s.status_glyph} {s.display_name}  {state_display}  {s.age_display}")

        # Directory - only if meaningful
        working_path = s.worktree_path or s.resolved_working_dir
        if working_path:
            path_str = str(working_path)
            # Show just the last 2 path components for brevity
            parts = path_str.split("/")
            if len(parts) > 2:
                path_str = ".../" + "/".join(parts[-2:])
            lines.append(f"[dim]dir[/dim]  {path_str}")

        # Error message for failed sessions
        if s.error_message:
            lines.append("")
            lines.append(f"[red]error[/red]  {s.error_message}")

        return "\n".join(lines)


    def _render_proxy_status(self, s: Session) -> str:
        """Render enhanced proxy status for the session.

        Returns:
            Formatted proxy status line or empty string if not applicable
        """
        return ""

    def _format_state(self, state: SessionState) -> str:
        """Format state with description."""
        descriptions = {
            SessionState.RUNNING: "active",
            SessionState.COMPLETED: "complete",
            SessionState.FAILED: "failed",
            SessionState.PAUSED: "paused",
            SessionState.KILLED: "killed",
        }
        return descriptions.get(state, str(state.value))

    def watch_session(self, new_session: Session | None) -> None:
        """Update display when session changes."""
        self.refresh(recompose=True)

    def update_session(self, session: Session | None) -> None:
        """Update the displayed session."""
        self.session = session
