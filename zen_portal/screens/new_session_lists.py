"""List builders for new session modal attach and resume tabs."""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Generic, TypeVar

from textual.containers import Vertical
from textual.widgets import Static

from ..services.discovery import DiscoveryService, ClaudeSessionInfo, ExternalTmuxSession
from ..services.tmux import TmuxService

T = TypeVar("T")


class ListBuilder(ABC, Generic[T]):
    """Base class for list builders with common selection and display logic."""

    row_id_prefix: str = "list-row-"
    empty_message: str = "no items"

    def __init__(self) -> None:
        self.sessions: list[T] = []
        self.selected = 0

    @abstractmethod
    def load_sessions(self) -> None:
        """Load sessions from the appropriate source."""
        ...

    @abstractmethod
    def _render_row(self, session: T, index: int) -> str:
        """Render a single row label for the given session."""
        ...

    def build_list(self, container: Vertical) -> None:
        """Build the list display (called once on load)."""
        container.remove_children()

        if not self.sessions:
            container.mount(Static(self.empty_message, classes="empty-list"))
            return

        for i, session in enumerate(self.sessions):
            label = self._render_row(session, i)
            classes = "list-row selected" if i == self.selected else "list-row"
            container.mount(
                Static(label, id=f"{self.row_id_prefix}{i}", classes=classes, markup=True)
            )

    def get_selected(self) -> T | None:
        """Get currently selected session."""
        if self.sessions and 0 <= self.selected < len(self.sessions):
            return self.sessions[self.selected]
        return None


class AttachListBuilder(ListBuilder[ExternalTmuxSession]):
    """Builds and manages the attach list for external tmux sessions."""

    row_id_prefix = "attach-row-"
    empty_message = "no tmux sessions"

    def __init__(
        self,
        discovery: DiscoveryService,
        tmux: TmuxService,
    ) -> None:
        super().__init__()
        self._discovery = discovery
        self._tmux = tmux

    def load_sessions(self) -> None:
        """Load all tmux sessions for attach tab."""
        all_names = self._tmux.list_sessions()
        self.sessions = []

        for name in all_names:
            info = self._tmux.get_session_info(name)
            session = self._discovery.analyze_tmux_session(info)
            if not session.is_dead:
                self.sessions.append(session)

    def _render_row(self, session: ExternalTmuxSession, index: int) -> str:
        """Render attach list row: glyph, name, command, cwd."""
        glyph = "[green]●[/green]" if session.has_claude else "○"
        cmd = session.command or "?"
        cwd_name = session.cwd.name if session.cwd else ""
        return f"{glyph} {session.name:<20} {cmd:<10} {cwd_name}"


class ResumeListBuilder(ListBuilder[ClaudeSessionInfo]):
    """Builds and manages the resume list for Claude sessions."""

    row_id_prefix = "resume-row-"
    empty_message = "no sessions in ~/.claude/projects/"

    def __init__(
        self,
        discovery: DiscoveryService,
        known_claude_ids: set[str] | None = None,
    ) -> None:
        super().__init__()
        self._discovery = discovery
        self._known_ids = known_claude_ids or set()

    def load_sessions(self, limit: int = 15) -> None:
        """Load recent Claude sessions for resume tab."""
        self.sessions = self._discovery.list_claude_sessions(limit=limit)

    def _render_row(self, session: ClaudeSessionInfo, index: int) -> str:
        """Render resume list row: glyph, project name, time ago.

        Zen design: project name first (most meaningful), minimal chrome.
        Known sessions (managed by zen-portal) marked with ●, others with ○.
        """
        project_name = session.project_path.name if session.project_path else "unknown"
        time_ago = self._format_time_ago(session.modified_at)

        # Known sessions (tracked by zen-portal) get filled glyph
        is_known = session.session_id in self._known_ids
        glyph = "[cyan]●[/cyan]" if is_known else "[dim]○[/dim]"

        # Zen format: glyph + project name (left) + time (right)
        # Truncate project name to fit, pad for alignment
        max_name_len = 42
        if len(project_name) > max_name_len:
            project_name = project_name[: max_name_len - 1] + "…"

        return f"{glyph} {project_name:<{max_name_len}} [dim]{time_ago:>6}[/dim]"

    def _format_time_ago(self, dt: datetime) -> str:
        """Format time ago - compact, zen style."""
        now = datetime.now()
        diff = now - dt
        seconds = diff.total_seconds()

        if seconds < 60:
            return "now"
        elif seconds < 3600:
            return f"{int(seconds / 60)}m"
        elif seconds < 86400:
            return f"{int(seconds / 3600)}h"
        elif seconds < 604800:  # 7 days
            return f"{int(seconds / 86400)}d"
        else:
            return f"{int(seconds / 604800)}w"


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
