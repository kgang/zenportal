"""List builders for new session modal attach and resume tabs."""

from datetime import datetime

from textual.containers import Vertical
from textual.widgets import Static

from ..services.discovery import DiscoveryService, ClaudeSessionInfo, ExternalTmuxSession
from ..services.tmux import TmuxService


class AttachListBuilder:
    """Builds and manages the attach list for external tmux sessions."""

    def __init__(
        self,
        discovery: DiscoveryService,
        tmux: TmuxService,
    ):
        self._discovery = discovery
        self._tmux = tmux
        self.sessions: list[ExternalTmuxSession] = []
        self.selected = 0

    def load_sessions(self) -> None:
        """Load all tmux sessions for attach tab."""
        all_names = self._tmux.list_sessions()
        self.sessions = []

        for name in all_names:
            info = self._tmux.get_session_info(name)
            session = self._discovery.analyze_tmux_session(info)
            if not session.is_dead:
                self.sessions.append(session)

    def build_list(self, container: Vertical) -> None:
        """Build the attach list display (called once on load)."""
        container.remove_children()

        if not self.sessions:
            container.mount(Static("no tmux sessions", classes="empty-list"))
            return

        for i, session in enumerate(self.sessions):
            glyph = "[green]●[/green]" if session.has_claude else "○"
            cmd = session.command or "?"
            cwd_name = session.cwd.name if session.cwd else ""

            label = f"{glyph} {session.name:<20} {cmd:<10} {cwd_name}"
            classes = "list-row selected" if i == self.selected else "list-row"
            container.mount(Static(label, id=f"attach-row-{i}", classes=classes, markup=True))

    def get_selected(self) -> ExternalTmuxSession | None:
        """Get currently selected session."""
        if self.sessions and 0 <= self.selected < len(self.sessions):
            return self.sessions[self.selected]
        return None


class ResumeListBuilder:
    """Builds and manages the resume list for Claude sessions."""

    def __init__(
        self,
        discovery: DiscoveryService,
        known_claude_ids: set[str] | None = None,
    ):
        self._discovery = discovery
        self._known_ids = known_claude_ids or set()
        self.sessions: list[ClaudeSessionInfo] = []
        self.selected = 0

    def load_sessions(self, limit: int = 15) -> None:
        """Load recent Claude sessions for resume tab."""
        self.sessions = self._discovery.list_claude_sessions(limit=limit)

    def build_list(self, container: Vertical) -> None:
        """Build the resume list display (called once on load).

        Sessions known to zen-portal (via state) are tagged with a glyph.
        """
        container.remove_children()

        if not self.sessions:
            container.mount(Static("no claude sessions found", classes="empty-list"))
            return

        for i, session in enumerate(self.sessions):
            short_id = session.session_id[:8]
            project_name = session.project_path.name if session.project_path else "?"
            time_ago = self._format_time_ago(session.modified_at)

            # Tag sessions known to zen-portal
            is_known = session.session_id in self._known_ids
            glyph = "[cyan]●[/cyan]" if is_known else "○"

            label = f"{glyph} {short_id}  {project_name:<24} {time_ago}"
            classes = "list-row selected" if i == self.selected else "list-row"
            container.mount(Static(label, id=f"resume-row-{i}", classes=classes, markup=True))

    def get_selected(self) -> ClaudeSessionInfo | None:
        """Get currently selected session."""
        if self.sessions and 0 <= self.selected < len(self.sessions):
            return self.sessions[self.selected]
        return None

    def _format_time_ago(self, dt: datetime) -> str:
        """Format a datetime as a human-readable time ago string."""
        now = datetime.now()
        diff = now - dt
        seconds = diff.total_seconds()

        if seconds < 60:
            return "now"
        elif seconds < 3600:
            minutes = int(seconds / 60)
            return f"{minutes}m ago"
        elif seconds < 86400:
            hours = int(seconds / 3600)
            return f"{hours}h ago"
        else:
            days = int(seconds / 86400)
            return f"{days}d ago"


def update_list_selection(
    query_one_func,
    row_id_prefix: str,
    old_idx: int,
    new_idx: int,
) -> None:
    """Update selection styling without rebuilding the list.

    Args:
        query_one_func: Function to query widgets (e.g., self.query_one)
        row_id_prefix: Prefix for row IDs (e.g., "attach-row-" or "resume-row-")
        old_idx: Previous selected index
        new_idx: New selected index
    """
    if old_idx == new_idx:
        return
    try:
        old_row = query_one_func(f"#{row_id_prefix}{old_idx}", Static)
        old_row.remove_class("selected")
    except Exception:
        pass
    try:
        new_row = query_one_func(f"#{row_id_prefix}{new_idx}", Static)
        new_row.add_class("selected")
    except Exception:
        pass
